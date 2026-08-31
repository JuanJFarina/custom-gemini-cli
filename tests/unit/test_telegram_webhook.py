import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

import asyncpg
from fastapi import BackgroundTasks, FastAPI, Request
from pytest import MonkeyPatch

import harle_api.app as app_module
from harle_services.access import (
    QuotaExceeded,
    QuotaReservation,
    TemporaryBan,
    UsageQuotaService,
)
from harle_services.bootstrap import ProcessRuntime
from harle_services.messaging import (
    TelegramUpdateDeduplicator,
    UserWorkCoordinator,
)
from harle_services.runtime import (
    RequestAccepted,
    RequestAdmission,
    RequestAdmissionService,
    UserRuntime,
    UserRuntimeFactory,
)
from harle_services.tools import ToolsInjector


@dataclass(frozen=True)
class FakeSettings:
    TELEGRAM_WEBHOOK_SECRET: str = "secret"
    TELEGRAM_BOT_TOKEN: str = "token"


class FakeUpdateDeduplicator:
    def __init__(self) -> None:
        self.claimed: set[int] = set()

    async def claim(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
    ) -> bool:
        del telegram_user_id, telegram_chat_id
        if update_id in self.claimed:
            return False
        self.claimed.add(update_id)
        return True


class FakeAdmissions:
    def __init__(self, results: list[RequestAdmission]) -> None:
        self.calls = 0
        self.results = results

    async def admit(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_update_id: int,
    ) -> RequestAdmission:
        del telegram_user_id, telegram_chat_id, telegram_update_id
        result = self.results[self.calls]
        self.calls += 1
        return result


def fake_runtime(
    admissions: FakeAdmissions,
    deduplicator: FakeUpdateDeduplicator,
) -> ProcessRuntime:
    return ProcessRuntime(
        pool=cast(asyncpg.Pool, object()),
        admissions=cast(RequestAdmissionService, admissions),
        users=cast(UserRuntimeFactory, object()),
        tools=cast(ToolsInjector, object()),
        telegram_updates=cast(TelegramUpdateDeduplicator, deduplicator),
        user_work=UserWorkCoordinator(),
        usage_quota=cast(UsageQuotaService, object()),
    )


def test_duplicate_webhook_starts_assistant_only_once(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        reservation = QuotaReservation(
            id=uuid4(),
            user_id=uuid4(),
            remaining=59,
            resets_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        admissions = FakeAdmissions(
            [
                RequestAccepted(
                    user_runtime=cast(UserRuntime, object()),
                    quota_reservation=reservation,
                ),
            ],
        )
        deduplicator = FakeUpdateDeduplicator()
        runtime = fake_runtime(admissions, deduplicator)
        application = FastAPI()
        application.state.runtime = runtime
        request = Request({"type": "http", "app": application})
        process_calls = 0

        async def fake_process(**_: object) -> None:
            nonlocal process_calls
            process_calls += 1

        monkeypatch.setattr(app_module, "get_settings", FakeSettings)
        monkeypatch.setattr(app_module, "process_telegram_message", fake_process)
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

        assert first.body == (
            b'{"ok":true,"accepted":true,"remaining":59,'
            b'"reset_at":"2026-09-01T00:00:00Z"}'
        )
        assert duplicate.body == b'{"ok":true,"accepted":false,"duplicate":true}'
        assert admissions.calls == 1
        assert process_calls == 1

    asyncio.run(verify())


def test_ban_and_quota_rejections_do_not_start_assistant(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        reset_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        admissions = FakeAdmissions(
            [
                TemporaryBan(blocked_until=reset_at, notify_user=True),
                QuotaExceeded(remaining=0, resets_at=reset_at),
            ],
        )
        runtime = fake_runtime(
            admissions,
            FakeUpdateDeduplicator(),
        )
        application = FastAPI()
        application.state.runtime = runtime
        request = Request({"type": "http", "app": application})
        process_calls = 0
        notices: list[str] = []

        async def fake_process(**_: object) -> None:
            nonlocal process_calls
            process_calls += 1

        async def fake_send_message(
            *,
            bot_token: str,
            chat_id: int,
            text: str,
        ) -> None:
            del bot_token, chat_id
            notices.append(text)

        monkeypatch.setattr(app_module, "get_settings", FakeSettings)
        monkeypatch.setattr(app_module, "process_telegram_message", fake_process)
        monkeypatch.setattr(app_module, "send_message", fake_send_message)

        responses = []
        for update_id in (100, 101):
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

        assert b'"reason":"temporarily_banned"' in responses[0].body
        assert b'"reason":"monthly_quota_exceeded"' in responses[1].body
        assert process_calls == 0
        assert admissions.calls == 2
        assert len(notices) == 2
        assert "2026-09-01T00:00:00Z" in notices[0]
        assert "0 requests remaining" in notices[1]

    asyncio.run(verify())
