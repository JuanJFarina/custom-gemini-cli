# Harle Commercial Version 1 Implementation Plan

## Document Purpose

This document turns `COMMERCIAL_RELEASE_DELTA.md` and `docs/target_architecture.png` into a concrete implementation plan for the first commercial release.

It describes:

- The exact first-version product boundary
- The target runtime and package architecture
- The PostgreSQL schema and migration path
- The required service, repository, tool, API, and infrastructure changes
- The isolation mechanism for Juan José Farina's existing Google Sheets expense tools
- The implementation sequence, validation gates, deployment changes, and release criteria

This is an implementation plan, not an authorization to implement every phase at once. Each phase should be reviewed and implemented through small, independently verifiable steps.

## Resolved First-Version Scope

### Commercial users

Every active commercial user receives:

- Telegram access
- An isolated internal Harle user account
- PostgreSQL-backed conversations and tool interactions
- A PostgreSQL-backed user profile and personal history
- PostgreSQL-backed internal expense tracking
- PostgreSQL-backed internal calendar-like events
- User-scoped tool authorization
- Direct-write versus proposed-write authorization
- Temporary anti-abuse bans
- Plan-based monthly quotas
- Privacy, deletion, export, audit, and operational protections required by the release delta

### Juan José Farina

Juan receives:

- The same multi-user identity, profile, conversation, event, quota, and safety infrastructure
- The internal event tool family
- The existing Google Sheets expense tool family
- No internal PostgreSQL expense tool family by default

Juan's Google Sheets access is a private compatibility path, not a commercial integration. It remains backed by the current process-level service-account credentials and spreadsheet IDs.

Authorization must use Juan's stable internal UUID. Display name, Telegram username, and Telegram chat ID must never be used as the privilege check.

### Deferred to commercial version 2

- Multi-user Google Sheets onboarding and OAuth
- Google Calendar OAuth and tools
- Synchronization between internal expenses and Google Sheets
- Synchronization between internal events and Google Calendar
- Recurring events
- Event attendees
- Reminders and event notifications
- Proactive event polling
- Agent scheduling and autonomous check-ins
- Additional communication channels
- Distributed rate limiting
- Multi-process deployment

## Tool Access Matrix

| Tool family | Commercial user | Juan | Version 1 backend |
| --- | ---: | ---: | --- |
| Internal expenses | Yes | No | PostgreSQL |
| Internal events | Yes | Yes | PostgreSQL |
| User and assistant profile tools | Yes | Yes | PostgreSQL |
| Legacy Google Sheets expenses | No | Yes | Existing Google Sheets service-account integration |
| Google Calendar | No | No | Deferred |

The Juan expense decision is mutually exclusive in version 1: a request receives either the internal expense family or the legacy Google Sheets expense family, never both.

## Architecture Interpretation

The target architecture diagram is retained as the conceptual architecture with the following first-version adaptations:

- `FastAPI` and `Preflight Policy` are required.
- `Agent` and `AgentConfig` are request-scoped.
- PostgreSQL repositories, connection pools, tool metadata, and safe external clients may be process-scoped.
- Repositories must be stateless with respect to users. A process-scoped repository receives the user UUID in every operation or is wrapped by an immutable request-scoped facade.
- `ConversationStore`, `UserPersonaStore`, `AssistantPersonaStore`, the internal expense store, the internal event store, proposed-action storage, and action auditing use PostgreSQL.
- The diagram's `RemindersStore` becomes an `EventStore` in version 1. Reminder delivery remains deferred.
- `ToolsInjector` must perform authorization filtering in version 1.
- Prompt-relevance ranking and tool-detail search are optional optimizations after authorization filtering is proven safe.
- `TimeAndWeatherInjector` may be process-scoped, but it must receive user-specific timezone and location inputs.
- Polling injectors, `NewsInjector`, and `AgentsScheduler` are deferred.
- The CLI remains a development interface and is not a commercial product surface.

## Required Dependency Boundaries

The implementation must converge on these layers:

```text
harle_api            -> harle_services, harle_utils
harle_services       -> harle_infrastructure, harle_domain, harle_utils
harle_infrastructure -> harle_domain, harle_utils
harle_domain         -> harle_utils
harle_utils          -> standard library and utility dependencies
```

Responsibilities:

- `harle_api`: FastAPI routes, payload validation, headers, status codes, and response serialization
- `harle_services`: use-case orchestration, agent execution, preflight, tool injection, authorization, quotas, and privacy workflows
- `harle_infrastructure`: PostgreSQL repositories, migrations, dependency injection, provider clients, and fake clients
- `harle_domain`: entities, value objects, invariants, policies, and external communication interfaces
- `harle_utils`: settings, logging, clocks, exceptions, encryption helpers, and other cross-cutting concerns

API handlers must remain thin and contain no business policy or `try`/`except` blocks. Service exceptions should be translated through registered FastAPI exception handlers.

## Target Package Structure

The final structure should be:

```text
src/
  harle_api/
    app.py
    dependencies.py
    settings.py
    exception_handlers.py
    routes/
      health.py
      telegram.py
      account_sync.py
      privacy.py
    payloads/
      telegram.py
      account_sync.py
      privacy.py

  harle_services/
    bootstrap.py
    agent/
      models.py
      runner.py
      prompt_builder.py
      runtime.py
      retry.py
    access/
      identity.py
      subscriptions.py
      preflight.py
      rate_limit.py
      quota.py
    tools/
      registry.py
      injector.py
      executor.py
      authorization.py
    expenses/
      service.py
      handlers.py
    events/
      service.py
      handlers.py
    profiles/
      service.py
      handlers.py
    actions/
      service.py
      confirmations.py
    messaging/
      processor.py
      worker.py
    privacy/
      export.py
      deletion.py

  harle_domain/
    accounts/
      models.py
      ports.py
      policies.py
    conversations/
      models.py
      ports.py
    profiles/
      models.py
      ports.py
    expenses/
      models.py
      ports.py
      rules.py
    events/
      models.py
      ports.py
      rules.py
    tools/
      models.py
      ports.py
      policies.py
    actions/
      models.py
      ports.py
    messaging/
      models.py
      ports.py

  harle_infrastructure/
    di/
      container.py
    postgres/
      pool.py
      migrations.py
      transaction.py
      repositories/
        accounts.py
        conversations.py
        profiles.py
        expenses.py
        events.py
        actions.py
      messaging/
        inbox.py
        outbox.py
    google_sheets/
      settings.py
      client.py
      repository.py
      mappings.py
    gemini/
      client.py
    telegram/
      client.py
    context/
      time_weather.py
    local/
      file_conversations.py
      sqlite_conversations.py
    fakes/
      gemini.py
      telegram.py
      google_sheets.py
      clock.py

  harle_cli/
    cli.py

  harle_utils/
    settings.py
    logging.py
    exceptions.py
    clock.py
    encryption.py

migrations/
  0001_accounts.sql
  0002_conversations.sql
  0003_profiles.sql
  0004_internal_expenses.sql
  0005_internal_events.sql
  0006_actions.sql
  0007_telegram_delivery.sql

scripts/
  migrate.py
  provision_user.py
  verify_restore.py

tests/
  unit/
  integration/
  fakes/
```

The package migration should be incremental. Compatibility imports may temporarily remain in `harle_agent`, but production code must stop importing from them before that package is removed.

## Component Lifecycles

### Process-scoped components

The FastAPI lifespan should create and own:

- One `asyncpg.Pool`
- Stateless PostgreSQL repository instances wrapping the pool
- One Gemini client
- One Telegram API client
- One lazily created Google Sheets client for Juan's private capability
- One immutable tool registry containing metadata and handler factories
- One `RateLimitService`
- One `UsageQuotaService`
- One per-user work coordinator
- One durable inbox worker
- One durable outbox worker
- One time and weather injector with bounded caches
- Typed process settings

Process-scoped components must not store a current user UUID, current chat ID, prompt, profile, credentials selected from a user record, or any other request-specific mutable value.

### Request-scoped components

Each accepted message receives an immutable `UserRuntime` containing:

- Internal user UUID
- Telegram identity and chat ID
- Telegram `update_id`
- Display name
- Plan and subscription status
- Locale and IANA timezone
- User and assistant profiles
- User-scoped conversation facade
- User-scoped expense facade
- User-scoped event facade
- Proposed-action and audit facades
- Authorized tool families
- Injected tool definitions and handlers
- Agent configuration
- Correlation and idempotency keys

`Harle` remains request-scoped and is created from this runtime.

## First-Version Telegram Flow

The final request path is:

1. Telegram sends a webhook update.
2. FastAPI validates `X-Telegram-Bot-Api-Secret-Token`.
3. The API payload model validates and extracts `update_id`, sender ID, chat ID, display name, message text, and callback data when present.
4. `TelegramInboxRepository.claim()` inserts the update ID.
5. A duplicate update returns immediately without quota reservation, Gemini, tools, a second response, or a second audit entry.
6. `IdentityService` maps the Telegram sender ID to an internal user UUID.
7. `RateLimitService` rejects a currently banned identity or records the accepted timestamp.
8. `SubscriptionService` rejects unknown, inactive, expired, or revoked users.
9. `UsageQuotaService` atomically checks the completed UTC-month count plus process-local in-flight reservations.
10. Accepted work is stored durably in the PostgreSQL inbox before the webhook acknowledges it.
11. The message worker acquires the per-user execution lock.
12. `UserRuntimeFactory` loads the user, profile, stores, tool permissions, and context.
13. `ToolsInjector` selects authorized families.
14. `AgentRunner` loads context, calls Gemini, executes authorized reads or writes, and produces a final response.
15. Conversation completion, internal writes, action audit records, and outbound messages are persisted with stable idempotency keys.
16. The quota reservation is released in all outcomes.
17. The outbox worker sends pending Telegram chunks and records Telegram message IDs.

Typing indicators remain best-effort and do not enter the durable outbox.

## PostgreSQL Migration Strategy

### Migration mechanism

Use numbered SQL migrations executed by a small `asyncpg` migration runner. Do not add an ORM solely for migrations.

The runner must:

- Create `schema_migrations` if absent
- Acquire a PostgreSQL advisory lock
- Verify migration checksums
- Apply each pending migration in its own transaction
- Record version, checksum, and application timestamp
- Fail startup or deployment before serving traffic when migration state is invalid

Application startup must never run `CREATE TABLE`, `ALTER TABLE`, or implicit schema repair.

### Existing database preservation

The current production database already has `users` and `conversations`.

Migration must:

1. Preserve every current user UUID.
2. Identify the current Juan row through the existing Telegram ID.
3. Backfill its Telegram identity into `external_identities`.
4. Keep `users.telegram_id` temporarily during the beta migration.
5. Add conversation status and mark existing conversation rows as completed.
6. Preserve existing conversation and tool-call rows.
7. Record Juan's existing UUID as `LEGACY_GOOGLE_SHEETS_USER_ID` in deployment configuration.
8. Verify row counts and ownership before removing startup owner creation.

Dropping `users.telegram_id` should be a later migration after the beta has proven identity resolution.

### Migration files

#### `0001_accounts.sql`

Create or adapt:

- `plans`
- `users`
- `external_identities`

`plans`:

- `code TEXT PRIMARY KEY`
- `monthly_request_limit INTEGER NOT NULL`
- `active BOOLEAN NOT NULL`
- timestamps

Seed provisional plans:

- `free`: 60
- `basic`: 480
- `max`: 1920

`users`:

- `id UUID PRIMARY KEY`
- `display_name TEXT NOT NULL`
- `plan_code TEXT NOT NULL REFERENCES plans(code)`
- `subscription_status TEXT NOT NULL`
- `subscription_valid_until TIMESTAMPTZ`
- `subscription_synced_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

Allowed subscription values:

- `active`
- `inactive`
- `past_due`
- `cancelled`
- `revoked`

`external_identities`:

- `id UUID PRIMARY KEY`
- `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
- `provider TEXT NOT NULL`
- `external_user_id TEXT NOT NULL`
- `display_name TEXT NOT NULL`
- timestamps
- unique constraint on `(provider, external_user_id)`
- index on `user_id`

#### `0002_conversations.sql`

Adapt `conversations`:

- Keep `user_id`, Telegram chat ID, prompt, response, model, kind, tool-call payload, result payload, and creation time
- Add `status`
- Add `telegram_update_id`
- Add `failure_code`
- Add `completed_at`
- Replace Juan-specific serialization keys only in application formatting; existing row columns do not need renaming

Allowed status values:

- `processing`
- `completed`
- `failed`

Indexes:

- `(user_id, telegram_chat_id, created_at DESC, id DESC)`
- `(user_id, kind, status, created_at)`
- partial quota index for completed conversation rows

Quota counts only:

```text
kind = 'conversation' AND status = 'completed'
```

#### `0003_profiles.sql`

Create:

- `user_profiles`
- `assistant_profiles`

`user_profiles`:

- `user_id UUID PRIMARY KEY`
- `preferred_name TEXT NOT NULL`
- `locale TEXT NOT NULL`
- `timezone TEXT NOT NULL`
- `latitude NUMERIC`
- `longitude NUMERIC`
- `personal_history TEXT NOT NULL`
- timestamps

`assistant_profiles`:

- `user_id UUID PRIMARY KEY`
- `display_name TEXT NOT NULL`
- `profile_text TEXT NOT NULL`
- timestamps

Juan's `data/juan_personal_history.md` becomes one-time seed input. Runtime code must stop reading the file after migration.

#### `0004_internal_expenses.sql`

Create `expense_transactions`:

- `id UUID PRIMARY KEY`
- `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
- `entry_type TEXT NOT NULL`
- `amount NUMERIC(18, 2) NOT NULL`
- `currency CHAR(3) NOT NULL`
- `category TEXT NOT NULL`
- `transaction_date DATE NOT NULL`
- `description TEXT NOT NULL`
- `status TEXT NOT NULL`
- `installment_group_id UUID`
- `installment_number SMALLINT`
- `installment_count SMALLINT`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`
- `cancelled_at TIMESTAMPTZ`

Allowed entry types:

- `expense`
- `refund`

Allowed statuses:

- `active`
- `cancelled`

Initial categories:

- `rent`
- `essential_services`
- `non_essential_services`
- `home`
- `transport`
- `outings`
- `shopping`
- `other`

Constraints:

- Amount is positive; refund semantics come from `entry_type`
- Currency is a three-letter uppercase ISO code
- Installment fields are either all null or all populated
- Installment count is between 2 and 12
- Installment number is between 1 and installment count

Indexes:

- `(user_id, transaction_date DESC)`
- `(user_id, status, transaction_date DESC)`
- `(user_id, category, transaction_date DESC)`
- partial `(user_id, installment_group_id)` where group ID is not null

#### `0005_internal_events.sql`

Create `internal_events`:

- `id UUID PRIMARY KEY`
- `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
- `title TEXT NOT NULL`
- `description TEXT NOT NULL`
- `starts_at TIMESTAMPTZ NOT NULL`
- `ends_at TIMESTAMPTZ NOT NULL`
- `timezone TEXT NOT NULL`
- `all_day BOOLEAN NOT NULL`
- `status TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`
- `cancelled_at TIMESTAMPTZ`
- `deleted_at TIMESTAMPTZ`

Allowed statuses:

- `scheduled`
- `cancelled`
- `deleted`

Constraints:

- `ends_at > starts_at`
- Timezone must be validated by the application as an IANA timezone

Indexes:

- `(user_id, starts_at)`
- `(user_id, status, starts_at)`

User-facing deletion is soft deletion. Account deletion may physically cascade rows according to the final retention policy.

#### `0006_actions.sql`

Create:

- `proposed_actions`
- `action_audits`

`proposed_actions`:

- action UUID
- owner UUID
- source update ID
- tool family
- tool name
- validated arguments JSON
- user-facing summary
- status
- expiration, confirmation, execution, and creation timestamps

Allowed statuses:

- `pending`
- `confirmed`
- `cancelled`
- `expired`
- `executing`
- `executed`
- `failed`
- `needs_reconciliation`

`action_audits`:

- audit UUID
- owner UUID
- proposed action UUID when applicable
- idempotency key
- tool family and tool name
- authorization mode
- target type and target identifier
- redacted before and after state
- result status
- source update ID
- creation timestamp

Allowed authorization modes:

- `direct`
- `confirmed`

The audit idempotency key must be unique.

#### `0007_telegram_delivery.sql`

Create:

- `telegram_inbox`
- `telegram_outbox`

`telegram_inbox`:

- `update_id BIGINT PRIMARY KEY`
- Telegram user ID
- internal user UUID when resolved
- chat ID
- message text or callback data required to process accepted work
- status
- attempt count
- lease expiration
- rejection code
- receive, start, and completion timestamps

Allowed statuses:

- `received`
- `accepted`
- `processing`
- `completed`
- `failed`
- `rejected`

`telegram_outbox`:

- outbox UUID
- update ID
- chat ID
- chunk index
- response text
- status
- attempt count
- Telegram message ID
- creation, lease, send, and failure timestamps
- unique constraint on `(update_id, chunk_index)`

Message retention must be governed by the data policy because inbox and outbox rows contain conversation content.

## Domain Model and Port Work

### Accounts

Create:

- `User`
- `Plan`
- `SubscriptionStatus`
- `ExternalIdentity`
- `ResolvedUser`

Create ports:

- `UserRepository`
- `ExternalIdentityRepository`
- `SubscriptionRepository`

Invariants:

- External identity is unique by provider and external user ID
- An inactive or missing subscription cannot produce a `UserRuntime`
- Juan's private tool privilege is based only on internal UUID

### Conversations

Move the `ConversationStore` contract out of `harle_agent.models`.

Split operations:

- Load bounded conversation context
- Begin a processing conversation
- Save tool interactions
- Complete the conversation
- Fail the conversation with a safe code
- Count completed monthly conversations

Every method must require a user UUID. Telegram operations also require a chat ID or update ID where relevant.

### Profiles

Create:

- `UserProfile`
- `AssistantProfile`
- `UserProfileStore`
- `AssistantProfileStore`

The prompt receives profiles through the request runtime. Profile modifications use the same direct-versus-proposed authorization rules as expenses and events.

### Expenses

Create domain models using `Decimal`, typed category values, and `date`.

Core operations:

- Add one-time expense
- Add refund
- Add 2–12 installments
- List one or more days
- Summarize one or more months
- Update by transaction UUID
- Cancel by transaction UUID

Pure domain rules:

- Validate amount, currency, category, and installment count
- Apply the user's local transaction date
- Preserve the existing 00:00–04:00 previous-day rule
- Split installment totals deterministically without losing or creating currency fractions
- Calculate refunds as negative contributions to totals while storing positive amounts

Internal transactions should use UUIDs for correction. Matching by amount and spreadsheet cell is retained only by the legacy Google Sheets adapter.

### Internal events

Create:

- `InternalEvent`
- `EventStatus`
- `CreateEvent`
- `UpdateEvent`
- `EventStore`

Core operations:

- List events in a bounded date range
- Create a one-time event
- Update an owned event
- Cancel an owned event
- Soft-delete an owned event

Rules:

- Convert user input to UTC using the profile timezone
- Preserve the originating IANA timezone
- Require end time after start time
- Exclude deleted events from normal reads
- Exclude cancelled events unless explicitly requested
- Do not schedule notifications or background work

### Tools

Replace the fixed `Literal` of tool names with runtime validation against the injected registry.

Create:

- `ToolFamily`
- `ToolEffect`
- `ToolDefinition`
- `ToolExecutionContext`
- `ToolCall`
- `ToolCallResult`
- `ToolRegistry` port
- `ToolClient` or executor port where external communication is needed

Tool effects:

- `read`
- `modify`

Each tool definition declares:

- Name
- Family
- Description
- Typed argument model
- Effect
- Whether concurrent execution is safe
- Handler factory

## Tool Registry and Injector

### Process-scoped registry

The registry contains these version-1 families:

- `internal_expenses`
- `internal_events`
- `profiles`
- `legacy_google_sheets_expenses`

The registry may know all families, but it must not instantiate handlers or clients until the request's authorization policy selects a family.

### Required authorization selection

`ToolAccessPolicy` returns:

```text
Commercial user:
  internal_expenses
  internal_events
  profiles

Juan:
  legacy_google_sheets_expenses
  internal_events
  profiles
```

The policy receives:

- Resolved internal user UUID
- Subscription status
- Plan
- Process setting containing Juan's stable UUID

The policy must default to denial when configuration is missing or inconsistent.

### ToolsInjector responsibilities

`ToolsInjector` must:

1. Resolve authorized families.
2. Reject families unavailable in the current release.
3. Build request-scoped handlers from explicit dependencies.
4. Produce the exact tool-name set accepted for the request.
5. Build the prompt descriptions from only those definitions.
6. Ensure unavailable tool names fail before any client or repository call.
7. Expose family and effect metadata to the authorization service.

Version 1 does not require model-based relevance ranking. It may send all tools from the authorized families because authorization filtering is the security boundary.

## Legacy Google Sheets Isolation

The current implementation constructs `GoogleSheetsClient()` directly inside every expense tool and reads process settings from a Pydantic default factory. This must be removed.

### Configuration

Add:

- `LEGACY_GOOGLE_SHEETS_USER_ID`
- Existing current-year spreadsheet ID
- Existing next-year spreadsheet ID
- Existing base64 service-account JSON

The Google Sheets settings model must be separate from generic agent settings.

Rules:

- Generic application startup may know whether the legacy capability is configured.
- Credentials are decoded only when the configured Juan runtime first requests the family.
- Missing credentials fail Juan's runtime clearly but do not prevent commercial users from starting.
- Credential contents, spreadsheet IDs, formulas, and payloads are never logged.

### Defense in depth

Google Sheets access requires all of these checks:

1. `ToolAccessPolicy` selects the legacy family only for the configured internal UUID.
2. `ToolsInjector` does not expose legacy names or descriptions to another user.
3. The dependency-injection container creates the client only for the configured UUID.
4. `LegacyGoogleSheetsExpenseRepository` verifies the execution context's UUID.
5. Every modifying handler verifies its tool family and authorization context before calling the repository.
6. A direct attempt to execute a legacy tool name for another user returns a safe authorization error without constructing the client.

### Preserved behavior

Move, without semantic changes:

- Formula parsing and rebuilding
- Spreadsheet and worksheet selection
- Category-to-column mapping
- Current-year and next-year spreadsheet handling
- One-time expenses and refunds
- Installment writes
- Daily and monthly reads
- Existing transaction correction behavior

The late-night date rule should move to shared expense domain logic so both expense backends follow it.

### External-write uncertainty

Google Sheets does not provide a transaction that spans the external write and the local audit record.

For Juan's modifying operations:

- Persist an action execution record before calling Google Sheets.
- Do not automatically retry an ambiguous external write.
- Mark a crash or timeout after dispatch as `needs_reconciliation`.
- Require manual reconciliation instead of risking a duplicate formula addition.

Internal PostgreSQL writes do not have this limitation because the data change and audit record can share one database transaction.

## Internal Expense Tool Family

Create handlers:

- `add_expense`
- `add_refund`
- `add_installment_expense`
- `list_expenses`
- `summarize_expenses`
- `update_expense`
- `cancel_expense`

The model receives semantic categories rather than spreadsheet column letters.

Read results must include transaction UUIDs so later corrections are unambiguous.

Write behavior:

- Direct user-requested writes execute after validation.
- Inferred writes become proposed actions.
- Creation, updates, and cancellations write their audit records in the same PostgreSQL transaction.
- Every write accepts an idempotency key derived from update ID, reasoning loop, and tool-call position.

Installment behavior:

- Create one group UUID.
- Create one row per installment.
- First installment uses the supplied date.
- Later installments use the first day of each following month, preserving current behavior.
- Allocate decimal remainder deterministically so row amounts sum exactly to the original amount.

Query behavior:

- Always filter by owner UUID.
- Use explicit user-local date boundaries converted correctly for storage.
- Monthly totals group by semantic category.
- Refunds subtract from totals.
- Cancelled entries are excluded by default.

## Internal Event Tool Family

Create handlers:

- `list_events`
- `create_event`
- `update_event`
- `cancel_event`
- `delete_event`

Read behavior:

- Require a bounded date range.
- Filter by owner UUID.
- Return event UUID, title, description, local start and end, timezone, and status.

Write behavior:

- Validate timezone and interval before persistence.
- Use direct-versus-proposed authorization.
- Audit in the same transaction.
- Use stable idempotency keys.
- Treat `delete_event` as soft deletion in version 1.

No event operation creates a reminder, notification, recurrence, calendar sync, or scheduler job.

## Agent Refactor

### `AgentConfig`

Stop reading settings at import time.

Build an explicit request configuration containing:

- Gemini model
- Maximum retries
- Maximum tool loops
- Conversation context budget
- User identity and locale
- Injected tool definitions

### `AgentRunner`

Split current `Harle` behavior into:

- Context loading
- Prompt construction
- Gemini call
- Structured response validation
- Tool execution
- Conversation completion

The first refactor should preserve the current reason-and-act loop and Google Search grounding.

### Prompt changes

Remove:

- Juan-specific names and tags
- Claims that Harle is a human
- Claims of human feelings or identity
- Global personal-history file access
- Static global tool descriptions
- Debug logging of the complete system prompt

Add:

- User display name and profile
- Assistant profile
- User timezone and current context
- Only authorized tool descriptions
- Explicit read-versus-modify behavior
- Direct-request versus inferred-write rules
- Generic conversation field names

### Tool-call validation

If Gemini emits a tool absent from the request registry:

- Do not retry the tool
- Do not reveal hidden tool names
- Return a safe unavailable-tool result to the reasoning loop
- Record a non-sensitive diagnostic event

## Preflight Services

### IdentityService

Responsibilities:

- Resolve Telegram ID through `external_identities`
- Return a typed user and subscription view
- Never create users implicitly from webhook traffic

### SubscriptionService

Responsibilities:

- Validate plan and subscription status
- Apply stale-state and failed-payment policy
- Support manual beta provisioning and external synchronization

Initial controlled beta:

- `scripts/provision_user.py` creates users and Telegram identities explicitly.
- A signed internal synchronization endpoint may update plan and status from the external account product.

### RateLimitService

Process-local state per Telegram identity:

- Rolling timestamp deque
- `blocked_until`
- Strike count
- Last normal-use time
- Ban-notice state

Rules:

- The tenth valid accepted message in two seconds triggers a ban.
- Cooldowns escalate from at least 60 seconds to 5 minutes and 1 hour.
- Strikes decay after normal use.
- Banned attempts do not reserve quota or invoke Gemini.
- At most one notice is enqueued per cooldown.

Inject a clock so unit tests do not sleep.

### UsageQuotaService

Responsibilities:

- Calculate explicit UTC month boundaries
- Count only completed conversation rows
- Maintain process-local in-flight reservations
- Serialize reserve and release operations per user
- Return remaining requests and reset time

The reservation formula is:

```text
completed_current_month_conversations + in_flight_requests < plan_limit
```

A conversation becomes quota-eligible after the final response and tool results are durably committed and the Telegram response is placed in the outbox. Telegram delivery success does not change quota because provider cost was incurred and delivery is retryable.

## Write Authorization and Proposed Actions

### Direct writes

A direct write:

- Was explicitly requested in the current user message
- Has complete, validated arguments
- Is permitted by the injected tool family

It executes immediately and creates an audit record.

### Inferred writes

An inferred write:

- Was suggested by Harle
- Was inferred from context
- Originated from proactive behavior
- Does not have clear direct authorization in the current message

It creates an expiring proposed action and does not execute.

### Confirmation

The same internal user must confirm the same proposed-action UUID.

The implementation must support:

- Confirmation
- Cancellation
- Expiration
- Duplicate confirmation
- Confirmation after expiration
- Confirmation by another user

Telegram inline buttons are preferred because they bind callback data to the action UUID. Plain-text confirmation may be added only if it cannot ambiguously match multiple pending actions.

## Durable Telegram Processing

### Inbox worker

Replace FastAPI `BackgroundTasks`.

The worker:

- Polls accepted or expired-leased rows
- Claims rows with `FOR UPDATE SKIP LOCKED`
- Assigns a processing lease
- Uses a per-user lock to serialize one user's work
- Requeues work after an expired lease
- Marks final status

### Outbox worker

The worker:

- Claims pending rows
- Sends chunks in order
- Stores Telegram message IDs
- Retries safe transport failures with bounded backoff
- Moves repeated failures to a terminal state for alerting

Telegram does not provide a general idempotency key for `sendMessage`. Duplicate webhook updates are fully deduplicated, but a process crash after Telegram accepts a message and before the local sent status is committed leaves a small duplicate-delivery window. This limitation must be documented and monitored rather than hidden.

### Per-user ordering

Version 1 may use process-local `asyncio.Lock` instances because deployment is one process.

Locks must:

- Be created through a coordinator service
- Be cleaned up after inactivity
- Never contain user content

Inbox durability preserves work across restarts. Distributed ordering is deferred until multiple processes are introduced.

## Profiles, Memory, and Context Injectors

### Profile migration

For Juan:

- Read `data/juan_personal_history.md` once during provisioning.
- Store it in `user_profiles.personal_history`.
- Verify the stored value.
- Stop reading the file at runtime.

For new users:

- Create an empty profile with explicit timezone and locale.

### Context loading

Load concurrently where safe:

- Bounded conversation history
- User profile
- Assistant profile
- Current date and time
- Weather when location is configured
- Relevant internal events when requested

The time/weather injector may cache provider results by rounded location, but user timezone formatting remains request-scoped.

## Privacy and Operational Work

### Logging

Replace message interpolation with structured, non-sensitive fields.

Allowed operational fields:

- Correlation ID
- Internal user UUID
- Telegram update ID
- Plan
- Tool family and name
- Status
- Duration
- Retry count

Forbidden fields:

- Prompt and response bodies
- Personal history
- Profile text
- Expense descriptions
- Event descriptions
- Tool payloads
- Google credentials
- Spreadsheet IDs
- Access tokens

### Safe failures

Introduce typed exceptions:

- Unauthorized identity
- Inactive subscription
- Temporary ban
- Quota exceeded
- Tool unavailable
- Invalid tool arguments
- Provider unavailable
- Persistence failure
- Ambiguous external write

API and Telegram messages must expose safe user text, not raw exception details.

### Privacy services

Create:

- Data export service
- Account deletion service

Export must include:

- Account and identity metadata
- Profiles
- Conversations
- Internal expenses
- Internal events
- Proposed actions and audit history where policy permits

Deletion must:

- Revoke identities first
- Prevent new requests
- Delete or anonymize PostgreSQL-owned data according to policy
- Not delete Juan's external spreadsheet
- Record the deletion workflow without retaining forbidden personal content

### Health and readiness

Keep:

- `GET /healthcheck` as process liveness

Add:

- `GET /ready` checking PostgreSQL connectivity, migration version, and worker state

Readiness must not call Gemini, Telegram, or Google Sheets.

### Metrics and alerts

Track:

- Webhook accepted, rejected, and duplicate counts
- Identity and subscription rejections
- Ban triggers
- Quota rejections
- Gemini latency and failure count
- Tool execution count and failure count by family
- Inbox age and backlog
- Outbox age and backlog
- Ambiguous Google Sheets writes
- PostgreSQL pool saturation

Metrics must contain no user content.

## Existing File Modification Plan

| Existing path | Required change |
| --- | --- |
| `src/harle_api/app.py` | Keep app construction and lifespan; move route logic into routes; remove `BackgroundTasks`; initialize process runtime and workers |
| `src/harle_api/runtime.py` | Remove fixed owner; become temporary compatibility layer over the new process runtime |
| `src/harle_api/assistant.py` | Move orchestration into services messaging processor; accept `UserRuntime` |
| `src/harle_api/telegram.py` | Split payload parsing into API and HTTP sending into infrastructure |
| `src/harle_api/settings.py` | Remove required allowed-user setting; retain only API-specific settings before consolidation |
| `src/harle_agent/agent.py` | Move to `harle_services/agent/runner.py`; remove global settings, tools, personal file, and sensitive prompt logging |
| `src/harle_agent/settings.py` | Split Gemini, legacy Google Sheets, and runtime settings into typed utility/infrastructure settings |
| `src/harle_agent/retry_decorator.py` | Replace name-based retry behavior with explicit retry policies and safe result types |
| `src/harle_agent/environment_knowledge.py` | Move provider work to infrastructure context injector; accept user location/timezone |
| `src/harle_agent/prompts/system.py` | Replace hardcoded identity with parameterized transparent prompt |
| `src/harle_agent/prompts/summary.py` | Either integrate into bounded memory summarization or remove if still unused |
| `src/harle_agent/models/harle_models.py` | Split service DTOs from domain entities; remove import-time settings defaults |
| `src/harle_agent/models/harle_tool.py` | Replace fixed names and untyped arguments with registry-validated typed tool definitions |
| `src/harle_agent/models/conversation_store.py` | Move contract to domain conversations ports |
| `src/harle_agent/models/conversation_record.py` | Move entity to domain conversations models |
| `src/harle_agent/stores/postgres_store.py` | Move to infrastructure repository; remove schema DDL and owner upsert |
| `src/harle_agent/stores/sqlite_store.py` | Move to local infrastructure; mark development-only; use generic prompt keys |
| `src/harle_agent/stores/file_store.py` | Move to local infrastructure; use generic prompt keys |
| `src/harle_agent/tools/__init__.py` | Remove global `TOOLS`; replace with registry bootstrap |
| `src/harle_agent/tools/tools_utils.py` | Move result formatting into service/domain tool modules |
| `src/harle_agent/tools/expenses/one_time_transaction.py` | Move legacy handler behavior behind injected Google Sheets repository |
| `src/harle_agent/tools/expenses/installments_transaction.py` | Move legacy handler behavior behind injected Google Sheets repository |
| `src/harle_agent/tools/expenses/expense_queries.py` | Move legacy queries behind injected Google Sheets repository |
| `src/harle_agent/tools/expenses/transaction_updates.py` | Move legacy correction behind injected Google Sheets repository |
| `src/harle_agent/tools/expenses/shared_prompt.py` | Split semantic expense rules from spreadsheet-specific wording |
| `src/harle_agent/tools/expenses/utils/google_sheets.py` | Move to infrastructure; require explicit settings; remove default settings factory |
| `src/harle_agent/tools/expenses/utils/shared_models.py` | Split semantic expense models into domain and legacy request models into infrastructure |
| `src/harle_agent/tools/expenses/utils/constants.py` | Move semantic categories to domain; keep sheet columns/month names in Google Sheets infrastructure |
| `src/harle_cli/cli.py` | Keep development-only; build an explicit runtime; never infer Juan privileges without an explicit user UUID |
| `src/harle_utils/base_settings.py` | Consolidate into typed settings module |
| `src/harle_utils/logging.py` | Add structured safe logging and remove import-time environment side effects where practical |
| `pyproject.toml` | Add test dependencies and package discovery for new packages; update mypy package list |
| `.pre-commit-config.yaml` | Include all source packages and keep existing quality gates |
| `.env.example` | Remove commercial reliance on `TELEGRAM_ALLOWED_USER_ID`; add legacy UUID and worker/subscription settings; label Sheets variables Juan-only |
| `requirements.txt` | Continue editable install or replace with the selected deployment dependency workflow |
| `README.md` | Later update startup, migration, and commercial configuration after explicit documentation approval |

After migration and verification, remove obsolete `harle_agent` implementation modules rather than maintaining two active architectures.

## New File Introduction Plan

### API

- `src/harle_api/routes/telegram.py`
- `src/harle_api/routes/health.py`
- `src/harle_api/routes/account_sync.py`
- `src/harle_api/routes/privacy.py`
- `src/harle_api/payloads/telegram.py`
- `src/harle_api/payloads/account_sync.py`
- `src/harle_api/payloads/privacy.py`
- `src/harle_api/dependencies.py`
- `src/harle_api/exception_handlers.py`

### Services

- Agent runtime, runner, prompt builder, models, and retry policy
- Identity, subscription, preflight, rate-limit, and quota services
- Tool registry, injector, executor, and authorization
- Internal expense service and handlers
- Internal event service and handlers
- Profile service and handlers
- Proposed-action service and confirmation handling
- Durable message processor and worker
- Export and deletion services
- Bootstrap service used by API and CLI

### Domain

- Account, conversation, profile, expense, event, tool, action, and messaging models
- Ports for every repository and external client
- Pure expense, event, and authorization policies

### Infrastructure

- PostgreSQL pool, transactions, migration runner, repositories, inbox, and outbox
- Google Sheets settings, client, mapping, and repository
- Gemini, Telegram, and weather clients
- Dependency-injection container
- File/SQLite development adapters
- Fakes for provider clients and time

### Root and operations

- Seven versioned SQL migrations
- Migration, provisioning, and restore-verification scripts
- `.github/workflows/ci.yml`
- Focused unit and PostgreSQL integration tests

## Implementation Phases and Review Checkpoints

### Phase 0: Confirm policies and align documentation

Decide:

- Juan uses Sheets instead of internal expenses
- Internal event all-day semantics
- Expense currency policy
- Proposed-action TTL and confirmation UX
- Subscription synchronization mechanism
- Retention and deletion periods

Update `docs/02_FEATURES.md` and `docs/03_SRS.md` before code implementation because they currently imply multi-user Google Sheets and external calendar/reminder behavior in version 1.

Acceptance:

- Product docs, release delta, and this plan describe one release boundary.

### Phase 1: Introduce architecture shells

Steps:

1. Create domain package and typed account/conversation/tool contracts.
2. Create service and infrastructure packages.
3. Add compatibility imports without changing runtime behavior.
4. Update package discovery and type-check configuration.

Acceptance:

- Existing CLI and Telegram paths still run.
- Pre-commit remains green.
- New dependency boundaries have no cycles.

### Phase 2: Add migration system and preserve current data

Steps:

1. Implement migration runner and migration table.
2. Baseline current users and conversations.
3. Add plans and external identities.
4. Backfill current Telegram identity while preserving Juan's UUID.
5. Add conversation status and indexes.
6. Remove startup schema mutation only after migration verification.

Acceptance:

- A copy of the current database migrates without losing users or conversations.
- Re-running migrations changes nothing.
- Startup fails safely on an old schema.

Rollback:

- Restore the pre-migration backup.
- Do not attempt destructive down migrations during beta.

### Phase 3: Resolve identity and isolate conversations

Steps:

1. Implement account repositories.
2. Implement identity and subscription services.
3. Replace the allowed-user gate.
4. Create request-scoped `UserRuntime`.
5. Bind conversation operations to the resolved UUID.
6. Prove two-user isolation.

Acceptance:

- Unknown users never invoke Gemini.
- Two users cannot read or write each other's conversation rows.
- Juan's existing conversation ownership remains unchanged.

### Phase 4: Introduce tool registry and isolate Google Sheets

Steps:

1. Add tool family metadata and runtime name validation.
2. Implement `ToolAccessPolicy`.
3. Implement `ToolsInjector`.
4. Move Google Sheets client construction into infrastructure.
5. Add the configured Juan UUID guard.
6. Migrate existing handlers behind the injected repository.
7. Remove global `TOOLS`.

Acceptance:

- A commercial runtime contains no Sheets tool names, descriptions, handlers, settings, or client.
- A forced Sheets call from a commercial runtime fails before client construction.
- Juan retains current Google Sheets behavior.

### Phase 5: Add internal expense persistence and tools

Steps:

1. Add expense migration and models.
2. Implement expense rules.
3. Implement PostgreSQL expense repository.
4. Implement service methods.
5. Add read tools.
6. Add direct write tools with transaction/audit placeholders.
7. Add installment behavior.
8. Add correction and cancellation.

Acceptance:

- Commercial users can add, query, summarize, update, and cancel only their own expenses.
- Installments sum exactly to the original amount.
- Juan still receives Sheets tools instead of internal expense tools.

### Phase 6: Add internal event persistence and tools

Steps:

1. Add event migration and models.
2. Implement event invariants.
3. Implement PostgreSQL event repository.
4. Add list and create tools.
5. Add update, cancel, and soft-delete tools.

Acceptance:

- Every entitled user can manage only their own events.
- No event creates background or external-calendar work.
- Juan and commercial users receive the same event family.

### Phase 7: Migrate profiles, memory, and prompts

Steps:

1. Add profile migrations and repositories.
2. Seed Juan's personal history.
3. Parameterize system prompt.
4. Load user and assistant profiles.
5. Generalize conversation serialization keys.
6. Remove sensitive prompt logging.

Acceptance:

- No runtime code reads Juan's personal-history file.
- No prompt hardcodes Juan.
- Harle remains warm but does not claim human identity.

### Phase 8: Add authorization, proposed actions, and audit

Steps:

1. Add action migration and repositories.
2. Classify tool effects.
3. Implement direct authorization.
4. Implement proposed-action creation.
5. Implement Telegram confirmation and cancellation.
6. Wrap every modifying family in audit execution.
7. Add ambiguous Google Sheets reconciliation state.

Acceptance:

- Inferred writes never execute immediately.
- Another user cannot confirm an action.
- Duplicate confirmation does not duplicate a write.
- Every successful modification has one audit record.

### Phase 9: Add durable Telegram processing

Steps:

1. Extend Telegram payload model with update ID and callbacks.
2. Add inbox/outbox migration and repositories.
3. Claim updates before preflight work.
4. Replace `BackgroundTasks`.
5. Add inbox worker and leases.
6. Add per-user ordering.
7. Add outbox worker and chunk status.

Acceptance:

- Duplicate update IDs cause no duplicate Gemini call or side effect.
- Accepted pending work resumes after restart.
- Conflicting writes for one user are serialized.

### Phase 10: Add bans and quotas

Steps:

1. Implement injectable clock.
2. Implement rolling safety windows and escalation.
3. Implement quota count query.
4. Implement in-flight reservation.
5. Add rejection responses with remaining usage and reset time.

Acceptance:

- The tenth valid message inside two seconds bans only that identity.
- Banned and over-quota requests do not invoke Gemini.
- Tool-call rows and failed conversations do not consume monthly quota.

### Phase 11: Add account synchronization and privacy workflows

Steps:

1. Add controlled provisioning script.
2. Add signed subscription synchronization endpoint.
3. Add export service.
4. Add account deletion service.
5. Verify cascade and anonymization behavior.

Acceptance:

- External subscription updates are idempotent.
- Deleted users cannot authenticate.
- Export and deletion cover every user-owned PostgreSQL table.

### Phase 12: Add operational hardening and CI

Steps:

1. Add safe structured logging.
2. Add readiness endpoint.
3. Add metrics.
4. Add CI with PostgreSQL.
5. Add backup and restore validation.
6. Correct deployment entrypoints and migration command.
7. Run a two-user controlled beta.

Acceptance:

- CI gates the critical release tests.
- Restore validation has been exercised.
- No sensitive prompt, profile, expense, event, credential, or tool payload appears in logs.

## Essential Test Plan

Tests should remain focused. No function or method needs more than three tests.

### Unit tests

- Expense date and installment rules
- Event interval and timezone rules
- Tool access matrix
- Juan Sheets guard
- Rate-limit escalation and decay
- UTC quota boundaries
- Direct versus proposed authorization
- Prompt construction without unauthorized tools

### Repository integration tests

- Conversation isolation
- Expense isolation and aggregation
- Event isolation and range queries
- Proposed-action ownership
- Audit idempotency
- Inbox deduplication
- Outbox uniqueness
- Migration from the current schema

### Service integration tests

- Unknown and inactive users stop before Gemini
- Commercial user receives internal expenses and events
- Juan receives Sheets expenses and internal events
- Non-Juan Sheets call never constructs the client
- Duplicate update creates one conversation and one side effect
- Banned and over-quota requests do not call Gemini
- Inferred write waits for same-user confirmation
- Restart reclaims accepted inbox work

### Provider fakes

Provide fakes for:

- Gemini
- Telegram
- Google Sheets
- Clock

Fakes must record calls without accepting arbitrary untyped payloads.

## CI Plan

Create `.github/workflows/ci.yml` with:

1. Python setup for the supported version.
2. PostgreSQL service.
3. Editable development install.
4. Migration to latest schema.
5. Pre-commit execution.
6. Focused unit tests.
7. PostgreSQL integration tests.

CI must not require real Gemini, Telegram, Google Sheets, or weather credentials.

## Deployment and Cutover Plan

### Before deployment

1. Create and test a production backup.
2. Record the current Juan user UUID and Telegram ID.
3. Configure `LEGACY_GOOGLE_SHEETS_USER_ID`.
4. Run migration against a restored production snapshot.
5. Verify conversation ownership and row counts.
6. Verify the legacy Sheets negative-access test.

### Deployment

1. Stop accepting webhook traffic or place the service in maintenance.
2. Run versioned migrations.
3. Deploy the new process.
4. Start inbox and outbox workers.
5. Run readiness checks.
6. Re-enable webhook traffic.
7. Manually test Juan.
8. Manually test two commercial beta users.

### Rollback

Use forward-only schema migrations during beta.

If application rollback is required:

- Stop traffic.
- Restore the pre-deployment database backup when the old application cannot safely read the new schema.
- Restore the previous application version.
- Re-register the webhook if needed.

Do not silently recreate tables through application startup.

## Major Risks

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| Incorrect identity backfill | Cross-user data exposure | Preserve UUIDs, compare counts, and block release on isolation tests |
| Google Sheets remains globally registered | Commercial user could modify Juan's spreadsheet | Authorization, injection, DI, repository, and execution guards |
| Existing import-time globals survive | Requests can share user-specific tools or configuration | Remove `TOOLS`, cached owner, client default factories, and personal-history globals |
| Tool name emitted outside registry | Hidden or unauthorized handler execution | Runtime registry validation before lookup |
| External Sheets write has ambiguous outcome | Duplicate or missing expense | No automatic ambiguous retry; reconciliation state |
| Startup DDL remains active | Schema drift and unsafe deployments | Remove after migrations are established |
| Durable worker lease bug | Stuck or duplicate processing | Bounded leases, idempotency keys, and restart tests |
| Process-local quota state resets | Temporary allowance after restart | Accepted first-version limitation; completed DB count remains durable |
| Multiple app processes are started | Rate limits, ordering, and reservations become unsafe | Enforce one process in deployment and readiness metadata |
| Sensitive logs remain | Privacy breach | Remove full-prompt logging and test log output |
| Internal and legacy expense behavior diverges | Inconsistent user experience | Shared domain rules and provider-specific adapter tests |
| Documentation remains inconsistent | Implementation violates approved product scope | Complete Phase 0 before code |

## Open Decisions Required Before Their Phase

1. Whether internal events support all-day events in version 1.
2. Default currency and whether users may select multiple currencies.
3. Whether expense categories are fixed for version 1.
4. Whether Juan can opt into internal expenses later without synchronization.
5. Proposed-action expiration duration.
6. Telegram inline buttons versus text confirmation.
7. Subscription synchronization transport and authentication.
8. Failed-payment grace period.
9. Data export format.
10. Retention periods for conversations, inbox, outbox, cancelled expenses, deleted events, audit records, and backups.
11. Supported production region.
12. Exact metrics and alert thresholds.

These decisions should not block unrelated foundation work, but each must be resolved before implementing the affected behavior.

## Definition of Done

Commercial version 1 is complete only when:

- Telegram identity resolves to a stable internal UUID on every update.
- Unknown or inactive identities never invoke Gemini or a tool.
- Every commercial user receives internal PostgreSQL expenses and events.
- Juan receives internal events and the legacy Google Sheets expense family.
- No other user can see, construct, or execute a Google Sheets tool.
- Conversations, profiles, expenses, events, proposed actions, and audits are isolated by user.
- Duplicate Telegram updates create no duplicate model expense, internal write, external write, response record, or audit entry.
- Modifying tools distinguish direct authorization from inferred proposals.
- Monthly quotas count only completed conversation rows.
- Temporary bans occur before Gemini and quota consumption.
- Accepted work survives process restarts through PostgreSQL inbox and outbox storage.
- Prompts and logs contain no global Juan-specific content.
- Export and deletion cover all user-owned PostgreSQL state.
- Versioned migrations replace startup DDL.
- Critical tests and quality checks run in CI.
- Backup restoration and credential revocation have been exercised.
- Google Sheets multi-user integration and Google Calendar remain absent from the commercial version-1 runtime.
