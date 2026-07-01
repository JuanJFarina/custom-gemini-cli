from pathlib import Path
from typing import Any, Awaitable, Callable
import re
from google.genai.types import (
    Tool,
    GenerateContentResponse,
    GenerateContentConfig,
    GoogleSearch,
)
from functools import wraps
from asyncio import create_task, Task
from .memory import PERSONAL_HISTORY_PATH
from .prompts.system import SYSTEM_PROMPT
from .reasoning import (
    HarleThought,
    reasoning_protocol_text,
)
from .runtime_context import (
    get_current_time_and_date,
    get_current_weather,
)
from pydantic import BaseModel, ConfigDict
from google.genai import Client
from .models.harle_models import HarleConfig, HarleStores, HarleToolResult
from .tools.expenses import build_expense_tool_from_env

MAX_ATTEMPTS = 3
MAX_TOOL_DEPTH = 3


def retry(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        attempts = 0
        while attempts < MAX_ATTEMPTS:
            try:
                return await func(*args, **kwargs)
            except Exception:
                attempts += 1
        if func.__name__ == "_call_gemini":
            return HarleThought(
                action="respond",
                response="I couldn't think a response because my AI model is nor responding, sorry !",
            )
        elif func.__name__ == "_call_tool":
            return HarleToolResult(
                tool_name="Tool name not available when creating this error message.",
                result={
                    "error": f"Tool can't be called, even after {MAX_ATTEMPTS} attempts. Don't retry."
                },
            )
        raise RuntimeError(f"{func.__name__} failed after {MAX_ATTEMPTS} attempts.")

    return wrapper


class Harle(BaseModel):
    config: HarleConfig
    stores: HarleStores

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def model_post_init(self, context: Any, /) -> None:
        self._client: Client = Client(api_key=self.config.api_key)
        if expense_tool := build_expense_tool_from_env():
            self.stores.tool_store.tools.append(expense_tool)

    async def call(self, prompt: str) -> tuple[str, Task[None]]:
        conversations = await self.stores.conversation_store.load()
        system_instruction = self._build_system_instruction(conversations)
        response: str = await self.reason_and_act(
            prompt=prompt,
            system_instruction=system_instruction,
        )
        task = self._save_conversation(prompt=prompt, response_text=response)
        return response, task

    async def reason_and_act(
        self,
        prompt: str,
        system_instruction: str,
        depth: int = 0,
    ) -> str:
        harle_thought = await self._call_gemini(
            system_instruction=system_instruction, prompt=prompt
        )

        if harle_thought.action == "respond":
            return harle_thought.response or ""

        if harle_thought.action == "call_tool":
            if depth >= MAX_TOOL_DEPTH:
                return "I could not complete the request because the tool loop reached its limit."

            tool_result = await self._call_tool(harle_thought)
            prompt = self._update_prompt(prompt=prompt, tool_result=tool_result)
            return await self.reason_and_act(
                prompt=prompt,
                system_instruction=system_instruction,
                depth=depth + 1,
            )
        return ""

    @retry
    async def _call_gemini(self, system_instruction: str, prompt: str) -> HarleThought:
        gemini_response: GenerateContentResponse = (
            await self._client.aio.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[
                        Tool(
                            google_search=GoogleSearch(),
                        )
                    ],
                ),
            )
        )
        if not gemini_response.candidates:
            return HarleThought(
                action="respond",
                response="Sorry, could you repeat ?",
            )

        content = gemini_response.candidates[0].content
        parts = content.parts or []
        text_parts: list[str] = []

        for part in parts:
            if part.thought:
                continue

            text = part.text
            if text and text.strip():
                text_parts.append(text.strip())

        response_text = self._extract_json_object(text_parts[-1])
        return HarleThought.model_validate_json(response_text)

    def _save_conversation(self, prompt: str, response_text: str) -> Task[None]:
        return create_task(
            self.stores.conversation_store.save(
                prompt=prompt,
                response_text=response_text,
                model=self.config.model,
            )
        )

    @retry
    async def _call_tool(self, reasoning: HarleThought) -> HarleToolResult:
        tool = self.stores.tool_store.get(reasoning.tool_name)
        result = await tool.tool_func(reasoning.tool_args)
        return HarleToolResult(tool_name=tool.tool_name, result=result)

    def _extract_json_object(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped)

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            return stripped
        return stripped[start : end + 1]

    def _update_prompt(self, prompt: str, tool_result: HarleToolResult) -> str:
        return f"""
            Original user message:
            {prompt}

            After it, you called the tool {tool_result.tool_name}. This is the result:
            {tool_result.result}
            """

    def _build_system_instruction(self, latest_conversations: str) -> str:
        system_instruction = SYSTEM_PROMPT.format(
            current_time_and_date=get_current_time_and_date(),
            current_weather=get_current_weather(),
            juan_personal_history_summary=_load_personal_history(PERSONAL_HISTORY_PATH),
            latest_conversations=latest_conversations,
        )
        system_instruction = f"{system_instruction}\n\n{reasoning_protocol_text()}"
        return system_instruction


def _load_personal_history(path: Path) -> str:
    if not path.is_file():
        return "No personal history has been recorded yet."

    content = path.read_text(encoding="utf-8").strip()
    return content or "No personal history has been recorded yet."
