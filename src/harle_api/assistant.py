from asyncio import CancelledError, Task, create_task
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import httpx
from asyncpg import PostgresError

from harle_agent.agent import Harle
from harle_agent.models import (
    HarlePersonalContext,
    HarleRunResult,
    HarleStores,
)
from harle_agent.retry_decorator import ASSISTANT_FAILURES
from harle_api.settings import ApiSettings, get_settings
from harle_api.telegram import (
    send_message,
    send_typing_action,
)
from harle_services.access import (
    PreflightAccepted,
    QuotaExceeded,
)
from harle_services.bootstrap import ProcessRuntime
from harle_services.messaging import MessageCoordinator, MessageTurn
from harle_services.runtime import UserRuntime
from harle_services.tools import ToolInjectionContext, ToolsInjector
from harle_utils import (
    InactiveSubscriptionError,
    MissingProfileError,
    UnknownIdentityError,
)

PROCESSING_FAILURES = (*ASSISTANT_FAILURES, OSError, PostgresError)


@dataclass(frozen=True, slots=True)
class _GeneratedTurn:
    harle: Harle
    result: HarleRunResult


async def process_telegram_messages(
    *,
    telegram_user_id: int,
    runtime: ProcessRuntime,
    settings: ApiSettings | None = None,
) -> None:
    settings = settings or get_settings()
    while turn := await runtime.messages.current_turn(telegram_user_id):
        has_next = await _process_turn(
            turn=turn,
            runtime=runtime,
            settings=settings,
        )
        if not has_next:
            return


async def _process_turn(
    *,
    turn: MessageTurn,
    runtime: ProcessRuntime,
    settings: ApiSettings,
) -> bool:
    try:
        admission = await runtime.preflight.check(turn.telegram_user_id)
    except (UnknownIdentityError, InactiveSubscriptionError):
        return await runtime.messages.finish_failed(
            telegram_user_id=turn.telegram_user_id,
            retryable=True,
        )

    if isinstance(admission, QuotaExceeded):
        await _send_notice(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=turn.telegram_chat_id,
            text=(
                f"You have {admission.remaining} requests remaining this month. "
                f"Your allowance resets at {_utc_boundary(admission.resets_at)}."
            ),
        )
        return await runtime.messages.finish_failed(
            telegram_user_id=turn.telegram_user_id,
            retryable=True,
        )

    if not isinstance(admission, PreflightAccepted):
        raise RuntimeError("Unexpected preflight result.")

    try:
        user_runtime = await runtime.users.create_for_resolved_user(
            resolved_user=admission.resolved_user,
            telegram_chat_id=turn.telegram_chat_id,
        )
        return await _run_admitted_turn(
            telegram_user_id=turn.telegram_user_id,
            user_runtime=user_runtime,
            coordinator=runtime.messages,
            tools=runtime.tools,
            settings=settings,
        )
    except (MissingProfileError, OSError, PostgresError, RuntimeError):
        return await runtime.messages.finish_failed(
            telegram_user_id=turn.telegram_user_id,
            retryable=True,
        )
    finally:
        await runtime.preflight.release(admission.quota_reservation)


async def _run_admitted_turn(
    *,
    telegram_user_id: int,
    user_runtime: UserRuntime,
    coordinator: MessageCoordinator,
    tools: ToolsInjector,
    settings: ApiSettings,
) -> bool:
    try:
        await send_typing_action(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            chat_id=user_runtime.telegram_chat_id,
        )
    except httpx.HTTPError:
        pass

    while turn := await coordinator.current_turn(telegram_user_id):
        task = create_task(
            _generate_response(
                turn=turn,
                user_runtime=user_runtime,
                coordinator=coordinator,
                tools=tools,
            ),
        )
        generic_task = cast(Task[object], task)
        await coordinator.bind_reasoning_task(
            telegram_user_id=telegram_user_id,
            generation=turn.generation,
            task=generic_task,
        )
        try:
            generated = await task
        except CancelledError:
            if await coordinator.should_restart(
                telegram_user_id=telegram_user_id,
                generation=turn.generation,
            ):
                continue
            raise
        except PROCESSING_FAILURES:
            return await coordinator.finish_failed(
                telegram_user_id=telegram_user_id,
                retryable=True,
            )
        finally:
            await coordinator.reasoning_finished(
                telegram_user_id=telegram_user_id,
                task=generic_task,
            )

        if await coordinator.should_restart(
            telegram_user_id=telegram_user_id,
            generation=turn.generation,
        ):
            continue
        if not await coordinator.begin_delivery(
            telegram_user_id=telegram_user_id,
            generation=turn.generation,
        ):
            continue
        try:
            await send_message(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                chat_id=turn.telegram_chat_id,
                text=generated.result.response_text,
            )
        except httpx.HTTPError:
            return await coordinator.finish_failed(
                telegram_user_id=telegram_user_id,
                retryable=False,
            )
        try:
            await generated.harle.save(
                prompt=turn.prompt,
                run_result=generated.result,
                telegram_update_ids=turn.update_ids,
            )
        except (OSError, PostgresError, RuntimeError):
            return await coordinator.finish_failed(
                telegram_user_id=telegram_user_id,
                retryable=False,
            )
        return await coordinator.finish_delivered(
            telegram_user_id=telegram_user_id,
            update_ids=turn.update_ids,
        )

    return False


async def _generate_response(
    *,
    turn: MessageTurn,
    user_runtime: UserRuntime,
    coordinator: MessageCoordinator,
    tools: ToolsInjector,
) -> _GeneratedTurn:
    tool_store = tools.inject(
        ToolInjectionContext(
            resolved_user=user_runtime.resolved_user,
            timezone=user_runtime.user_profile.timezone,
            prompt=turn.prompt,
        ),
    )
    harle_stores = HarleStores(
        conversation_store=user_runtime.conversation_store,
        tool_store=tool_store,
    )
    user_profile = user_runtime.user_profile
    assistant_profile = user_runtime.assistant_profile
    harle = Harle(
        stores=harle_stores,
        personal_context=HarlePersonalContext(
            user_name=user_runtime.resolved_user.user.display_name,
            preferred_name=user_profile.preferred_name,
            locale=user_profile.locale,
            timezone=user_profile.timezone,
            assistant_profile=(
                f"{assistant_profile.display_name}: {assistant_profile.profile_text}"
            ),
            personal_history=(
                user_profile.personal_history
                or "No personal history has been supplied."
            ),
            latitude=(
                float(user_profile.latitude)
                if user_profile.latitude is not None
                else None
            ),
            longitude=(
                float(user_profile.longitude)
                if user_profile.longitude is not None
                else None
            ),
        ),
        on_tool_started=lambda: coordinator.mark_tool_started(
            telegram_user_id=turn.telegram_user_id,
            generation=turn.generation,
        ),
    )
    return _GeneratedTurn(harle=harle, result=await harle.call(turn.prompt))


def _utc_boundary(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


async def _send_notice(*, bot_token: str, chat_id: int, text: str) -> None:
    try:
        await send_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=text,
        )
    except httpx.HTTPError:
        pass
