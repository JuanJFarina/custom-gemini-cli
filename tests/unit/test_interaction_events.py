from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

import pytest

from harle_domain.events import (
    EventStatus,
    InteractionEvent,
    InteractionEventRepository,
)
from harle_services.events import InteractionEventService, interaction_probability

NOW = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def _event(
    *,
    last_user_message_at: datetime,
    last_agent_message_at: datetime | None = None,
) -> InteractionEvent:
    return InteractionEvent(
        id=uuid4(),
        user_id=uuid4(),
        status=EventStatus.ACTIVE,
        last_user_message_at=last_user_message_at,
        last_agent_message_at=last_agent_message_at,
        created_at=NOW - timedelta(days=30),
        updated_at=NOW,
    )


def test_calm_probability_is_stable_across_five_minute_checks() -> None:
    interval = timedelta(minutes=5)
    survival = 1.0
    elapsed = timedelta(0)
    for _ in range(24 * 12):
        survival *= 1 - interaction_probability(
            elapsed=elapsed,
            scheduler_interval=interval,
        )
        elapsed += interval

    assert 1 - survival == pytest.approx(0.0606, abs=0.0001)


def test_interaction_trigger_uses_latest_contact_and_seven_day_cutoff() -> None:
    service = InteractionEventService(
        cast(InteractionEventRepository, object()),
        clock=lambda: NOW,
        random_value=lambda: 0,
    )

    assert service.should_trigger(
        _event(
            last_user_message_at=NOW - timedelta(days=6),
            last_agent_message_at=NOW - timedelta(days=1),
        ),
        scheduler_interval=timedelta(minutes=5),
    )
    assert not service.should_trigger(
        _event(last_user_message_at=NOW - timedelta(days=7, seconds=1)),
        scheduler_interval=timedelta(minutes=5),
    )
