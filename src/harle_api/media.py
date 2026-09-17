from collections.abc import Mapping
from dataclasses import dataclass

from harle_domain.messaging import MediaKind, TelegramMediaReference

MAX_MEDIA_REQUEST_SIZE = 12 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp"},
)
SUPPORTED_AUDIO_TYPES = frozenset(
    {
        "audio/aac",
        "audio/flac",
        "audio/m4a",
        "audio/mp3",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-wav",
    },
)
SUPPORTED_TYPES = {
    MediaKind.IMAGE: SUPPORTED_IMAGE_TYPES,
    MediaKind.AUDIO: SUPPORTED_AUDIO_TYPES,
}
UNSUPPORTED_MEDIA_FIELDS = frozenset(
    {"animation", "sticker", "video", "video_note"},
)


@dataclass(frozen=True)
class RejectedMedia:
    reason: str


UNSUPPORTED_MEDIA_RESULTS = {
    False: None,
    True: RejectedMedia("unsupported_media_type"),
}


@dataclass(frozen=True)
class _MediaCandidate:
    value: Mapping[str, object]
    kind: MediaKind
    mime_type: str


def extract_media(
    update_id: int,
    message: Mapping[str, object],
    maximum_request_size: int,
) -> TelegramMediaReference | RejectedMedia | None:
    candidate = _media_candidate(message)
    if candidate is None or isinstance(candidate, RejectedMedia):
        return candidate
    return _reference(
        update_id=update_id,
        value=candidate.value,
        kind=candidate.kind,
        mime_type=candidate.mime_type,
        maximum_request_size=maximum_request_size,
    )


def _media_candidate(
    message: Mapping[str, object],
) -> _MediaCandidate | RejectedMedia | None:
    photos = message.get("photo")
    if isinstance(photos, list):
        photo = _largest_photo(photos)
        return (
            _MediaCandidate(photo, MediaKind.IMAGE, "image/jpeg")
            if photo is not None
            else RejectedMedia("invalid_image")
        )

    for field, default_mime_type in (("voice", "audio/ogg"), ("audio", "")):
        audio = message.get(field)
        if isinstance(audio, Mapping):
            return _MediaCandidate(
                audio,
                MediaKind.AUDIO,
                _parse_str(audio.get("mime_type")) or default_mime_type,
            )

    document = message.get("document")
    if isinstance(document, Mapping):
        mime_type = _parse_str(document.get("mime_type"))
        return (
            _MediaCandidate(document, MediaKind.IMAGE, mime_type)
            if mime_type in SUPPORTED_IMAGE_TYPES
            else RejectedMedia("unsupported_media_type")
        )
    return UNSUPPORTED_MEDIA_RESULTS[
        bool(UNSUPPORTED_MEDIA_FIELDS.intersection(message))
    ]


def _reference(
    *,
    update_id: int,
    value: Mapping[str, object],
    kind: MediaKind,
    mime_type: str,
    maximum_request_size: int,
) -> TelegramMediaReference | RejectedMedia:
    if mime_type not in SUPPORTED_TYPES[kind]:
        return RejectedMedia("unsupported_media_type")
    file_id = _parse_str(value.get("file_id"))
    file_unique_id = _parse_str(value.get("file_unique_id"))
    if not all((file_id, file_unique_id)):
        return RejectedMedia("invalid_media")
    file_size = _parse_positive_int(value.get("file_size"))
    if (file_size or 0) > maximum_request_size:
        return RejectedMedia("media_too_large")
    return TelegramMediaReference(
        update_id=update_id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        kind=kind,
        mime_type=mime_type,
        file_size=file_size,
        file_name=_file_name(value.get("file_name")),
    )


def _largest_photo(values: list[object]) -> Mapping[str, object] | None:
    photos = [value for value in values if isinstance(value, Mapping)]
    if not photos:
        return None
    return max(
        photos,
        key=lambda photo: (
            _integer_or_zero(photo.get("width")),
            _integer_or_zero(photo.get("height")),
            _integer_or_zero(photo.get("file_size")),
        ),
    )


def _parse_positive_int(value: object) -> int | None:
    parsed = _parse_int(value)
    return parsed if parsed is not None and parsed > 0 else None


def _integer_or_zero(value: object) -> int:
    parsed = _parse_int(value)
    return 0 if parsed is None else parsed


def _file_name(value: object) -> str | None:
    name = _parse_str(value).replace("\\", "/").split("/")[-1]
    return name[:255] or None


def _parse_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _parse_str(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
