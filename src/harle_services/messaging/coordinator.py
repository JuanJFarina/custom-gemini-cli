from asyncio import CancelledError, Lock, Task
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field

from harle_domain.messaging import (
    TelegramUpdateRepository,
    TelegramUpdateState,
)
from harle_services.access import TemporaryBan

from .models import (
    MessageFragment,
    MessageSubmission,
    MessageSubmissionStatus,
    MessageTurn,
)

TERMINAL_SUBMISSIONS: Mapping[TelegramUpdateState, MessageSubmissionStatus] = {
    TelegramUpdateState.DELIVERED: MessageSubmissionStatus.DELIVERED,
    TelegramUpdateState.RATE_LIMITED: MessageSubmissionStatus.DUPLICATE,
    TelegramUpdateState.REJECTED: MessageSubmissionStatus.DUPLICATE,
    TelegramUpdateState.TOOL_STARTED: MessageSubmissionStatus.INTERRUPTED,
    TelegramUpdateState.DELIVERING: MessageSubmissionStatus.INTERRUPTED,
    TelegramUpdateState.INTERRUPTED: MessageSubmissionStatus.INTERRUPTED,
}


@dataclass(slots=True)
class _ActiveTurn:
    messages: list[MessageFragment]
    generation: int = 0
    tool_started: bool = False
    sealed: bool = False
    reasoning_task: Task[object] | None = None


@dataclass(slots=True)
class _UserMessages:
    lock: Lock = field(default_factory=Lock)
    active: _ActiveTurn | None = None
    queued: list[MessageFragment] = field(default_factory=list)


class MessageCoordinator:
    def __init__(
        self,
        repository: TelegramUpdateRepository,
        rate_limiter: Callable[[int], TemporaryBan | None],
    ) -> None:
        self._repository = repository
        self._rate_limiter = rate_limiter
        self._entries_lock = Lock()
        self._entries: MutableMapping[int, _UserMessages] = {}

    async def receive(
        self,
        message: MessageFragment,
    ) -> MessageSubmission:
        update_id = message.update_id
        telegram_user_id = message.telegram_user_id
        entry = await self._entry(telegram_user_id)
        task_to_cancel: Task[object] | None = None
        async with entry.lock:
            receipt = await self._repository.receive(
                update_id=update_id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=message.telegram_chat_id,
                message_text=message.text,
            )
            terminal_submission = _terminal_submission(receipt.state)
            if terminal_submission is not None:
                return terminal_submission
            if _contains_update(entry, update_id):
                return MessageSubmission(MessageSubmissionStatus.DUPLICATE)
            if receipt.newly_persisted:
                temporary_ban = self._rate_limiter(telegram_user_id)
                if temporary_ban is not None:
                    await self._repository.mark_rate_limited([update_id])
                    return MessageSubmission(
                        MessageSubmissionStatus.RATE_LIMITED,
                        temporary_ban,
                    )
            if entry.active is None:
                entry.active = _ActiveTurn(messages=[message])
                status = MessageSubmissionStatus.STARTED
            elif entry.active.tool_started or entry.active.sealed:
                entry.queued.append(message)
                status = MessageSubmissionStatus.QUEUED
            else:
                entry.active.messages.append(message)
                entry.active.generation += 1
                task_to_cancel = entry.active.reasoning_task
                status = MessageSubmissionStatus.JOINED

        if task_to_cancel is not None:
            task_to_cancel.cancel()
        return MessageSubmission(status)

    async def reject(
        self,
        *,
        update_id: int,
        telegram_user_id: int,
        telegram_chat_id: int,
        text: str,
    ) -> MessageSubmission:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            receipt = await self._repository.receive(
                update_id=update_id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                message_text=text,
            )
            if receipt.state in {
                TelegramUpdateState.REJECTED,
                TelegramUpdateState.DELIVERED,
                TelegramUpdateState.RATE_LIMITED,
                TelegramUpdateState.INTERRUPTED,
            }:
                return MessageSubmission(MessageSubmissionStatus.DUPLICATE)
            if receipt.newly_persisted:
                temporary_ban = self._rate_limiter(telegram_user_id)
                if temporary_ban is not None:
                    await self._repository.mark_rate_limited([update_id])
                    return MessageSubmission(
                        MessageSubmissionStatus.RATE_LIMITED,
                        temporary_ban,
                    )
            await self._repository.mark_rejected([update_id])
            return MessageSubmission(MessageSubmissionStatus.REJECTED)

    async def current_turn(self, telegram_user_id: int) -> MessageTurn | None:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            if active is None:
                return None
            turn = _snapshot(telegram_user_id, active)
        await self._repository.mark_processing(turn.update_ids)
        return turn

    async def bind_reasoning_task(
        self,
        *,
        telegram_user_id: int,
        generation: int,
        task: Task[object],
    ) -> None:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            if (
                active is None
                or active.generation != generation
                or active.tool_started
                or active.sealed
            ):
                task.cancel()
                return
            active.reasoning_task = task

    async def reasoning_finished(
        self,
        *,
        telegram_user_id: int,
        task: Task[object],
    ) -> None:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            if active is not None and active.reasoning_task is task:
                active.reasoning_task = None

    async def should_restart(
        self,
        *,
        telegram_user_id: int,
        generation: int,
    ) -> bool:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            return (
                active is not None
                and not active.tool_started
                and not active.sealed
                and active.generation != generation
            )

    async def mark_tool_started(
        self,
        *,
        telegram_user_id: int,
        generation: int,
    ) -> None:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            if active is None or active.generation != generation or active.sealed:
                raise CancelledError
            active.tool_started = True
            update_ids = tuple(message.update_id for message in active.messages)
        await self._repository.mark_tool_started(update_ids)

    async def begin_delivery(
        self,
        *,
        telegram_user_id: int,
        generation: int,
    ) -> bool:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            if active is None or active.generation != generation:
                return False
            active.sealed = True
            update_ids = tuple(message.update_id for message in active.messages)
        await self._repository.mark_delivering(update_ids)
        return True

    async def finish_delivered(
        self,
        *,
        telegram_user_id: int,
        update_ids: Sequence[int],
    ) -> bool:
        return await self._finish(
            telegram_user_id=telegram_user_id,
            update_ids=update_ids,
        )

    async def finish_failed(
        self,
        *,
        telegram_user_id: int,
        retryable: bool,
    ) -> bool:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            if active is None:
                return bool(entry.queued)
            update_ids = tuple(message.update_id for message in active.messages)
            unsafe = active.tool_started or not retryable
            _advance(entry)
            has_next = entry.active is not None
        if unsafe:
            await self._repository.mark_interrupted(update_ids)
        else:
            await self._repository.mark_failed(update_ids)
        return has_next

    async def _finish(
        self,
        *,
        telegram_user_id: int,
        update_ids: Sequence[int],
    ) -> bool:
        entry = await self._entry(telegram_user_id)
        async with entry.lock:
            active = entry.active
            if active is None:
                return bool(entry.queued)
            active_ids = tuple(message.update_id for message in active.messages)
            if tuple(update_ids) != active_ids:
                raise ValueError("Delivered update identifiers do not match the turn.")
            _advance(entry)
            return entry.active is not None

    async def _entry(self, telegram_user_id: int) -> _UserMessages:
        async with self._entries_lock:
            return self._entries.setdefault(telegram_user_id, _UserMessages())


def _contains_update(entry: _UserMessages, update_id: int) -> bool:
    messages = [
        *(entry.active.messages if entry.active is not None else ()),
        *entry.queued,
    ]
    return any(message.update_id == update_id for message in messages)


def _terminal_submission(
    state: TelegramUpdateState,
) -> MessageSubmission | None:
    status = TERMINAL_SUBMISSIONS.get(state)
    return MessageSubmission(status) if status is not None else None


def _snapshot(telegram_user_id: int, active: _ActiveTurn) -> MessageTurn:
    first = active.messages[0]
    if any(
        message.telegram_chat_id != first.telegram_chat_id
        for message in active.messages
    ):
        raise ValueError("A combined Telegram turn must use one chat.")
    return MessageTurn(
        telegram_user_id=telegram_user_id,
        telegram_chat_id=first.telegram_chat_id,
        messages=tuple(active.messages),
        generation=active.generation,
    )


def _advance(entry: _UserMessages) -> None:
    entry.active = _ActiveTurn(messages=list(entry.queued)) if entry.queued else None
    entry.queued.clear()
