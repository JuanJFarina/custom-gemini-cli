from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from harle_domain.messaging import RecentMedia, TelegramMediaReference
from harle_utils import Clock, as_utc, utc_now


@dataclass(slots=True)
class InMemoryRecentMediaStore:
    maximum_per_user: int = 10
    retention: timedelta = timedelta(hours=12)
    clock: Clock = utc_now
    _entries: MutableMapping[UUID, list[RecentMedia]] = field(
        default_factory=dict,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.maximum_per_user <= 0:
            raise ValueError("Recent media limit must be positive.")
        if self.retention <= timedelta(0):
            raise ValueError("Recent media retention must be positive.")

    def add(
        self,
        *,
        user_id: UUID,
        reference: TelegramMediaReference,
    ) -> RecentMedia:
        stored = RecentMedia(
            user_id=user_id,
            reference=reference,
            stored_at=as_utc(self.clock()),
        )
        active = self._active(user_id, stored.stored_at)
        active = [item for item in active if item.attachment_id != stored.attachment_id]
        self._entries[user_id] = [*active, stored][-self.maximum_per_user :]
        return stored

    def list_recent(self, *, user_id: UUID) -> Sequence[RecentMedia]:
        active = self._active(user_id, as_utc(self.clock()))
        self._entries[user_id] = active
        return tuple(reversed(active))

    def get(
        self,
        *,
        user_id: UUID,
        attachment_id: UUID,
    ) -> RecentMedia | None:
        active = self._active(user_id, as_utc(self.clock()))
        self._entries[user_id] = active
        return next(
            (item for item in reversed(active) if item.attachment_id == attachment_id),
            None,
        )

    def _active(self, user_id: UUID, current_time: datetime) -> list[RecentMedia]:
        return [
            item
            for item in self._entries.get(user_id, [])
            if current_time - item.stored_at <= self.retention
        ]
