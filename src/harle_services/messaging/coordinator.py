from asyncio import Lock
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(slots=True)
class _UserWork:
    lock: Lock = field(default_factory=Lock)
    references: int = 0


class UserWorkCoordinator:
    def __init__(self) -> None:
        self._entries_lock = Lock()
        self._entries: MutableMapping[UUID, _UserWork] = {}

    @asynccontextmanager
    async def serialize(self, user_id: UUID) -> AsyncIterator[None]:
        entry = await self._retain(user_id)
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            await self._release(user_id, entry)

    async def _retain(self, user_id: UUID) -> _UserWork:
        async with self._entries_lock:
            entry = self._entries.setdefault(user_id, _UserWork())
            entry.references += 1
            return entry

    async def _release(self, user_id: UUID, entry: _UserWork) -> None:
        async with self._entries_lock:
            entry.references -= 1
            if entry.references == 0:
                self._entries.pop(user_id, None)
