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

- Internal events have `user_event` and `system_event` types, `notification_window_start`, and a `notified` boolean.
- Both event types default to a 15-minute notification lead, which can be changed per event.
- A process-local `AgentsScheduler` runs every five minutes, wakes the owning active user's agent without modifying tools or consuming conversation quota, and marks events notified after successful Telegram delivery.

Remaining goals:

- Add user-controlled memory and profile inspection, correction, refinement, and deletion.
- Add notification preferences, quiet periods, and bounded proactive check-ins.
- Add image and voice-note input through Telegram.
- Add an authorized agent tool that invokes a controlled Google expense and calendar import or synchronization service.
- Add multi-user Google Sheets and Google Calendar through least-privilege OAuth.
- Define source-of-truth, synchronization, conflict, and revocation behavior before connecting internal and Google data.
- Consider WhatsApp, broader integrations, customization UI, and model routing only after the first commercial architecture is proven.

Exit criteria:

- Each capability has explicit product policy, user ownership, authorization, privacy, and delivery behavior before implementation.
- New integrations do not expose another user's credentials or data.
- Proactive behavior remains opt-in and preserves user agency.
- Images, voice notes, imported records, and scheduled event context remain isolated to the owning user.

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
- **Unresolved policy implemented as code**: Block the affected phase until the product decision is recorded in Features or the SRS.

## Open Product Decisions

- Final plan names, quotas, upgrades, downgrades, carry-over, and failed-payment grace behavior
- Proposed-action lifetime and Telegram confirmation experience
- Conversation, inbox, outbox, expense, event, audit, and backup retention
- Export format, deletion SLA, credential revocation, and supported operating region
- Future expense currencies, category customization, and export semantics
- Whether Juan may move from legacy Sheets to internal expenses and how existing data would be handled
- Memory consent and automatic learning policy
- Reminder recurrence, notification preferences, and quiet periods
- Behavior when scheduler downtime causes an event notification window to be missed
- System-event creation permissions and supported task payloads
- Image and voice-note size, retention, transcription, and unsupported-media behavior
- Internal versus Google source-of-truth and synchronization rules
- Exact service-level targets, metrics, and alert thresholds
