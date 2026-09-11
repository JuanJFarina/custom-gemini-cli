import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import cast

from harle_domain.messaging import TelegramUpdateReceipt, TelegramUpdateState
from harle_services.access import TemporaryBan
from harle_services.messaging import (
    MessageCoordinator,
    MessageSubmissionStatus,
)


class FakeTelegramUpdates:
    def __init__(self) -> None:
        self.states: dict[int, TelegramUpdateState] = {}

    async def receive(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
        message_text: str,
    ) -> TelegramUpdateReceipt:
        del telegram_user_id, telegram_chat_id, message_text
        newly_persisted = update_id not in self.states
        state = self.states.setdefault(update_id, TelegramUpdateState.RECEIVED)
        return TelegramUpdateReceipt(state, newly_persisted)

    async def mark_processing(self, update_ids: Sequence[int]) -> None:
        self._mark(update_ids, TelegramUpdateState.PROCESSING)

    async def mark_tool_started(self, update_ids: Sequence[int]) -> None:
        self._mark(update_ids, TelegramUpdateState.TOOL_STARTED)

    async def mark_delivering(self, update_ids: Sequence[int]) -> None:
        self._mark(update_ids, TelegramUpdateState.DELIVERING)

    async def mark_failed(self, update_ids: Sequence[int]) -> None:
        self._mark(update_ids, TelegramUpdateState.FAILED)

    async def mark_rate_limited(self, update_ids: Sequence[int]) -> None:
        self._mark(update_ids, TelegramUpdateState.RATE_LIMITED)

    async def mark_interrupted(self, update_ids: Sequence[int]) -> None:
        self._mark(update_ids, TelegramUpdateState.INTERRUPTED)

    def _mark(
        self,
        update_ids: Sequence[int],
        state: TelegramUpdateState,
    ) -> None:
        for update_id in update_ids:
            self.states[update_id] = state


async def _wait_forever() -> object:
    await asyncio.Event().wait()
    return object()


def test_coordinator_deduplicates_active_and_delivered_updates() -> None:
    async def verify() -> None:
        updates = FakeTelegramUpdates()
        checked_identities: list[int] = []

        def rate_limit(telegram_user_id: int) -> TemporaryBan | None:
            checked_identities.append(telegram_user_id)
            if len(checked_identities) == 2:
                return TemporaryBan(
                    blocked_until=datetime.now(timezone.utc) + timedelta(minutes=1),
                    notify_user=True,
                )
            return None

        coordinator = MessageCoordinator(updates, rate_limit)

        first = await coordinator.receive(
            update_id=1,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Hello",
        )
        active_duplicate = await coordinator.receive(
            update_id=1,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Hello",
        )
        updates.states[2] = TelegramUpdateState.DELIVERED
        delivered_duplicate = await coordinator.receive(
            update_id=2,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Done",
        )
        limited = await coordinator.receive(
            update_id=3,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Too fast",
        )
        limited_duplicate = await coordinator.receive(
            update_id=3,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Too fast",
        )

        assert first.status is MessageSubmissionStatus.STARTED
        assert active_duplicate.status is MessageSubmissionStatus.DUPLICATE
        assert delivered_duplicate.status is MessageSubmissionStatus.DELIVERED
        assert limited.status is MessageSubmissionStatus.RATE_LIMITED
        assert limited_duplicate.status is MessageSubmissionStatus.DUPLICATE
        assert checked_identities == [10, 10]

    asyncio.run(verify())


def test_coordinator_joins_ordered_messages_and_cancels_pre_tool_reasoning() -> None:
    async def verify() -> None:
        coordinator = MessageCoordinator(FakeTelegramUpdates(), lambda _: None)
        await coordinator.receive(
            update_id=1,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="First",
        )
        turn = await coordinator.current_turn(10)
        assert turn is not None
        task = asyncio.create_task(_wait_forever())
        await coordinator.bind_reasoning_task(
            telegram_user_id=10,
            generation=turn.generation,
            task=cast(asyncio.Task[object], task),
        )

        joined = await coordinator.receive(
            update_id=2,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Second",
        )
        await asyncio.sleep(0)
        restarted = await coordinator.current_turn(10)

        assert joined.status is MessageSubmissionStatus.JOINED
        assert task.cancelled()
        assert restarted is not None
        assert restarted.update_ids == (1, 2)
        assert restarted.prompt == "[Message 1]\nFirst\n\n[Message 2]\nSecond"

    asyncio.run(verify())


def test_coordinator_queues_messages_after_tool_execution_starts() -> None:
    async def verify() -> None:
        coordinator = MessageCoordinator(FakeTelegramUpdates(), lambda _: None)
        await coordinator.receive(
            update_id=1,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Create an event",
        )
        turn = await coordinator.current_turn(10)
        assert turn is not None
        await coordinator.mark_tool_started(
            telegram_user_id=10,
            generation=turn.generation,
        )

        queued = await coordinator.receive(
            update_id=2,
            telegram_user_id=10,
            telegram_chat_id=20,
            text="Also add lunch",
        )
        has_next = await coordinator.finish_delivered(
            telegram_user_id=10,
            update_ids=turn.update_ids,
        )
        next_turn = await coordinator.current_turn(10)

        assert queued.status is MessageSubmissionStatus.QUEUED
        assert has_next
        assert next_turn is not None
        assert next_turn.update_ids == (2,)

    asyncio.run(verify())
