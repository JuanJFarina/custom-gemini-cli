from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from harle_agent.settings import get_agent_settings
from harle_domain.conversations.ports import ConversationStore
from harle_domain.tools.models import (
    HarleToolStore,
    InternalToolCallInteraction,
    ToolCallAction,
)


class HarleConfig(BaseModel):
    model: str = get_agent_settings().GEMINI_MODEL
    api_key: str = get_agent_settings().GEMINI_API_KEY


class HarlePersonalContext(BaseModel):
    user_name: str = Field(min_length=1)
    preferred_name: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    timezone: str = Field(min_length=1)
    assistant_profile: str = Field(min_length=1)
    personal_history: str = Field(min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        allow_inf_nan=False,
    )

    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown IANA timezone: {value}") from exc
        return value

    @model_validator(mode="after")
    def validate_location(self) -> "HarlePersonalContext":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be supplied together.")
        return self


class HarleResponse(BaseModel):
    action: Literal["respond"]
    response: str


HarleThought = Annotated[
    HarleResponse | ToolCallAction,
    Field(discriminator="action"),
]

HarleThoughtAdapter: TypeAdapter[HarleThought] = TypeAdapter(HarleThought)


class HarleStores(BaseModel):
    conversation_store: ConversationStore
    tool_store: HarleToolStore

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class HarleRunResult(BaseModel):
    response_text: str
    tool_interactions: list[InternalToolCallInteraction] = Field(
        default_factory=list,
    )
