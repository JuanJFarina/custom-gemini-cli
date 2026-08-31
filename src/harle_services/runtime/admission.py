from dataclasses import dataclass
from typing import TypeAlias

from harle_services.access import (
    PreflightAccepted,
    PreflightService,
    QuotaExceeded,
    QuotaReservation,
    TemporaryBan,
    UsageQuotaService,
)

from .factory import UserRuntimeFactory
from .models import UserRuntime


@dataclass(frozen=True, slots=True)
class RequestAccepted:
    user_runtime: UserRuntime
    quota_reservation: QuotaReservation


RequestAdmission: TypeAlias = RequestAccepted | TemporaryBan | QuotaExceeded


@dataclass(frozen=True, slots=True)
class RequestAdmissionService:
    preflight: PreflightService
    users: UserRuntimeFactory
    quota: UsageQuotaService

    async def admit(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_update_id: int,
    ) -> RequestAdmission:
        preflight = await self.preflight.check(telegram_user_id)
        if not isinstance(preflight, PreflightAccepted):
            return preflight

        user_runtime: UserRuntime | None = None
        try:
            user_runtime = await self.users.create_for_resolved_user(
                resolved_user=preflight.resolved_user,
                telegram_chat_id=telegram_chat_id,
                telegram_update_id=telegram_update_id,
            )
        finally:
            if user_runtime is None:
                await self.quota.release(preflight.quota_reservation)

        if user_runtime is None:
            raise RuntimeError("User runtime was not created.")
        return RequestAccepted(
            user_runtime=user_runtime,
            quota_reservation=preflight.quota_reservation,
        )
