class AccessDeniedError(Exception):
    pass


class UnknownIdentityError(AccessDeniedError):
    pass


class InactiveSubscriptionError(AccessDeniedError):
    pass


class MissingProfileError(AccessDeniedError):
    pass


class ToolAccessDeniedError(AccessDeniedError):
    pass


class ToolUnavailableError(ValueError):
    pass


class InvalidDatabaseSchemaError(RuntimeError):
    pass
