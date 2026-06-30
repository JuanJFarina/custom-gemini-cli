from pydantic import BaseModel, Field
from typing import Annotated


class Values(BaseModel):
    integrity: Annotated[float, Field(ge=0.0, le=1.0)]
    honesty: Annotated[float, Field(ge=0.0, le=1.0)]
    responsibility: Annotated[float, Field(ge=0.0, le=1.0)]
    compassion: Annotated[float, Field(ge=0.0, le=1.0)]
    loyalty: Annotated[float, Field(ge=0.0, le=1.0)]
    courage: Annotated[float, Field(ge=0.0, le=1.0)]
    discipline: Annotated[float, Field(ge=0.0, le=1.0)]
    curiosity: Annotated[float, Field(ge=0.0, le=1.0)]
    intellectual_honesty: Annotated[float, Field(ge=0.0, le=1.0)]
    excellence: Annotated[float, Field(ge=0.0, le=1.0)]
    autonomy: Annotated[float, Field(ge=0.0, le=1.0)]
    purpose: Annotated[float, Field(ge=0.0, le=1.0)]


class Traits(BaseModel):
    values: Values
    motivations: list[str]
    preferences: list[str]
