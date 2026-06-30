from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from custom_gemini_cli.tools.expenses import (
    CATEGORY_COLUMNS,
    CATEGORY_GUIDANCE,
    MONTH_SHEET_NAMES,
)


ExpenseCategory = Literal[
    "alquileres",
    "servicios_esenciales",
    "servicios_no_esenciales",
    "hogar",
    "transporte",
    "salidas",
    "shopping",
    "otros",
]

ExpenseMonth = Literal[
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


class AddExpenseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int
    category: ExpenseCategory
    day: int | None = None
    month: ExpenseMonth | None = None
    refund: bool = False

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, amount: int) -> int:
        if amount <= 0:
            raise ValueError("amount must be a positive integer.")
        return amount


class HarleReasoning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["respond", "call_tool"]
    tool_name: Literal["add_non_credit_expense"] | None = None
    tool_args: AddExpenseArgs | None = None
    response: str | None = None

    @model_validator(mode="after")
    def validate_action_payload(self) -> HarleReasoning:
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


def parse_harle_reasoning(text: str) -> HarleReasoning:
    return HarleReasoning.model_validate_json(_extract_json_object(text))


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


def json_repair_prompt(*, invalid_response: str, error: str) -> str:
    return f"""
Your previous response did not match the required JSON protocol.

Validation error:
{error}

Previous response:
{invalid_response}

Return exactly one valid JSON object and nothing else. Use either:
{{"action":"respond","response":"..."}}
or:
{{"action":"call_tool","tool_name":"add_non_credit_expense","tool_args":{{"amount":100,"category":"hogar","day":null,"month":null,"refund":false}}}}
"""


def tool_result_prompt(*, original_prompt: str, tool_result: dict[str, object]) -> str:
    return f"""
Original user message:
{original_prompt}

The local Python tool was executed and returned this result:
{json.dumps(tool_result, ensure_ascii=False)}

Now respond naturally to Juan using the JSON response protocol. Do not call the tool again unless another tool call is truly required.
"""


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return stripped
    return stripped[start : end + 1]

