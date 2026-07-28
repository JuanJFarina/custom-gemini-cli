from harle_agent.models import ToolCallResult


def show_tool_results(tool_results: list[ToolCallResult]) -> str:
    if tool_results:
        return "\n".join(
            [f"{result.called_tool_name}: {result.result}" for result in tool_results],
        )
    return "No tool results yet."
