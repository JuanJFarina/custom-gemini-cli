from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationRecord:
    prompt: str
    response: str
    created_at: str
    kind: str
    tool_call_response: object
    tool_result: object
