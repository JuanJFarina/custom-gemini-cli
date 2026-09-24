from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from secrets import token_urlsafe
from typing import Protocol, runtime_checkable
from uuid import UUID

from harle_domain.accounts import (
    TelegramLinkCommandRecord,
    TelegramLinkOutcome,
    TelegramLinkRepository,
    TelegramLinkResult,
    TelegramLinkState,
)
from harle_domain.messaging import (
    OutboundMessenger,
    TelegramUpdateRepository,
    TelegramUpdateState,
)
from harle_utils import (
    Clock,
    MessageDeliveryError,
    TelegramAlreadyLinkedError,
    as_utc,
    log,
    utc_now,
)

from .sessions import hash_token


@dataclass(frozen=True, slots=True)
class TelegramLinkView:
    state: str
    url: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TelegramLinkCommand:
    update_id: int
    telegram_user_id: int
    telegram_chat_id: int
    telegram_display_name: str
    token: str


@runtime_checkable
class TemporaryBanDecision(Protocol):
    blocked_until: datetime
    notify_user: bool


class TelegramLinkCommandDisposition(str, Enum):
    PROCESSED = "account_link"
    DUPLICATE = "duplicate"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True, slots=True)
class TelegramLinkCommandResult:
    disposition: TelegramLinkCommandDisposition
    retry_at: datetime | None = None
    notified: bool = False


@dataclass(frozen=True, slots=True)
class TelegramLinkService:
    repository: TelegramLinkRepository
    bot_username: str
    lifetime: timedelta = timedelta(minutes=10)
    clock: Clock = utc_now

    def __post_init__(self) -> None:
        normalized = self.bot_username.removeprefix("@").strip()
        if not normalized:
            raise ValueError("Telegram bot username cannot be empty.")
        if self.lifetime <= timedelta(0):
            raise ValueError("Telegram link lifetime must be positive.")
        object.__setattr__(self, "bot_username", normalized)

    async def status(self, *, user_id: UUID) -> TelegramLinkView:
        status = await self.repository.get_status(
            user_id=user_id,
            current_time=as_utc(self.clock()),
        )
        return TelegramLinkView(
            state=status.state.value,
            expires_at=status.expires_at,
        )

    async def issue(self, *, user_id: UUID) -> TelegramLinkView:
        current_status = await self.repository.get_status(
            user_id=user_id,
            current_time=as_utc(self.clock()),
        )
        if current_status.state is TelegramLinkState.CONNECTED:
            raise TelegramAlreadyLinkedError
        token = token_urlsafe(32)
        created_at = as_utc(self.clock())
        expires_at = created_at + self.lifetime
        await self.repository.issue(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
            created_at=created_at,
        )
        return TelegramLinkView(
            state=TelegramLinkState.PENDING.value,
            url=f"https://t.me/{self.bot_username}?start={token}",
            expires_at=expires_at,
        )

    async def process_command(
        self,
        *,
        command: TelegramLinkCommand,
    ) -> TelegramLinkResult:
        if not command.token:
            raise ValueError("Telegram link token cannot be empty.")
        return await self.repository.process_command(
            command=TelegramLinkCommandRecord(
                update_id=command.update_id,
                telegram_user_id=command.telegram_user_id,
                telegram_chat_id=command.telegram_chat_id,
                telegram_display_name=command.telegram_display_name,
                token_hash=hash_token(command.token),
                processed_at=as_utc(self.clock()),
            ),
        )


@dataclass(frozen=True, slots=True)
class TelegramLinkCommandService:
    links: TelegramLinkService
    updates: TelegramUpdateRepository
    messenger: OutboundMessenger
    rate_limiter: Callable[[int], object | None]

    async def handle(
        self,
        *,
        command: TelegramLinkCommand,
    ) -> TelegramLinkCommandResult:
        receipt = await self.updates.receive(
            update_id=command.update_id,
            telegram_user_id=command.telegram_user_id,
            telegram_chat_id=command.telegram_chat_id,
            message_text="[Telegram account link]",
        )
        if receipt.state in {
            TelegramUpdateState.DELIVERED,
            TelegramUpdateState.RATE_LIMITED,
            TelegramUpdateState.REJECTED,
            TelegramUpdateState.INTERRUPTED,
        }:
            return TelegramLinkCommandResult(
                TelegramLinkCommandDisposition.DUPLICATE,
            )
        if receipt.newly_persisted:
            temporary_ban = self.rate_limiter(command.telegram_user_id)
            if temporary_ban is not None and not isinstance(
                temporary_ban,
                TemporaryBanDecision,
            ):
                raise TypeError("Unexpected Telegram safety-limit result.")
            if temporary_ban is not None:
                await self.updates.mark_rate_limited([command.update_id])
                if temporary_ban.notify_user:
                    await _send_message_safely(
                        messenger=self.messenger,
                        chat_id=command.telegram_chat_id,
                        text=(
                            "You're sending messages too quickly. Try again after "
                            f"{_utc_boundary(temporary_ban.blocked_until)}."
                        ),
                        operation="Telegram cooldown notice",
                    )
                return TelegramLinkCommandResult(
                    TelegramLinkCommandDisposition.RATE_LIMITED,
                    retry_at=temporary_ban.blocked_until,
                    notified=temporary_ban.notify_user,
                )
        result = await self.links.process_command(command=command)
        if result.outcome is TelegramLinkOutcome.DUPLICATE:
            return TelegramLinkCommandResult(
                TelegramLinkCommandDisposition.DUPLICATE,
            )
        await _send_message_safely(
            messenger=self.messenger,
            chat_id=command.telegram_chat_id,
            text=_link_result_message(result.outcome),
            operation="Telegram account-link result",
        )
        return TelegramLinkCommandResult(TelegramLinkCommandDisposition.PROCESSED)


async def _send_message_safely(
    *,
    messenger: OutboundMessenger,
    chat_id: int,
    text: str,
    operation: str,
) -> None:
    try:
        await messenger.send_message(chat_id=chat_id, text=text)
    except MessageDeliveryError:
        log.warning("%s delivery failed", operation)


def _utc_boundary(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _link_result_message(outcome: TelegramLinkOutcome) -> str:
    if outcome in {
        TelegramLinkOutcome.LINKED,
        TelegramLinkOutcome.ALREADY_LINKED,
    }:
        return "Tu cuenta de Telegram quedó vinculada a Harle."
    if outcome is TelegramLinkOutcome.CONFLICT:
        return "Esta cuenta de Telegram ya está vinculada a otra cuenta."
    return "Este enlace venció o ya fue usado. Generá uno nuevo desde Harle."
