from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from harle_services.accounts import (
    TelegramLinkView,
    WebSessionResult,
)


class TelegramLinkStatusPayload(BaseModel):
    state: str
    expires_at: datetime | None = None


class SessionPayload(BaseModel):
    user_id: UUID
    display_name: str
    plan_code: str
    subscription_period_starts_at: datetime
    subscription_period_ends_at: datetime
    telegram_link: TelegramLinkStatusPayload
    csrf_token: str
    session_expires_at: datetime

    @classmethod
    def from_view(cls, view: WebSessionResult) -> "SessionPayload":
        account = view.account
        return cls(
            user_id=account.user_id,
            display_name=account.display_name,
            plan_code=account.plan_code,
            subscription_period_starts_at=account.subscription_period.starts_at,
            subscription_period_ends_at=account.subscription_period.ends_at,
            telegram_link=TelegramLinkStatusPayload(
                state=view.telegram_link.state.value,
                expires_at=view.telegram_link.expires_at,
            ),
            csrf_token=view.csrf_token,
            session_expires_at=view.session_expires_at,
        )


class TelegramLinkPayload(BaseModel):
    state: str
    url: str | None = None
    expires_at: datetime | None = None

    @classmethod
    def from_view(cls, view: TelegramLinkView) -> "TelegramLinkPayload":
        return cls(
            state=view.state,
            url=view.url,
            expires_at=view.expires_at,
        )
