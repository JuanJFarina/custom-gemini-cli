from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.genai import types
from pydantic import ValidationError

from custom_gemini_cli.config import DEFAULT_MODEL
from custom_gemini_cli.gemini import (
    create_client,
    extract_response_text,
    generate_grounded_content,
    is_unavailable_model_error,
)
from custom_gemini_cli.memory import PERSONAL_HISTORY_PATH
from custom_gemini_cli.prompts.system import SYSTEM_PROMPT
from custom_gemini_cli.reasoning import (
    HarleReasoning,
    json_repair_prompt,
    parse_harle_reasoning,
    reasoning_protocol_text,
    tool_result_prompt,
)
from custom_gemini_cli.runtime_context import (
    get_current_time_and_date,
    get_current_weather,
)
from custom_gemini_cli.stores.protocol import ConversationStore
from custom_gemini_cli.tools.expenses import ExpenseTool


@dataclass
class Harle:
    model: str
    api_key: str
    conversation_store: ConversationStore
    expense_tool: ExpenseTool | None = None
    max_tool_depth: int = 3
    max_json_repair_attempts: int = 2
    last_response: Any | None = field(default=None, init=False)
    effective_model: str = field(default="", init=False)
    _tool_was_called: bool = field(default=False, init=False)

    def respond(self, message: str) -> str:
        history = self._load_conversations()
        system_instruction = self._build_system_instruction(history)
        client = create_client(api_key=self.api_key)
        self._tool_was_called = False
        self.effective_model = self.model

        try:
            response_text = self.reason(
                prompt=message,
                client=client,
                model=self.model,
                system_instruction=system_instruction,
            )
        except Exception as exc:
            if (
                self.model != DEFAULT_MODEL
                and not self._tool_was_called
                and is_unavailable_model_error(exc)
            ):
                response_text = self.reason(
                    prompt=message,
                    client=client,
                    model=DEFAULT_MODEL,
                    system_instruction=system_instruction,
                )
                self.effective_model = DEFAULT_MODEL
            else:
                raise
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

        self.conversation_store.save_conversation(
            prompt=message,
            response_text=response_text,
            model=self.effective_model or self.model,
        )
        return response_text

    def reason(
        self,
        prompt: str,
        *,
        client: Any,
        model: str,
        system_instruction: str,
        contents: list[types.Content] | None = None,
        depth: int = 0,
    ) -> str:
        conversation = contents or [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )
        ]
        response = generate_grounded_content(
            client=client,
            model=model,
            contents=conversation,
            system_instruction=system_instruction,
        )
        self.last_response = response

        response_text = extract_response_text(response)
        if self.expense_tool is None:
            return response_text

        reasoning = self._parse_or_repair_reasoning(
            client=client,
            model=model,
            system_instruction=system_instruction,
            original_prompt=prompt,
            response_text=response_text,
        )
        if reasoning.action == "respond":
            return reasoning.response or ""

        if depth >= self.max_tool_depth:
            return "I could not complete the request because the tool loop reached its limit."

        tool_result = self._execute_reasoning_tool(reasoning)
        self._tool_was_called = True

        return self.reason(
            prompt=prompt,
            client=client,
            model=model,
            system_instruction=system_instruction,
            contents=[
                *conversation,
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=response_text)],
                ),
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=tool_result_prompt(
                                original_prompt=prompt,
                                tool_result=tool_result,
                            )
                        )
                    ],
                ),
            ],
            depth=depth + 1,
        )

    def _parse_or_repair_reasoning(
        self,
        *,
        client: Any,
        model: str,
        system_instruction: str,
        original_prompt: str,
        response_text: str,
    ) -> HarleReasoning:
        try:
            return parse_harle_reasoning(response_text)
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)

        for _ in range(self.max_json_repair_attempts):
            repair_response = generate_grounded_content(
                client=client,
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=original_prompt)],
                    ),
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=response_text)],
                    ),
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=json_repair_prompt(
                                    invalid_response=response_text,
                                    error=last_error,
                                )
                            )
                        ],
                    ),
                ],
                system_instruction=system_instruction,
            )
            self.last_response = repair_response
            response_text = extract_response_text(repair_response)
            try:
                return parse_harle_reasoning(response_text)
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)

        return HarleReasoning(
            action="respond",
            response=(
                "I could not parse my internal JSON response. Please try again."
            ),
        )

    def _execute_reasoning_tool(self, reasoning: HarleReasoning) -> dict[str, Any]:
        if reasoning.tool_name == "add_non_credit_expense" and reasoning.tool_args:
            return self._update_expenses_tool(reasoning.tool_args.model_dump())

        return {
            "ok": False,
            "error": f"Unknown or incomplete tool request: {reasoning.tool_name}",
        }

    def _update_expenses_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.expense_tool is None:
            return {
                "ok": False,
                "error": "Expense tool is not configured.",
            }
        return self.expense_tool.add_non_credit_expense(args)

    def _load_conversations(self) -> str:
        return self.conversation_store.load_conversations()

    def _build_system_instruction(self, latest_conversations: str) -> str:
        system_instruction = SYSTEM_PROMPT.format(
            current_time_and_date=get_current_time_and_date(),
            current_weather=get_current_weather(),
            juan_personal_history_summary=_load_personal_history(PERSONAL_HISTORY_PATH),
            latest_conversations=latest_conversations,
        )
        if self.expense_tool is not None:
            system_instruction = f"{system_instruction}\n\n{reasoning_protocol_text()}"
        return system_instruction

    def _gemini_tools(self) -> list[types.Tool]:
        return [
            types.Tool(
                google_search=types.GoogleSearch(),
            )
        ]


def _load_personal_history(path: Path) -> str:
    if not path.is_file():
        return "No personal history has been recorded yet."

    content = path.read_text(encoding="utf-8").strip()
    return content or "No personal history has been recorded yet."


