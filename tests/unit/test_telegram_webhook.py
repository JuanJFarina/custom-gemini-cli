import asyncio
from dataclasses import dataclass

from fastapi import BackgroundTasks, FastAPI, Request
from pytest import MonkeyPatch

import harle_api.app as app_module
from harle_services.bootstrap import ProcessRuntime
from harle_services.messaging import UserWorkCoordinator


@dataclass(frozen=True)
class FakeSettings:
    TELEGRAM_WEBHOOK_SECRET: str = "secret"


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


class FakeUsers:
    def __init__(self) -> None:
        self.calls = 0

    async def create(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_update_id: int,
    ) -> object:
        del telegram_user_id, telegram_chat_id, telegram_update_id
        self.calls += 1
        return object()


def test_duplicate_webhook_starts_assistant_only_once(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        users = FakeUsers()
        deduplicator = FakeUpdateDeduplicator()
        runtime = ProcessRuntime(
            pool=object(),
            users=users,
            tools=object(),
            telegram_updates=deduplicator,
            user_work=UserWorkCoordinator(),
        )
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

        assert first.body == b'{"ok":true,"accepted":true}'
        assert duplicate.body == b'{"ok":true,"accepted":false,"duplicate":true}'
        assert users.calls == 1
        assert process_calls == 1

    asyncio.run(verify())
