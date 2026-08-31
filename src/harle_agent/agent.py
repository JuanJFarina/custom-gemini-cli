import re
from asyncio import Task, create_task, gather
from collections.abc import Awaitable, Callable
from time import time

from google.genai import Client
from google.genai.types import (
    GenerateContentConfig,
    GenerateContentResponse,
    GoogleSearch,
    Tool,
)
from pydantic import BaseModel, ConfigDict, Field

from harle_domain.tools.models import (
    InternalToolCallInteraction,
    ToolCall,
    ToolCallResult,
)
from harle_utils import log

from .environment_knowledge import (
    get_current_time_and_date,
    get_current_weather,
)
from .models import (
    HarleConfig,
    HarlePersonalContext,
    HarleRunResult,
    HarleStores,
    HarleThought,
    HarleThoughtAdapter,
)
from .prompts import SYSTEM_PROMPT
from .retry_decorator import retry
from .settings import get_agent_settings
from .tools import TOOLS, show_tool_results

SETTINGS = get_agent_settings()


class Harle(BaseModel):
    config: HarleConfig = Field(default_factory=HarleConfig)
    stores: HarleStores
    personal_context: HarlePersonalContext
    _client: Client | None = None

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def model_post_init(self, _: object, /) -> None:
        self._client = self._client or Client(api_key=self.config.api_key)
        registered_tool_names = {tool.name for tool in self.stores.tool_store.tools}
        self.stores.tool_store.tools.extend(
            tool for tool in TOOLS if tool.name not in registered_tool_names
        )

    async def call(self, prompt: str) -> tuple[str, Task[None]]:
        start_time = time()
        log.info("Loading conversations and current weather")
        conversations_task = create_task(self.stores.conversation_store.load())
        weather_task = create_task(
            get_current_weather(
                latitude=self.personal_context.latitude,
                longitude=self.personal_context.longitude,
                timezone_name=self.personal_context.timezone,
            ),
        )
        conversations, current_weather = await gather(conversations_task, weather_task)
        log.info("Building system instruction")
        system_instruction = self._build_system_instruction(
            conversations,
            current_weather=current_weather,
        )
        log.info("Starting reason and act loop")
        run_result = await self._reason_and_act(
            prompt=prompt,
            system_instruction=system_instruction,
        )
        log.info("Creating task to save conversation")
        task = self._save_conversation(prompt=prompt, run_result=run_result)
        log.info(f"Reason and act loop took {time() - start_time} seconds")
        return run_result.response_text, task

    async def _reason_and_act(
        self,
        prompt: str,
        system_instruction: str,
        tool_interactions: list[InternalToolCallInteraction] | None = None,
    ) -> HarleRunResult:
        tool_interactions = tool_interactions or []
        tool_results = _tool_results(tool_interactions)
        if len(tool_interactions) >= SETTINGS.MAX_LOOPS:
            return HarleRunResult(
                response_text=(
                    "I'm looping infinitely, these are the tool results so far: "
                    f"{show_tool_results(tool_results)}"
                ),
                tool_interactions=tool_interactions,
            )
        harle_thought = await self._call_gemini(
            system_instruction=system_instruction,
            prompt=prompt,
            tool_results=tool_results,
        )

        if harle_thought.action == "respond":
            if not harle_thought.response:
                log.warning("Action is respond but response is empty")
            return HarleRunResult(
                response_text=(
                    harle_thought.response or "I can't respond for some reason, sorry !"
                ),
                tool_interactions=tool_interactions,
            )

        if harle_thought.action == "call_tool":
            results = await self._call_tools_in_batches(harle_thought.calls)
            interaction = InternalToolCallInteraction(
                tool_calls=harle_thought.calls,
                tool_results=results,
            )
            return await self._reason_and_act(
                prompt=prompt,
                system_instruction=system_instruction,
                tool_interactions=tool_interactions + [interaction],
            )
        log.warning(f"Unknown action: {harle_thought.action}")
        return HarleRunResult(
            response_text="I can't respond for some reason, sorry !",
            tool_interactions=tool_interactions,
        )

    @retry
    async def _call_gemini(
        self,
        system_instruction: str,
        prompt: str,
        tool_results: list[ToolCallResult],
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

        candidates = gemini_response.candidates or []
        if not candidates or candidates[0].content is None:
            raise ValueError("Gemini response did not include content.")

        content = candidates[0].content
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

    def _save_conversation(self, prompt: str, run_result: HarleRunResult) -> Task[None]:
        return create_task(self._save_conversation_run(prompt, run_result))

    async def _save_conversation_run(
        self,
        prompt: str,
        run_result: HarleRunResult,
    ) -> None:
        for interaction in run_result.tool_interactions:
            await self.stores.conversation_store.save_tool_call(
                interaction=interaction,
                model=self.config.model,
            )

        await self.stores.conversation_store.save(
            prompt=prompt,
            response_text=run_result.response_text,
            model=self.config.model,
        )

    async def _call_tools_in_batches(
        self,
        calls: list[ToolCall],
    ) -> list[ToolCallResult]:
        results: list[ToolCallResult] = []
        concurrent_calls: list[ToolCall] = []
        for call in calls:
            tool = self.stores.tool_store.get(call.tool_name)
            if tool.can_run_concurrently:
                concurrent_calls.append(call)
                continue
            results.append(await self._call_tool(call))
        results.extend(
            await _call_concurrently(concurrent_calls, self._call_tool),
        )
        return results

    @retry
    async def _call_tool(self, call: ToolCall) -> ToolCallResult:
        tool = self.stores.tool_store.get(call.tool_name)
        return await tool.func(call.tool_args)

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

    def _update_prompt(self, prompt: str, tool_result: ToolCallResult) -> str:
        return f"""
            Original user message:
            {prompt}

            After it, you called the tool {tool_result.called_tool_name}. This is the result:
            {tool_result.result}
            """

    def _build_system_instruction(
        self,
        conversations: str,
        *,
        current_weather: str,
    ) -> str:
        tools_prompt = "\n".join(tool.prompt for tool in self.stores.tool_store.tools)
        system_instruction = SYSTEM_PROMPT.format(
            user_name=self.personal_context.user_name,
            preferred_name=self.personal_context.preferred_name,
            locale=self.personal_context.locale,
            timezone=self.personal_context.timezone,
            assistant_profile=self.personal_context.assistant_profile,
            personal_history=self.personal_context.personal_history,
            conversations=conversations,
            tools=tools_prompt,
            current_time_and_date=get_current_time_and_date(
                self.personal_context.timezone,
            ),
            current_weather=current_weather,
        )
        log.info(f"System Instructions Token Size: {len(system_instruction) / 4:.0f}")
        return system_instruction


async def _call_concurrently(
    calls: list[ToolCall],
    call_func: Callable[[ToolCall], Awaitable[ToolCallResult]],
) -> list[ToolCallResult]:
    coroutines = [call_func(call) for call in calls]
    return await gather(*coroutines)


def _tool_results(
    tool_interactions: list[InternalToolCallInteraction],
) -> list[ToolCallResult]:
    return [
        result
        for interaction in tool_interactions
        for result in interaction.tool_results
    ]
