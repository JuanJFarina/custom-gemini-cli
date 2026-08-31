import asyncio
from uuid import uuid4

from harle_services.messaging import UserWorkCoordinator


def test_coordinator_serializes_work_for_one_user() -> None:
    async def verify() -> None:
        coordinator = UserWorkCoordinator()
        user_id = uuid4()
        first_entered = asyncio.Event()
        second_attempted = asyncio.Event()
        second_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def first() -> None:
            async with coordinator.serialize(user_id):
                first_entered.set()
                await release_first.wait()

        async def second() -> None:
            second_attempted.set()
            async with coordinator.serialize(user_id):
                second_entered.set()

        first_task = asyncio.create_task(first())
        await first_entered.wait()
        second_task = asyncio.create_task(second())
        await second_attempted.wait()
        await asyncio.sleep(0)

        assert not second_entered.is_set()
        release_first.set()
        await asyncio.gather(first_task, second_task)
        assert second_entered.is_set()

    asyncio.run(verify())


def test_coordinator_keeps_different_users_independent() -> None:
    async def verify() -> None:
        coordinator = UserWorkCoordinator()
        first_entered = asyncio.Event()
        second_entered = asyncio.Event()

        async def run_for_user(
            own_event: asyncio.Event,
            other_event: asyncio.Event,
        ) -> None:
            async with coordinator.serialize(uuid4()):
                own_event.set()
                await other_event.wait()

        await asyncio.wait_for(
            asyncio.gather(
                run_for_user(first_entered, second_entered),
                run_for_user(second_entered, first_entered),
            ),
            timeout=1,
        )

    asyncio.run(verify())
