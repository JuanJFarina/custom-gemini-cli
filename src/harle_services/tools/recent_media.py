from collections.abc import Mapping
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from harle_domain.messaging import RecentMediaStore, TelegramMediaDownloader
from harle_domain.tools import (
    ToolCallResult,
    ToolDefinition,
    ToolEffect,
    ToolExecutionContext,
    ToolFamily,
    ToolHandler,
)

from .registry import ToolFamilyRegistration

FAMILY = ToolFamily.RECENT_MEDIA


class LoadRecentMediaArgs(BaseModel):
    attachment_id: UUID

    model_config = ConfigDict(extra="forbid")


INSTRUCTIONS = """For recent Telegram media:
- Recent attachment metadata appears separately in your context.
- Call load_recent_media only when an earlier attachment is needed for the current request.
- The selected image or audio becomes available in your next reasoning step."""

DEFINITION = ToolDefinition(
    name="load_recent_media",
    family=FAMILY,
    description="Load one recent Telegram image or audio attachment by internal UUID.",
    argument_model=LoadRecentMediaArgs,
    effect=ToolEffect.READ,
    can_run_concurrently=True,
)


def create_recent_media_registration(
    store: RecentMediaStore,
    downloader: TelegramMediaDownloader,
) -> ToolFamilyRegistration:
    def build_handlers(
        context: ToolExecutionContext,
    ) -> Mapping[str, ToolHandler]:
        async def load_recent_media(args: BaseModel) -> ToolCallResult:
            context.require_family(FAMILY)
            validated = cast(LoadRecentMediaArgs, args)
            recent = store.get(
                user_id=context.user_id,
                attachment_id=validated.attachment_id,
            )
            if recent is None:
                return ToolCallResult(
                    called_tool_name="load_recent_media",
                    result={
                        "ok": False,
                        "reason": "Recent attachment was not found or expired.",
                    },
                )
            media = await downloader.download(recent.reference)
            return ToolCallResult(
                called_tool_name="load_recent_media",
                result={
                    "ok": True,
                    "attachment_id": str(recent.attachment_id),
                    "kind": recent.reference.kind.value,
                    "file_name": recent.reference.file_name,
                },
                media=media,
            )

        return {"load_recent_media": load_recent_media}

    return ToolFamilyRegistration(
        family=FAMILY,
        instructions=INSTRUCTIONS,
        definitions=(DEFINITION,),
        handler_factory=build_handlers,
    )
