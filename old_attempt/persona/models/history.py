from pydantic import BaseModel
from uuid import UUID


class Event(BaseModel):
    id: UUID
    year: int | tuple[int, int]
    month: str | tuple[str, str] | None
    day: int | tuple[int, int] | None

    event: str


class History(BaseModel):
    personal_history: list[Event]

    def add_event(event: Event) -> None:
        ...

    def get_event(id: UUID) -> Event:
        ...

    def search_event(query: str) -> Event:
        ...

    def update_event(event: Event) -> None:
        ...
