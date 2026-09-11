import asyncio
from types import SimpleNamespace
from typing import cast

import httpx
from pytest import MonkeyPatch

import harle_api.assistant as assistant_module
from harle_agent.models import HarleRunResult
from harle_api.settings import ApiSettings
from harle_services.messaging import MessageCoordinator, MessageFragment, MessageTurn
from harle_services.runtime import UserRuntime
from harle_services.tools import ToolsInjector


class FakeHarle:
    def __init__(self) -> None:
        self.saved = False

    async def save(self, **_: object) -> None:
        self.saved = True


class FakeCoordinator:
    def __init__(self, turn: MessageTurn) -> None:
        self.turn = turn
        self.finished_failed = False

    async def current_turn(self, telegram_user_id: int) -> MessageTurn | None:
        del telegram_user_id
        return self.turn

    async def bind_reasoning_task(self, **_: object) -> None:
        return None

    async def reasoning_finished(self, **_: object) -> None:
        return None

    async def should_restart(self, **_: object) -> bool:
        return False

    async def begin_delivery(self, **_: object) -> bool:
        return True

    async def finish_failed(self, **_: object) -> bool:
        self.finished_failed = True
        return False


def test_failed_telegram_delivery_does_not_persist_completion(
    monkeypatch: MonkeyPatch,
) -> None:
    async def verify() -> None:
        turn = MessageTurn(
            telegram_user_id=1,
            telegram_chat_id=2,
            messages=(MessageFragment(3, 1, 2, "Hello"),),
            generation=0,
        )
        coordinator = FakeCoordinator(turn)
        harle = FakeHarle()

        async def generate_response(**_: object) -> object:
            return assistant_module._GeneratedTurn(
                harle=cast(assistant_module.Harle, harle),
                result=HarleRunResult(response_text="Hi"),
            )

        async def do_nothing(**_: object) -> None:
            return None

        async def fail_delivery(**_: object) -> None:
            raise httpx.ConnectError("delivery failed")

        monkeypatch.setattr(assistant_module, "_generate_response", generate_response)
        monkeypatch.setattr(assistant_module, "send_typing_action", do_nothing)
        monkeypatch.setattr(assistant_module, "send_message", fail_delivery)

        await assistant_module._run_admitted_turn(
            telegram_user_id=1,
            user_runtime=cast(
                UserRuntime,
                SimpleNamespace(telegram_chat_id=2),
            ),
            coordinator=cast(MessageCoordinator, coordinator),
            tools=cast(ToolsInjector, object()),
            settings=cast(
                ApiSettings,
                SimpleNamespace(TELEGRAM_BOT_TOKEN="token"),
            ),
        )

        assert not harle.saved
        assert coordinator.finished_failed

    asyncio.run(verify())
