# Project Management Plan

## Scope

This plan advances Harle from the implemented controlled beta described in [Features](02_FEATURES.md) and the [SRS](03_SRS.md) to a broad commercial release without expanding the first-product channel beyond Telegram.

The current beta already includes multi-user identity, user-scoped profiles and conversations, internal expenses, typed events with process-local Telegram notifications, Juan-only Google Sheets expenses, Telegram deduplication and ordering, temporary bans, and plan quotas.

This plan covers:

- Immediate alignment gaps in the implemented beta
- Reliability, authorization, privacy, and operational work required before broad launch
- Later product capabilities that remain part of the vision but are not broad-launch blockers

## Technology Decisions

- Telegram is the only commercial chat channel in the first version.
- Registration, web UI, payments, and subscription ownership remain in the external product.
- Production uses PostgreSQL; the CLI remains a local development interface.
- FastAPI runs as one process while rate limits, in-flight quotas, per-user ordering, and the five-minute event scheduler are process-local.
- Harle and user-specific stores, profiles, context, and tool handlers remain request-scoped.
- Process-scoped repositories and clients must not retain a current user.
- Commercial users receive PostgreSQL expenses and events.
- Juan receives PostgreSQL events and private legacy Google Sheets expenses based only on his configured internal UUID.
- Current controlled-beta schema changes use ordered idempotent SQL scripts. Versioned migrations remain required before broad launch.
- The current data model is defined in the [ERD](05_ERD.md).

## Non-Functional Targets

- No user may read or modify another user's conversations, profiles, expenses, events, or tool integrations.
- Unknown, inactive, banned, duplicate, or over-quota requests must stop before Gemini and tools.
- A duplicate Telegram update must not duplicate a conversation, tool record, or side effect.
- Logs and metrics must exclude conversation bodies, profile text, financial descriptions, event descriptions, credentials, spreadsheet identifiers, and tool payloads.
- Accepted work that the product promises to complete must survive process restarts.
- Production schema changes, backups, restoration, and account deletion must be repeatable and verifiable.
- Latency and external API cost must remain suitable for frequent daily use.

## Phases and Exit Criteria

### 1. Controlled-Beta Alignment

Goals:

- Persist `telegram_update_id` with tool interactions and enforce the existing update-and-interaction uniqueness rule.
- Move assistant orchestration and failure policy out of `harle_api` so the API depends only on services and utilities.
- Run the PostgreSQL expense, event, isolation, and restart-deduplication tests in the release environment.
- Add focused tests for non-Juan denial before Google Sheets client construction and for ban escalation, notice suppression, and strike decay.

Exit criteria:

- Replaying an update cannot create duplicate tool-interaction rows or side effects.
- Production API modules follow the documented dependency direction.
- All release-critical PostgreSQL integration tests pass against the deployed schema.
- Google Sheets construction and execution both fail safely for every non-Juan UUID.
- All three cooldown levels and strike decay are deterministic under an injected clock.

### 2. Broad-Launch Transaction and Delivery Safety

Goals:

- Replace ordered schema scripts with checksummed, versioned, forward-only migrations.
- Add direct-versus-inferred write authorization at runtime.
- Persist proposed actions, confirmation, cancellation, expiration, execution state, and action audits.
- Add durable Telegram inbox and outbox processing with leases, bounded retries, and stable idempotency keys.
- Synchronize plan and subscription state from the external account product through an authenticated, idempotent contract.

Exit criteria:

- Application startup never mutates schema and refuses incompatible migration state.
- Inferred writes cannot execute before same-user confirmation.
- Every modifying action has one redacted audit record.
- Accepted Telegram work resumes safely after a process restart.
- Subscription updates are authenticated, idempotent, and stop revoked users before assistant execution.

### 3. Privacy and Operations

Goals:

- Define retention, export, deletion, credential revocation, backup retention, and supported-region policies.
- Implement complete account export and deletion across every user-owned PostgreSQL entity.
- Add CI with PostgreSQL, readiness checks, privacy-safe metrics, alerts, backups, and restore verification.
- Establish measurable latency, reliability, and cost thresholds.

Exit criteria:

- Export and deletion cover all user-owned data according to the approved policy.
- Deleted or revoked users cannot authenticate.
- CI executes critical unit and PostgreSQL integration tests without real provider credentials.
- Readiness detects database, schema, and worker failures without calling external providers.
- Backup restoration and credential revocation have been exercised.

### 4. Product Evolution

Implemented baseline:

- Internal events have `user_event` and `system_event` types, `notification_window_start`, and `notification_status` with `disabled`, `pending`, and `delivered` states.
- Both event types enable notifications by default with a 15-minute lead. Users can disable or re-enable notifications, set a positive custom lead, or use zero to restore the default.
- A process-local `AgentsScheduler` runs every five minutes, wakes the owning active user's agent for pending events without modifying tools or consuming conversation quota, and marks notifications delivered after successful Telegram delivery.

Remaining goals:

- Add user-controlled memory and profile inspection, correction, refinement, and deletion.
- Add infinite weekly and monthly recurrence to the existing internal-event record without materializing occurrences.
- Replace the target event lifecycle with active or disabled events plus permanent deletion, and record successful notification time instead of per-occurrence notification state.
- Add native image, voice-note, and audio input through Telegram, automatically attaching current-message media to the Gemini reasoning loop.
- Add a read-only recent-media tool backed by a process-local, best-effort store of the ten newest Telegram media references per user for at least twelve hours.
- Add quiet periods and bounded proactive check-ins only if later product policy requires them.
- Add an authorized agent tool that invokes a controlled Google expense and calendar import or synchronization service.
- Add multi-user Google Sheets and Google Calendar through least-privilege OAuth.
- Define source-of-truth, synchronization, conflict, and revocation behavior before connecting internal and Google data.
- Consider WhatsApp, broader integrations, customization UI, and model routing only after the first commercial architecture is proven.

Exit criteria:

- Each capability has explicit product policy, user ownership, authorization, privacy, and delivery behavior before implementation.
- New integrations do not expose another user's credentials or data.
- Proactive behavior remains opt-in and preserves user agency.
- A recurring event remains one row, supports ordinary event schedules, and delivers at most one notification for each matching occurrence.
- Current-message media reaches Gemini directly, recent media can be reloaded by internal attachment ID, and unsupported media never invokes the assistant.
- Images, audio, imported records, and scheduled event context remain isolated to the owning user.

## Infrastructure and Cost

- Keep one FastAPI process until distributed rate limiting, quota reservations, ordering, and workers are implemented.
- Reuse process-wide PostgreSQL pools and safe provider clients.
- Prefer bounded context, selective tools, concise prompts, caching, and efficient models.
- Introduce infrastructure only when required for durability, isolation, or measurable operating cost.
- Do not add dates, capacity commitments, or plan prices until product and operational evidence supports them.

## Risk Management

- **Cross-user exposure**: Require UUID ownership in every repository operation and maintain two-user integration tests.
- **Legacy Sheets privilege leakage**: Keep authorization, injection, construction, and execution guards tied to Juan's internal UUID.
- **Ambiguous external writes**: Do not retry an uncertain Google Sheets modification automatically; require reconciliation.
- **Duplicate or lost Telegram work**: Use stable update-derived keys, durable queues, leases, and per-user ordering.
- **Process-count drift**: Enforce one-process deployment until coordination state becomes distributed.
- **Sensitive logging**: Use structured allowlisted fields and test that protected content is absent.
- **Recurring notification duplication**: Compare `last_notified_at` with the computed occurrence window and update it only after successful Telegram delivery.
- **Sensitive media references**: Keep Telegram file identifiers out of logs and model context, retain no raw bytes after active use, and scope every recent-media lookup by internal user UUID.
- **Ephemeral media loss**: Treat the twelve-hour process-local media window as best-effort and allow restart to discard it.
- **Unresolved policy implemented as code**: Block the affected phase until the product decision is recorded in Features or the SRS.

## Open Product Decisions

- Final plan names, quotas, upgrades, downgrades, carry-over, and failed-payment grace behavior
- Proposed-action lifetime and Telegram confirmation experience
- Conversation, inbox, outbox, expense, event, audit, and backup retention
- Export format, deletion SLA, credential revocation, and supported operating region
- Future expense currencies, category customization, and export semantics
- Whether Juan may move from legacy Sheets to internal expenses and how existing data would be handled
- Memory consent and automatic learning policy
- Proactive check-in preferences and quiet periods
- System-event creation permissions and supported task payloads
- Supported Telegram image and audio MIME types, file-size limits, and rejection messages
- Internal versus Google source-of-truth and synchronization rules
- Exact service-level targets, metrics, and alert thresholds
