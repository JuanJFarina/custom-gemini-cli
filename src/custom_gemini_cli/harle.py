from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.genai import types

from custom_gemini_cli.config import DEFAULT_MODEL
from custom_gemini_cli.gemini import (
    create_client,
    extract_function_calls,
    extract_response_text,
    generate_content_with_tools,
    get_first_candidate_content,
    is_unavailable_model_error,
)
from custom_gemini_cli.memory import PERSONAL_HISTORY_PATH
from custom_gemini_cli.prompts.system import SYSTEM_PROMPT
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
        response = generate_content_with_tools(
            client=client,
            model=model,
            contents=conversation,
            system_instruction=system_instruction,
            tools=self._gemini_tools(),
        )
        self.last_response = response

        function_calls = extract_function_calls(response)
        if not function_calls:
            return extract_response_text(response)

        if depth >= self.max_tool_depth:
            return "I could not complete the request because the tool loop reached its limit."

        function_call = function_calls[0]
        tool_result = self._execute_function_call(function_call)
        self._tool_was_called = True

        model_content = get_first_candidate_content(response)
        if model_content is None:
            return "I could not complete the request because Gemini returned an invalid tool call."

        conversation = [
            *conversation,
            model_content,
            types.Content(
                role="tool",
                parts=[
                    types.Part.from_function_response(
                        name=_get_function_call_name(function_call),
                        response=tool_result,
                    )
                ],
            ),
        ]
        return self.reason(
            prompt=prompt,
            client=client,
            model=model,
            system_instruction=system_instruction,
            contents=conversation,
            depth=depth + 1,
        )

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
        return SYSTEM_PROMPT.format(
            current_time_and_date=get_current_time_and_date(),
            current_weather=get_current_weather(),
            juan_personal_history_summary=_load_personal_history(PERSONAL_HISTORY_PATH),
            latest_conversations=latest_conversations,
        )

    def _gemini_tools(self) -> list[types.Tool]:
        tools = [
            types.Tool(
                google_search=types.GoogleSearch(),
            )
        ]
        if self.expense_tool is not None:
            tools.append(
                types.Tool(
                    function_declarations=[self.expense_tool.declaration],
                )
            )
        return tools

    def _execute_function_call(self, function_call: Any) -> dict[str, Any]:
        name = _get_function_call_name(function_call)
        args = _get_function_call_args(function_call)
        if name == "add_non_credit_expense":
            return self._update_expenses_tool(args)

        return {
            "ok": False,
            "error": f"Unknown tool: {name}",
        }


def _load_personal_history(path: Path) -> str:
    if not path.is_file():
        return "No personal history has been recorded yet."

    content = path.read_text(encoding="utf-8").strip()
    return content or "No personal history has been recorded yet."


def _get_function_call_name(function_call: Any) -> str:
    return str(getattr(function_call, "name", "") or "")


def _get_function_call_args(function_call: Any) -> dict[str, Any]:
    args = getattr(function_call, "args", None) or {}
    return dict(args)

