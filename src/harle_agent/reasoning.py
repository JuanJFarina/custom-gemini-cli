from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from harle_agent.tools.expenses import (
    CATEGORY_COLUMNS,
    CATEGORY_GUIDANCE,
    MONTH_SHEET_NAMES,
)


class HarleThought(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["respond", "call_tool"]
    tool_name: Literal["add_non_credit_expense"] | None = None
    tool_args: dict[str, Any] | None = None
    response: str | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> HarleThought:
        if self.action == "respond":
            if not self.response or not self.response.strip():
                raise ValueError("response is required when action is respond.")
            if self.tool_name is not None or self.tool_args is not None:
                raise ValueError("tool fields must be empty when action is respond.")
            return self

        if self.tool_name is None or self.tool_args is None:
            raise ValueError("tool_name and tool_args are required for call_tool.")
        if self.response is not None:
            raise ValueError("response must be empty when action is call_tool.")
        return self


def reasoning_protocol_text() -> str:
    categories = ", ".join(CATEGORY_COLUMNS)
    months = ", ".join(MONTH_SHEET_NAMES)
    return f"""
Internal response protocol:
- You must return exactly one valid JSON object and no markdown.
- Do not wrap the JSON in code fences.
- Use this protocol only for this assistant response; Juan must never see it.

Allowed JSON object for a normal answer:
{{
  "action": "respond",
  "response": "Your natural response to Juan"
}}

Allowed JSON object for a non-credit expense or refund update:
{{
  "action": "call_tool",
  "tool_name": "add_non_credit_expense",
  "tool_args": {{
    "amount": 100,
    "category": "hogar",
    "day": null,
    "month": null,
    "refund": false
  }}
}}

Tool rules:
- For ordinary questions or any request that does not require an expense update, use action "respond".
- Only call add_non_credit_expense for one-time non-credit expenses or refunds.
- If the expense request is ambiguous, appears duplicate, or involves credit/installments, respond with a clarifying question instead of calling the tool.
- Expense amount must be a positive integer in Argentine pesos.
- Valid categories: {categories}.
- Valid month values: {months}.
- day and month may be null; the tool will default them to the current Rosario date.
- refund must be true only for refunds or negative adjustments; otherwise false.

Category inference guidance:
{CATEGORY_GUIDANCE}
"""
