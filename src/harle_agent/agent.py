import re
from asyncio import Task, create_task
from pathlib import Path
from time import time
from typing import Any

from google.genai import Client
from google.genai.types import (
    GenerateContentConfig,
    GenerateContentResponse,
    GoogleSearch,
    Tool,
)
from pydantic import BaseModel, ConfigDict, Field

from harle_utils import log

from .environment_knowledge import (
    get_current_time_and_date,
    get_current_weather,
)
from .models import (
    HarleConfig,
    HarleStores,
    HarleThought,
    HarleThoughtAdapter,
    HarleToolCall,
    HarleToolResult,
)
from .prompts import SYSTEM_PROMPT
from .retry_decorator import retry
from .settings import PERSONAL_HISTORY_PATH, get_agent_settings
from .tools import TOOLS, show_tool_results

Settings = get_agent_settings()


class Harle(BaseModel):
    config: HarleConfig = Field(default_factory=HarleConfig)
    stores: HarleStores
    _client: Client | None = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def model_post_init(self, _: Any, /) -> None:
        self._client = self._client or Client(api_key=self.config.api_key)
        self.stores.tool_store.tools.extend(TOOLS)

    async def call(self, prompt: str) -> tuple[str, Task[None]]:
        start_time = time()
        log.info("Loading conversations")
        conversations = await self.stores.conversation_store.load()
        log.info("Building system instruction")
        system_instruction = self._build_system_instruction(conversations)
        log.info("Starting reason and act loop")
        response: str = await self._reason_and_act(
            prompt=prompt,
            system_instruction=system_instruction,
        )
        log.info("Creating task to save conversation")
        task = self._save_conversation(prompt=prompt, response_text=response)
        log.info(f"Reason and act loop took {time() - start_time} seconds")
        return response, task

    async def _reason_and_act(
        self,
        prompt: str,
        system_instruction: str,
        tool_results: list[HarleToolResult] | None = None,
    ) -> str:
        tool_results = tool_results or []
        if len(tool_results) >= Settings.MAX_LOOPS:
            return (
                "I'm looping infinitely, these are the tool results so far: "
                f"{show_tool_results(tool_results)}"
            )
        harle_thought = await self._call_gemini(
            system_instruction=system_instruction,
            prompt=prompt,
            tool_results=tool_results,
        )

        if harle_thought.action == "respond":
            if not harle_thought.response:
                log.warning("Action is respond but response is empty")
            return harle_thought.response or "I can't respond for some reason, sorry !"

        if harle_thought.action == "call_tool":
            result = await self._call_tool(harle_thought)
            return await self._reason_and_act(
                prompt=prompt,
                system_instruction=system_instruction,
                tool_results=tool_results + [result],
            )
        log.warning(f"Unknown action: {harle_thought.action}")
        return "I can't respond for some reason, sorry !"

    @retry
    async def _call_gemini(
        self,
        system_instruction: str,
        prompt: str,
        tool_results: list[HarleToolResult],
    ) -> HarleThought:
        for result in tool_results:
            prompt = self._update_prompt(prompt=prompt, tool_result=result)
        assert self._client
        gemini_response: GenerateContentResponse = (
            await self._client.aio.models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[
                        Tool(
                            google_search=GoogleSearch(),
                        ),
                    ],
                ),
            )
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
        return HarleThoughtAdapter.validate_json(response_text)

    def _save_conversation(self, prompt: str, response_text: str) -> Task[None]:
        return create_task(
            self.stores.conversation_store.save(
                prompt=prompt,
                response_text=response_text,
                model=self.config.model,
            ),
        )

    @retry
    async def _call_tool(self, tool_call: HarleToolCall) -> HarleToolResult:
        tool = self.stores.tool_store.get(tool_call.tool_name)  # type: ignore[arg-type]
        result = await tool.func(tool_call.tool_args)
        log.info(f"Tool {tool.name} called successfully")
        return result

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

            After it, you called the tool {tool_result.called_tool_name}. This is the result:
            {tool_result.result}
            """

    def _build_system_instruction(self, latest_conversations: str) -> str:
        tools_prompt = "\n".join([tool.prompt for tool in TOOLS])
        system_instruction = SYSTEM_PROMPT.format(
            tools=tools_prompt,
            juan_personal_history_summary=_load_personal_history(PERSONAL_HISTORY_PATH),
            current_time_and_date=get_current_time_and_date(),
            current_weather=get_current_weather(),
            latest_conversations=latest_conversations,
        )
        print(f"\n---------\n{system_instruction}\n---------\n")
        print(
            f"\n---------\nSystem Instructions Token Size: {len(system_instruction) / 4:.0f}\n---------\n",
        )
        log.info(f"System Instructions Token Size: {len(system_instruction) / 4:.0f}")
        return system_instruction


def _load_personal_history(path: Path) -> str:
    if not path.is_file():
        log.warning(f"Personal history file {path} does not exist")
        return "No personal history has been recorded yet."

    content = path.read_text(encoding="utf-8").strip()
    if not content:
        log.warning("Personal history file is empty")
    return content or "No personal history has been recorded yet."
