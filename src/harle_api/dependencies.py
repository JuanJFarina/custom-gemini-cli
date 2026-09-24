from fastapi import Request

from harle_api.runtime import ApiRuntime
from harle_services.bootstrap import AccountRuntime


def get_runtime(request: Request) -> ApiRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApiRuntime):
        raise RuntimeError("API runtime is not initialized.")
    return runtime


def get_account_runtime(request: Request) -> AccountRuntime:
    runtime = get_runtime(request)
    if runtime.account is None:
        raise RuntimeError("Account runtime is not initialized.")
    return runtime.account
