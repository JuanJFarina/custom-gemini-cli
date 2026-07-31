# Workload 2: Multi-User Runtime

## Goal

Resolve every Telegram request to one internal user and load only that user's conversations and personal context.

## Scope

- Replace the startup owner and allowed-user gate with per-request identity and subscription resolution.
- Build an immutable, request-scoped user runtime.
- Require the resolved user UUID in every conversation read and write.
- Store and load user profile, assistant profile, personal history, locale, and timezone by user UUID.
- Parameterize prompts and remove Juan-specific identity, human-identity claims, and sensitive prompt logging.
- Support manually provisioned beta users.
- Prove isolation with two users.

## Not included

- Automated account or payment synchronization
- A migration framework
- Tool-family authorization
- Memory learning or summarization

## Important boundary

Identity answers who may run Harle and own data. Profiles and prompts provide that user's context after identity is established. Neither may use process-global user state.

Propose any required database schema change before implementing it against an existing database.

## Done when

- Unknown or inactive users stop before Gemini.
- Two users cannot access each other's conversations or profiles.
- No runtime prompt or personal-history source is hardcoded to Juan.

Depends on workload 1.
