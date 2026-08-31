class AccessDeniedError(Exception):
    pass


class UnknownIdentityError(AccessDeniedError):
    pass


class InactiveSubscriptionError(AccessDeniedError):
    pass


class MissingProfileError(AccessDeniedError):
    pass


class InvalidDatabaseSchemaError(RuntimeError):
    pass
