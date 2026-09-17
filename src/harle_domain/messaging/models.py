from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import NAMESPACE_URL, UUID, uuid5


class MediaKind(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"

    @property
    def prompt_label(self) -> str:
        return {
            MediaKind.IMAGE: "Imagen adjunta",
            MediaKind.AUDIO: "Audio adjunto",
        }[self]


@dataclass(frozen=True, slots=True)
class TelegramMediaReference:
    update_id: int
    file_id: str
    file_unique_id: str
    kind: MediaKind
    mime_type: str
    file_size: int | None = None
    file_name: str | None = None

    def __post_init__(self) -> None:
        if self.update_id < 0:
            raise ValueError("Telegram update identifier cannot be negative.")
        if not all((self.file_id.strip(), self.file_unique_id.strip())):
            raise ValueError("Telegram media identifiers cannot be empty.")
        if not self.mime_type.strip():
            raise ValueError("Telegram media MIME type cannot be empty.")
        if self.file_size is not None and self.file_size <= 0:
            raise ValueError("Telegram media file size must be positive.")

    @property
    def attachment_id(self) -> UUID:
        return uuid5(NAMESPACE_URL, f"harle:telegram-media:{self.update_id}")

    @property
    def prompt_marker(self) -> str:
        details = ": ".join(filter(None, (self.kind.prompt_label, self.file_name)))
        return f"[{details}]"


@dataclass(frozen=True, slots=True)
class RecentMedia:
    user_id: UUID
    reference: TelegramMediaReference
    stored_at: datetime

    @property
    def attachment_id(self) -> UUID:
        return self.reference.attachment_id


@dataclass(frozen=True, slots=True)
class MediaContent:
    reference: TelegramMediaReference
    data: bytes
