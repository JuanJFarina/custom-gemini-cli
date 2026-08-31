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

## Deployment

Apply the idempotent schema script before deploying this workload:

```bash
psql "$POSTGRES_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f scripts/apply_multi_user_runtime.sql
```

The script preserves existing user UUIDs and conversations, backfills Telegram
identities, and leaves existing accounts inactive. Provision Juan and each beta
user explicitly before enabling webhook traffic:

```bash
python scripts/provision_user.py \
  --telegram-id TELEGRAM_USER_ID \
  --display-name "User Name" \
  --plan-code basic \
  --subscription-status active \
  --preferred-name "Preferred Name" \
  --locale en-US \
  --timezone UTC \
  --assistant-display-name Harle \
  --assistant-profile-text "A concise and transparent AI personal assistant."
```

For Juan's existing context, also pass
`--personal-history-file data/juan_personal_history.md` and his configured
location and timezone.

PostgreSQL is required for the Telegram runtime. Application startup validates
the schema and never applies DDL.

Do not roll out this workload to multiple real users until workload 3 is also
deployed. Tool-family authorization is intentionally deferred, so the legacy
global Google Sheets tools are not yet isolated.

Depends on workload 1.
