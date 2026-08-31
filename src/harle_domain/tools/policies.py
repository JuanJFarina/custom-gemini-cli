from harle_domain.tools.models import ToolCall, ToolDefinition, ToolEffect
from harle_utils import ToolAccessDeniedError


def require_direct_request(
    *,
    definition: ToolDefinition,
    call: ToolCall,
    user_message: str,
) -> None:
    if definition.effect is ToolEffect.READ:
        return

    quote = (call.direct_request_quote or "").strip()
    if len(quote) < 2 or quote.casefold() not in user_message.casefold():
        raise ToolAccessDeniedError(
            "A modifying tool requires a direct request in the current message.",
        )
