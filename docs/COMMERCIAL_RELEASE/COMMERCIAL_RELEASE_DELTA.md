# Harle Commercial Multi-User Release Delta

## Scope

The first commercial version is Telegram-only and runs as one FastAPI process.

FastAPI maps Telegram identities to internal Harle users and performs all pre-flight checks. Registration and payment remain in the external product, while the synchronized plan and subscription status are stored on the Harle user record.

The first version includes PostgreSQL-backed internal expense tracking for commercial users and an internal calendar-like event capability for every user. The existing Google Sheets expense tools remain available only to Juan José Farina's stable internal user UUID as a private legacy capability; they are not part of the commercial product.

Multi-user Google Sheets integration and Google Calendar integration are reserved for the second commercial version.

FastAPI shared state is limited to disposable process-level data such as temporary bans and in-flight request counts. Users, plans, conversations, profiles, internal events, and integrations remain in PostgreSQL or request-scoped objects.

Harle remains request-scoped rather than becoming a singleton.

## Current Release Blocker

The current build is not multi-user safe. Although PostgreSQL conversation records contain user IDs, the runtime still resolves every request to one startup owner. Personal history, prompts, spreadsheet configuration, and tool clients also use global or hardcoded user data.

Exposing the current implementation to multiple users could mix personal context or modify the wrong user's external data.

## First-Version Request Flow

1. Telegram calls the FastAPI webhook.
2. FastAPI validates the webhook secret and deduplicates the Telegram `update_id`.
3. FastAPI maps the Telegram user ID to an internal user.
4. FastAPI checks the user's temporary safety-ban state.
5. FastAPI validates subscription status, plan, current-month usage, and in-flight usage.
6. FastAPI builds a request-scoped user runtime.
7. Harle loads only that user's context and authorized tools.
8. Harle generates a response and executes authorized actions.
9. The successful conversation and tool interactions are persisted under the internal user ID.
10. FastAPI sends the response through Telegram.

The pre-flight policy should be encapsulated behind a clear service boundary so it can be extracted into a proxy or gateway in a later architecture version.

## Required Release Work

### Account Identity

**Current:** One global `TELEGRAM_ALLOWED_USER_ID` and one owner UUID are created at startup.

**Required:** Map each Telegram user ID to an internal user UUID through an external identity table and resolve that identity for every update.

### Subscription Entitlement

**Current:** There is no account or subscription check.

**Required:** Store the current plan and subscription status on the user record and synchronize them from the external registration and payment product.

### User-Scoped Runtime

**Current:** The API runtime holds one fixed PostgreSQL owner.

**Required:** Build a user runtime per request containing the resolved user, stores, profile, integration settings, credentials, and permissions.

### Database Lifecycle

**Current:** Tables are created and altered dynamically at application startup.

**Required:** Introduce versioned migrations, ownership constraints, indexes, production backups, and a tested restore procedure.

### Personal Context and Memory

**Current:** Harle loads one global Juan personal-history file and uses a hardcoded prompt identity.

**Required:** Persist a user-owned profile and personal history, retrieve bounded context by user UUID, and provide correction and deletion flows.

### Conversation Isolation

**Current:** PostgreSQL records have `user_id`, but every request uses the same startup owner.

**Required:** Use the resolved user's UUID for every conversation and tool-interaction query and write. Prove isolation through integration tests.

### Internal Expense Persistence

**Current:** Expense data is stored only in Juan José Farina's Google Sheets tracker.

**Required:** Persist commercial users' expense transactions in PostgreSQL under the owning user UUID. Preserve the existing operations for one-time expenses and refunds, installment expenses, daily and monthly queries, and transaction corrections.

Internal expense records must include ownership, amount, currency, category, transaction date, description, status, installment grouping when applicable, and creation and update timestamps. Queries must be indexed by user and transaction date, and every modifying operation must be audited.

### Juan-Only Google Sheets Expenses

**Current:** Spreadsheet IDs, service-account credentials, and Google Sheets tool functions are global.

**Required:** Keep the existing Google Sheets expense implementation only for Juan José Farina's stable internal user UUID. Google Sheets tools must not be constructed, described to the model, or executable for any other user.

The service-account credentials and spreadsheet IDs may remain process configuration for this private capability. A fail-fast authorization guard must verify the configured internal user UUID before creating the Google Sheets client and again before executing a modifying tool. Multi-user Google Sheets credentials, OAuth, onboarding, and storage are not first-version work.

### Internal Event Persistence

**Current:** There is no calendar or event persistence.

**Required:** Persist calendar-like events in PostgreSQL under the owning user UUID. Harle may query events by date range and create, update, cancel, or delete events only after a direct user request or confirmation of a proposed action.

The event model must include ownership, title, description, start time, end time, timezone, status, and creation and update timestamps. Event queries must be indexed by user and start time, and every modifying operation must be audited.

The first version supports passive, one-time events. Recurrence, attendees, reminders, notifications, external synchronization, and proactive event processing remain deferred.

### Write Authorization and Audit

**Current:** Any modifying tool call selected by the model executes immediately.

**Required:** Distinguish direct user requests from inferred modifications. Persist inferred writes as expiring proposed actions and audit every executed change, including internal expenses, internal events, and Juan's legacy Google Sheets changes.

### Telegram Idempotency and Ordering

**Current:** Telegram `update_id` is ignored and requests run as volatile background tasks.

**Required:** Persist and deduplicate update IDs, serialize conflicting work per user, and use durable inbound and outbound processing where accepted work must survive process restarts.

### Anti-Abuse Temporary Bans

**Current:** Every accepted Telegram message can immediately start a Gemini request.

**Required:** Apply the same safety rule to every user and plan:

- The tenth valid assistant message inside any rolling two-second window triggers a temporary ban.
- The ban affects only that Telegram identity.
- The initial cooldown lasts at least 60 seconds.
- Repeated incidents may escalate to 5 minutes and then 1 hour.
- Strikes should decay after normal use.
- Temporarily banned requests do not call Gemini or consume monthly quota.
- Harle sends at most one ban notice per cooldown to avoid response amplification.

The first implementation can keep each user's timestamp deque, `blocked_until`, strike count, and notification state in FastAPI shared state.

### Plan Usage Quotas

**Current:** Users have no durable request allowance or usage check.

**Required:** Compare the limit associated with the user's plan against successful current-month conversations.

Provisional allowances:

| Plan | Requests per month | Approximate daily average |
| --- | ---: | ---: |
| Free | 60 | 2 |
| Basic | 480 | 16 |
| Max | 1,920 | 64 |

Quota accounting rules:

- Deduplicate Telegram `update_id` before checking or consuming quota.
- Count only successful rows where `kind = 'conversation'`.
- Exclude `tool_call` rows, webhook retries, Gemini retries, failed responses, tool loops, and individual tool calls.
- Use explicit UTC month boundaries: `created_at >= month_start` and `created_at < next_month_start`.
- Add a conversation status so only successfully completed responses count.
- Include a process-local in-flight count so concurrent requests cannot all pass the same database count.
- Do not consume quota for malformed, unauthorized, temporarily banned, or operationally rejected requests.
- Return the remaining allowance and exact reset boundary without invoking Gemini.
- Index the query by user, conversation kind, completion status, and creation time.

The effective first-version usage check is:

```text
completed_current_month_conversations + in_flight_requests < plan_limit
```

The quota numbers are provisional. They correspond to approximately 2, 16, and 64 requests per day, but search grounding, tool loops, and prompt size can make requests differ significantly in cost.

### Prompt and Logging Safety

**Current:** The prompt claims human identity, hardcodes Juan, and can log full personal context at debug level.

**Required:** Parameterize user identity, align Harle's transparency with the product vision, remove global personal content, and prevent sensitive prompt logging.

### Privacy Controls

**Current:** There is no retention, export, account deletion, or credential-revocation workflow.

**Required:** Define and implement retention, export, deletion, secret encryption, least privilege, and credential revocation before paid launch.

### Operational Reliability

**Current:** There are no tests or CI workflows, and some raw provider failures can reach users.

**Required:** Add critical isolation and idempotency tests, CI gates, user-safe failures, readiness checks, metrics, alerts, backups, restore validation, and action tracing.

## First-Version FastAPI State

The single FastAPI process may keep the following disposable state in `app.state`:

- Per-user request timestamps for the rolling safety window
- Per-user `blocked_until` values
- Per-user safety strike counts
- Whether the current cooldown notice was already sent
- Per-user in-flight request counts used by quota checks

This state must be accessed through small services such as `RateLimitService` and `UsageQuotaService`, not directly throughout API handlers.

Persistent product state remains in PostgreSQL:

- Users, plan, and subscription status
- Telegram external identities
- User profiles and memories
- Conversations and tool interactions
- Internal expense transactions
- Internal calendar-like events
- Proposed actions and action audits

Juan's private Google Sheets service-account credentials and spreadsheet IDs remain in process configuration and are never exposed to another user's runtime.

## Recommended Implementation Order

### 1. Identity and Persistence Foundation

- Add versioned PostgreSQL migrations.
- Create internal users and Telegram external-identity mapping.
- Store plan and subscription status on users.
- Resolve users and active subscriptions before assistant execution.
- Pass a request-scoped user runtime instead of a startup owner.
- Reach a vertical slice with two manually provisioned test users.

### 2. User-Owned Context and Tools

- Move personal history and profile data from the global file into user-owned storage.
- Parameterize prompts and remove Juan-specific persistence keys.
- Scope conversations, tool interactions, internal expenses, and internal events to user UUID.
- Add a PostgreSQL expense store and internal expense tool family for commercial users.
- Add a PostgreSQL event store and request-driven tools for querying, creating, updating, cancelling, and deleting internal events.
- Add user-scoped tool-family authorization and inject only the tool families permitted for the resolved user.
- Keep the current Google Sheets expense family behind Juan's configured internal user UUID and process-level credentials.

### 3. Action Safety and Durable Delivery

- Implement direct-request versus inferred-write authorization.
- Add proposed actions, expiry, confirmation, cancellation, and action audit.
- Deduplicate Telegram updates.
- Serialize conflicting operations per user.
- Ensure accepted work survives restarts where required.

### 4. Commercial Hardening

- Add automatic per-user cooldowns.
- Add current-month plan quota checks and in-flight reservations.
- Implement retention, export, deletion, credential revocation, and safe logging.
- Add isolation, authorization, idempotency, quota, and failure-path tests in CI.
- Add readiness checks, metrics, alerts, backups, and restore validation.
- Run a controlled multi-user beta before open paid acquisition.

## Product Decisions Required Before Broad Launch

### Subscription Synchronization

Define how the external registration and payment product updates the local plan and subscription status, including stale-state and failed-payment behavior.

### Internal Expense Policy

Define the supported currencies, category customization, installment correction behavior, soft deletion, export format, and whether amounts are stored in their original currency only or also normalized for reporting.

### Juan Legacy Tool Access

Provision and preserve Juan José Farina's stable internal UUID, define how it is configured in each environment, and exercise a negative test proving that every other user is denied the Google Sheets tool family.

### Internal Event Policy

Define timezone and all-day-event behavior, whether users may hard-delete events or only cancel them, and how long cancelled events remain available. Recurrence, attendees, reminders, notifications, and external synchronization are second-version concerns.

### Confirmation Experience

Define Telegram wording or buttons, expiry, cancellation, and how confirmation is bound to the same user and proposed action.

### Data Policy

Define retention, deletion SLA, export format, backup retention, and supported operating region.

### Quota Policy

Confirm plan names, monthly limits, UTC reset behavior, upgrades, downgrades, refunds for internal failures, and whether unused requests carry over.

## Second-Version Google Integrations

The second commercial version adds multi-user Google Sheets and Google Calendar integrations. Each user connects a Google account through OAuth, with encrypted refresh credentials, selected spreadsheet or calendar settings, least-privilege scopes, and a revocation flow.

Harle may read authorized Google data on request and may modify spreadsheets or calendar events only after a direct user request or confirmation of a proposed action. Every modifying operation remains auditable and idempotent.

Before implementation, define whether internal expenses and events remain the sources of truth, Google services become the sources of truth, or the systems synchronize. The design must also define conflict resolution, recurring events, attendee invitations, spreadsheet compatibility, and ownership of OAuth callbacks and token refresh.

## Explicitly Deferred From the First Version

- Multi-message turn aggregation or response cancellation
- Relevance-based tool selection beyond the required per-user authorization filtering
- Proactive scheduling and autonomous check-ins
- Custom reminders and reminder delivery
- Multi-user Google Sheets integration and synchronization
- Google Calendar integration, synchronization, polling, and notifications
- Instagram, WhatsApp, and other communication channels
- Model routing
- Commercial CLI access
- Separate proxy or gateway service
- Redis or another distributed rate-limit store

The first version preserves the current immediate one-message, one-response behavior because Harle's 2–3 second latency is a product advantage.

## Definition of Releasable

- Two users cannot read or modify each other's conversations, profiles, memories, internal expenses, or internal events.
- An unknown, inactive, or unsubscribed Telegram identity never invokes Gemini or any integration.
- A duplicate Telegram update creates no duplicate response, finance change, internal-event change, or audit entry.
- Ten valid messages inside any rolling two-second window temporarily ban only that Telegram identity.
- Temporarily banned attempts do not invoke Gemini or consume monthly quota.
- Monthly quota checks count only successful conversation rows, exclude tool-call rows, include in-flight requests, and expose remaining usage.
- An inferred modifying action waits for confirmation.
- An explicitly requested modifying action is validated and auditable.
- No user other than Juan's configured internal UUID can receive or execute a Google Sheets tool.
- Event queries return only the requesting user's internal events, and every event modification is user-authorized and auditable.
- A process restart does not lose accepted work that was promised to the user.
- Deleting an account removes or anonymizes all user-owned data according to the retention policy.
- Logs and metrics contain no conversation bodies, personal-history content, access tokens, or integration payloads.
- Production backup restoration and credential revocation have both been exercised.

## Recommended Launch Boundary

Launch as a controlled paid beta with:

- Manually verified accounts
- One FastAPI process
- PostgreSQL-only production persistence
- Telegram as the sole channel
- PostgreSQL-backed internal expense tracking for commercial users
- One request-driven, user-scoped internal event capability
- Juan-only legacy Google Sheets expense tracking outside the commercial offering
- Automatic per-user safety bans
- Plan-based monthly quotas

Add a separate gateway, proactive behavior, additional channels, and distributed process state only after the first-version architecture is validated through production usage.
