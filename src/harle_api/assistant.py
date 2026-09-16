from asyncio import CancelledError, Task, create_task
from datetime import datetime
from typing import cast

from asyncpg import PostgresError

from harle_agent.retry_decorator import ASSISTANT_FAILURES
from harle_domain.messaging import OutboundMessenger
from harle_services.access import (
    PreflightAccepted,
    QuotaExceeded,
)
from harle_services.assistant import GeneratedResponse, generate_response
from harle_services.bootstrap import ProcessRuntime
from harle_services.messaging import MessageCoordinator, MessageTurn
from harle_services.runtime import UserRuntime
from harle_services.tools import ToolInjectionContext, ToolsInjector
from harle_utils import (
    InactiveSubscriptionError,
    MessageDeliveryError,
    MissingProfileError,
    UnknownIdentityError,
    log,
)

PROCESSING_FAILURES = (*ASSISTANT_FAILURES, OSError, PostgresError)
_GeneratedTurn = GeneratedResponse


async def process_telegram_messages(
    *,
    telegram_user_id: int,
    runtime: ProcessRuntime,
) -> None:
    while turn := await runtime.messages.current_turn(telegram_user_id):
        has_next = await _process_turn(
            turn=turn,
            runtime=runtime,
        )
        if not has_next:
            return


async def _process_turn(
    *,
    turn: MessageTurn,
    runtime: ProcessRuntime,
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
            messenger=runtime.messenger,
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
            messenger=runtime.messenger,
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
    messenger: OutboundMessenger,
) -> bool:
    try:
        await messenger.send_typing_action(
            chat_id=user_runtime.telegram_chat_id,
        )
    except MessageDeliveryError:
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
        except PROCESSING_FAILURES as exc:
            log.warning("Turn generation failed: %s", type(exc).__name__)
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
            await messenger.send_message(
                chat_id=turn.telegram_chat_id,
                text=generated.result.response_text,
            )
        except MessageDeliveryError:
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
) -> GeneratedResponse:
    tool_store = tools.inject(
        ToolInjectionContext(
            resolved_user=user_runtime.resolved_user,
            timezone=user_runtime.user_profile.timezone,
            prompt=turn.prompt,
        ),
    )
    return await generate_response(
        prompt=turn.prompt,
        user_runtime=user_runtime,
        tool_store=tool_store,
        on_tool_started=lambda: coordinator.mark_tool_started(
            telegram_user_id=turn.telegram_user_id,
            generation=turn.generation,
        ),
    )


def _utc_boundary(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


async def _send_notice(
    *,
    messenger: OutboundMessenger,
    chat_id: int,
    text: str,
) -> None:
    try:
        await messenger.send_message(
            chat_id=chat_id,
            text=text,
        )
    except MessageDeliveryError:
        pass
