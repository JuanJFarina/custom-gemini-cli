# Commercial Release Workloads

These seven workloads define the reduced controlled-beta implementation scope agreed after reviewing the broader commercial plan.

Read before implementation:

- `../01_VISION.md`
- `../02_FEATURES.md`
- `../03_SRS.md`
- `COMMERCIAL_RELEASE_DELTA.md`
- `COMMERCIAL_V1_IMPLEMENTATION_PLAN.md`
- The selected workload's `README.md`

The product documents still contain broader requirements around reminders, scheduling, and Google integrations. Do not implement those when they conflict with a workload brief; raise the conflict for a product decision.

## Workloads

1. `01-architecture-foundation`
2. `02-multi-user-runtime`
3. `03-tool-registry-sheets-isolation`
4. `04-internal-expenses`
5. `05-internal-events`
6. `06-telegram-dedup-ordering`
7. `07-bans-quotas`

Workloads 4 and 5 may proceed independently after workloads 2 and 3.

## Shared constraints

- Keep FastAPI as one process and Telegram as the only commercial channel.
- Keep `Harle` and all user-specific state request-scoped.
- Follow the API, services, infrastructure, domain, and utils dependency boundaries in `.cursor/rules/hexagonal_architecture.mdc`.
- Prefer small, typed implementations and focused tests.
- Preserve current CLI and Juan Google Sheets behavior unless a workload explicitly changes it.
- Aggregate consecutive messages while the current turn remains safe to restart, while rate-limiting every persisted Telegram update independently.
- Select likely tool families with explicit English and Spanish terms, falling back to all authorized families when no term matches.
- Let Harle execute an available modifying tool when it interprets the user's current prompt as requesting the change; do not add a separate runtime authorization gate.
- Never infer unresolved product behavior. Ask before implementing it.

## Deferred from these workloads

- A PostgreSQL migration framework
- Persisted proposed actions and Telegram confirmation buttons
- Durable inbox/outbox workers
- Automated subscription synchronization, export, and deletion
- CI, readiness, metrics, alerts, and backup automation
- Multi-user Google Sheets, Google Calendar, reminders, recurrence, and proactive scheduling

Some deferred items remain necessary before a broad paid launch. Database changes must be proposed and approved before modifying an existing production schema.

## Deployment

Apply the commercial schema scripts in this order before starting the application:

1. `scripts/apply_multi_user_runtime.sql`
2. `scripts/apply_internal_expenses.sql`
3. `scripts/apply_internal_events.sql`
4. `scripts/apply_telegram_dedup_ordering.sql`
5. `scripts/apply_bans_quotas.sql`
