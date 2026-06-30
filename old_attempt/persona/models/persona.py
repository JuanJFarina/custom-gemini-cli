from pydantic import BaseModel

from typing import Any


class Persona(BaseModel):
    previous_experiences_manager: Any
    previous_thoughts_manager: Any
    traits: Traits
