from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from harle_domain.messaging import TelegramMediaReference
from harle_services.access import TemporaryBan


class MessageSubmissionStatus(str, Enum):
    STARTED = "started"
    JOINED = "joined"
    QUEUED = "queued"
    DUPLICATE = "duplicate"
    DELIVERED = "delivered"
    RATE_LIMITED = "rate_limited"
    INTERRUPTED = "interrupted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class MessageSubmission:
    status: MessageSubmissionStatus
    temporary_ban: TemporaryBan | None = None

    def __post_init__(self) -> None:
        is_rate_limited = self.status is MessageSubmissionStatus.RATE_LIMITED
        if is_rate_limited != (self.temporary_ban is not None):
            raise ValueError("Rate-limited submissions require temporary ban details.")

    @property
    def accepted(self) -> bool:
        return self.status in {
            MessageSubmissionStatus.STARTED,
            MessageSubmissionStatus.JOINED,
            MessageSubmissionStatus.QUEUED,
        }

    @property
    def starts_processing(self) -> bool:
        return self.status is MessageSubmissionStatus.STARTED


@dataclass(frozen=True, slots=True)
class MessageFragment:
    update_id: int
    telegram_user_id: int
    telegram_chat_id: int
    text: str
    media: TelegramMediaReference | None = None


@dataclass(frozen=True, slots=True)
class MessageTurn:
    telegram_user_id: int
    telegram_chat_id: int
    messages: Sequence[MessageFragment]
    generation: int

    @property
    def update_ids(self) -> tuple[int, ...]:
        return tuple(message.update_id for message in self.messages)

    @property
    def prompt(self) -> str:
        if len(self.messages) == 1:
            return self.messages[0].text
        return "\n\n".join(
            f"[Message {index}]\n{message.text}"
            for index, message in enumerate(self.messages, start=1)
        )

    @property
    def media(self) -> Sequence[TelegramMediaReference]:
        return tuple(
            message.media for message in self.messages if message.media is not None
        )
