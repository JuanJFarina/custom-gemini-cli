from harle_agent.models import HarleToolResult


def show_tool_results(tool_results: list[HarleToolResult]) -> str:
    if tool_results:
        return "\n".join(
            [f"{result.called_tool_name}: {result.result}" for result in tool_results],
        )
    return "No tool results yet."
