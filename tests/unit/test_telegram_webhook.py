import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

import asyncpg
from fastapi import BackgroundTasks, FastAPI, Request
from pytest import MonkeyPatch

import harle_api.app as app_module
from harle_services.access import PreflightService, TemporaryBan
from harle_services.bootstrap import ProcessRuntime
from harle_services.messaging import (
    MessageCoordinator,
    MessageSubmission,
    MessageSubmissionStatus,
)
from harle_services.runtime import UserRuntimeFactory
from harle_services.tools import ToolsInjector


@dataclass(frozen=True)
class FakeSettings:
    TELEGRAM_WEBHOOK_SECRET: str = "secret"
    TELEGRAM_BOT_TOKEN: str = "token"


class FakeMessages:
    def __init__(self, statuses: list[MessageSubmissionStatus]) -> None:
        self.statuses = statuses
        self.received: list[int] = []

    async def receive(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
        text: str,
    ) -> MessageSubmission:
        del telegram_user_id, telegram_chat_id, text
        self.received.append(update_id)
        status = self.statuses.pop(0)
        temporary_ban = (
            TemporaryBan(
                blocked_until=datetime(2026, 9, 11, 4, tzinfo=timezone.utc),
                notify_user=True,
            )
            if status is MessageSubmissionStatus.RATE_LIMITED
            else None
        )
        return MessageSubmission(status, temporary_ban)


def fake_runtime(messages: FakeMessages) -> ProcessRuntime:
    return ProcessRuntime(
        pool=cast(asyncpg.Pool, object()),
        preflight=cast(PreflightService, object()),
        users=cast(UserRuntimeFactory, object()),
        tools=cast(ToolsInjector, object()),
        messages=cast(MessageCoordinator, messages),
    )


def test_webhook_persists_before_starting_one_process_and_ignores_duplicate(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        messages = FakeMessages(
            [
                MessageSubmissionStatus.STARTED,
                MessageSubmissionStatus.DUPLICATE,
            ],
        )
        runtime = fake_runtime(messages)
        application = FastAPI()
        application.state.runtime = runtime
        request = Request({"type": "http", "app": application})
        process_calls = 0

        async def fake_process(**_: object) -> None:
            nonlocal process_calls
            process_calls += 1

        monkeypatch.setattr(app_module, "get_settings", FakeSettings)
        monkeypatch.setattr(app_module, "process_telegram_messages", fake_process)
        update = {
            "update_id": 100,
            "message": {
                "text": "Hello",
                "chat": {"id": 200},
                "from": {"id": 300},
            },
        }

        first_tasks = BackgroundTasks()
        first = await app_module.post_telegram_webhook(
            update=update,
            background_tasks=first_tasks,
            request=request,
            x_telegram_bot_api_secret_token="secret",
        )
        await first_tasks()

        duplicate_tasks = BackgroundTasks()
        duplicate = await app_module.post_telegram_webhook(
            update=update,
            background_tasks=duplicate_tasks,
            request=request,
            x_telegram_bot_api_secret_token="secret",
        )
        await duplicate_tasks()

        assert first.body == b'{"ok":true,"accepted":true,"disposition":"started"}'
        assert duplicate.body == b'{"ok":true,"accepted":false,"duplicate":true}'
        assert messages.received == [100, 100]
        assert process_calls == 1

    asyncio.run(verify())


def test_joined_queued_and_interrupted_updates_do_not_start_another_process(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        messages = FakeMessages(
            [
                MessageSubmissionStatus.JOINED,
                MessageSubmissionStatus.QUEUED,
                MessageSubmissionStatus.INTERRUPTED,
            ],
        )
        runtime = fake_runtime(messages)
        application = FastAPI()
        application.state.runtime = runtime
        request = Request({"type": "http", "app": application})
        process_calls = 0
        async def fake_process(**_: object) -> None:
            nonlocal process_calls
            process_calls += 1

        monkeypatch.setattr(app_module, "get_settings", FakeSettings)
        monkeypatch.setattr(app_module, "process_telegram_messages", fake_process)

        responses = []
        for update_id in (100, 101, 102):
            tasks = BackgroundTasks()
            response = await app_module.post_telegram_webhook(
                update={
                    "update_id": update_id,
                    "message": {
                        "text": "Hello",
                        "chat": {"id": 200},
                        "from": {"id": 300},
                    },
                },
                background_tasks=tasks,
                request=request,
                x_telegram_bot_api_secret_token="secret",
            )
            await tasks()
            responses.append(response)

        assert b'"disposition":"joined"' in responses[0].body
        assert b'"disposition":"queued"' in responses[1].body
        assert b'"reason":"interrupted_after_tool_execution"' in responses[2].body
        assert process_calls == 0

    asyncio.run(verify())


def test_rate_limited_update_notifies_without_starting_processing(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        messages = FakeMessages([MessageSubmissionStatus.RATE_LIMITED])
        runtime = fake_runtime(messages)
        application = FastAPI()
        application.state.runtime = runtime
        request = Request({"type": "http", "app": application})
        notices: list[str] = []
        process_calls = 0

        async def fake_process(**_: object) -> None:
            nonlocal process_calls
            process_calls += 1

        async def fake_send_message(*, text: str, **_: object) -> None:
            notices.append(text)

        monkeypatch.setattr(app_module, "get_settings", FakeSettings)
        monkeypatch.setattr(app_module, "process_telegram_messages", fake_process)
        monkeypatch.setattr(app_module, "send_message", fake_send_message)

        tasks = BackgroundTasks()
        response = await app_module.post_telegram_webhook(
            update={
                "update_id": 100,
                "message": {
                    "text": "Hello",
                    "chat": {"id": 200},
                    "from": {"id": 300},
                },
            },
            background_tasks=tasks,
            request=request,
            x_telegram_bot_api_secret_token="secret",
        )
        await tasks()

        assert b'"reason":"temporarily_banned"' in response.body
        assert b'"notified":true' in response.body
        assert len(notices) == 1
        assert process_calls == 0

    asyncio.run(verify())
