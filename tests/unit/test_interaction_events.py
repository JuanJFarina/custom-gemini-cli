from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

import pytest

from harle_domain.events import (
    EventStatus,
    InteractionEvent,
    InteractionEventRepository,
)
from harle_domain.profiles import InteractionFrequency
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


def test_interaction_frequency_maps_to_probability_scales() -> None:
    assert InteractionFrequency.HIGH.scale == timedelta(hours=12)
    assert InteractionFrequency.MEDIUM.scale == timedelta(hours=24)
    assert InteractionFrequency.LOW.scale == timedelta(hours=48)


@pytest.mark.parametrize("frequency", list(InteractionFrequency))
def test_probability_reaches_sixty_three_percent_at_scale(
    frequency: InteractionFrequency,
) -> None:
    interval = timedelta(minutes=5)
    survival = 1.0
    elapsed = timedelta(0)
    checks = int(frequency.scale / interval)
    for _ in range(checks):
        survival *= 1 - interaction_probability(
            elapsed=elapsed,
            scheduler_interval=interval,
            scale=frequency.scale,
        )
        elapsed += interval

    assert 1 - survival == pytest.approx(0.6321, abs=0.0001)


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
        scale=InteractionFrequency.HIGH.scale,
    )
    assert not service.should_trigger(
        _event(last_user_message_at=NOW - timedelta(days=7, seconds=1)),
        scheduler_interval=timedelta(minutes=5),
        scale=InteractionFrequency.HIGH.scale,
    )
