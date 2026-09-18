# Entity Relationship Diagram

## Scope

This is a conceptual view of Harle's current PostgreSQL model. It aligns with the [SRS](03_SRS.md) and [Project Management Plan](04_PMP.md) while omitting migration-level detail.

```mermaid
erDiagram
    PLAN ||--o{ HARLE_USER : assigns
    HARLE_USER ||--o{ EXTERNAL_IDENTITY : authenticates_with
    HARLE_USER ||--o| USER_PROFILE : has
    HARLE_USER ||--o| ASSISTANT_PROFILE : configures
    HARLE_USER ||--o{ CONVERSATION : owns
    HARLE_USER ||--o{ EXPENSE_TRANSACTION : owns
    HARLE_USER ||--o{ INTERNAL_EVENT : owns
    CONVERSATION o|--o{ TELEGRAM_UPDATE_CLAIM : completes

    PLAN {
        TEXT code PK
        INTEGER monthly_request_limit
        BOOLEAN active
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    HARLE_USER {
        UUID id PK
        TEXT display_name
        TEXT plan_code FK
        TEXT subscription_status
        TIMESTAMPTZ subscription_valid_until
        TIMESTAMPTZ subscription_synced_at
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    EXTERNAL_IDENTITY {
        UUID id PK
        UUID user_id FK
        TEXT provider
        TEXT external_user_id
        TEXT display_name
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    USER_PROFILE {
        UUID user_id PK, FK
        TEXT preferred_name
        TEXT locale
        TEXT timezone
        NUMERIC latitude
        NUMERIC longitude
        TEXT personal_history
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    ASSISTANT_PROFILE {
        UUID user_id PK, FK
        TEXT display_name
        TEXT profile_text
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    CONVERSATION {
        BIGINT id PK
        UUID user_id FK
        BIGINT telegram_chat_id
        BIGINT telegram_update_id
        TEXT prompt
        TEXT response
        TEXT model
        TEXT kind
        TEXT status
        JSONB tool_call_response
        JSONB tool_result
        SMALLINT tool_interaction_index
        TEXT failure_code
        TIMESTAMPTZ created_at
        TIMESTAMPTZ completed_at
    }

    TELEGRAM_UPDATE_CLAIM {
        BIGINT update_id PK
        BIGINT telegram_user_id
        BIGINT telegram_chat_id
        TEXT message_text
        TEXT status
        BIGINT conversation_id FK
        TIMESTAMPTZ claimed_at
        TIMESTAMPTZ updated_at
        TIMESTAMPTZ tool_started_at
        TIMESTAMPTZ delivered_at
    }

    EXPENSE_TRANSACTION {
        UUID id PK
        UUID user_id FK
        TEXT entry_type
        NUMERIC amount
        CHAR currency
        TEXT category
        DATE transaction_date
        TEXT description
        UUID installment_group_id
        SMALLINT installment_number
        SMALLINT installment_count
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    INTERNAL_EVENT {
        UUID id PK
        UUID user_id FK
        TEXT title
        TEXT description
        TIMESTAMPTZ starts_at
        TIMESTAMPTZ ends_at
        TEXT timezone
        BOOLEAN all_day
        TEXT event_type
        TEXT status
        TIMESTAMPTZ notification_window_start
        TIMESTAMPTZ last_notified_at
        JSONB recurrence_rule
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
```

## Relationships

| From | To | Cardinality | Notes |
| --- | --- | --- | --- |
| Plan | Harle user | One to many | Every user references one configured plan. |
| Harle user | External identity | One to many | Provider and external user ID are unique together. Telegram is the current provider. |
| Harle user | User profile | One to zero or one | A profile is required before the runtime can serve the user. |
| Harle user | Assistant profile | One to zero or one | The assistant persona is configured independently for each user. |
| Harle user | Conversation | One to many | Conversation and tool-interaction rows are owned by one user. |
| Harle user | Expense transaction | One to many | Commercial expense data is private to its owner. |
| Harle user | Internal event | One to many | Every event query and mutation is owner-scoped. |
| Conversation | Telegram update claim | Zero or one to many | One aggregated conversation may complete multiple Telegram updates. |

## Entity Semantics

### Accounts and Profiles

- Subscription status is `active`, `inactive`, `past_due`, `cancelled`, or `revoked`.
- An external identity cannot belong to two users for the same provider and external identifier.
- Profiles store user-owned personalization separately from conversation history.
- Latitude and longitude are both present or both absent. Timezones use IANA names.
- Juan's Google Sheets privilege is deployment configuration keyed to his stable user UUID; it is not a database role or display-name property.

### Conversations and Telegram Claims

- Conversation rows use kind `conversation` or `tool_call`.
- Conversation status is `processing`, `completed`, or `failed`; monthly quota counts only completed conversation rows.
- A non-null Telegram update ID identifies a delivered conversation. Tool interactions also require an update-derived identifier and interaction index for complete idempotency.
- Telegram claim status is `received`, `processing`, `tool_started`, `delivering`, `delivered`, `failed`, `rate_limited`, `interrupted`, or `rejected`.
- Telegram update IDs are globally unique for the bot and persist deduplication state across process restarts.

### Expenses

- Amounts are positive with two decimal places and currency is `ARS`.
- Entry type is `expense` or `refund`; refunds contribute negatively to summaries.
- Categories are fixed to rent, essential services, non-essential services, home, transport, outings, shopping, and other.
- Installment fields are all absent or all present. Counts range from 2 to 12, and installment numbers are unique within one user's group.
- Expense deletion is permanent. Selecting one installment for update or deletion affects its complete group.

### Internal Events

- Event status is `active` or `disabled`.
- Event type is `user_event` for the user's agenda or `system_event` for an internal assistant reminder or task.
- Start and end are stored in UTC while the originating IANA timezone is preserved.
- End must follow start. All-day events use local-midnight boundaries.
- Notification windows may start at the event anchor or earlier. Both event types default to a zero-minute lead, and positive values configure a pre-start lead.
- `recurrence_rule` is absent for a one-time event or contains one non-empty `week_days` or `month_days` list. Recurrence is infinite and creates no occurrence rows.
- A recurring event preserves the ordinary event schedule and fields. A missing month day produces no occurrence in that month.
- Successful notification delivery updates `last_notified_at`; failure leaves it unchanged so delivery remains eligible until the occurrence ends.
- Disabling is reversible and suppresses occurrences and notifications. Deletion permanently removes the event.

## Indexes and Constraints

- Conversations are indexed by user, chat, creation time, kind, status, and monthly quota range.
- Delivered conversation update IDs and update-plus-tool-interaction identifiers are unique when present.
- Expenses are indexed by user and transaction date, category, and installment group.
- Events are indexed by user, status, and start time, with partial indexes for active one-time notifications and active recurrence definitions.
- Telegram claims use `update_id` as the primary deduplication key and are indexed by status and update time.
- User-owned entities cascade when their owning user is physically deleted, subject to the future retention and deletion policy.

Recent Telegram media remains outside the PostgreSQL ERD while its twelve-hour retention is best-effort. The process-local store contains only user-scoped Telegram references and compact metadata, never raw image or audio bytes.

## Confirmed Pending Notification-Quota Delta

This target delta is required but is not part of the current PostgreSQL model.

```mermaid
erDiagram
    HARLE_USER ||--o{ EVENT_NOTIFICATION_DELIVERY : owns
    INTERNAL_EVENT o|--o{ EVENT_NOTIFICATION_DELIVERY : produces
    HARLE_USER ||--o{ EVENT_NOTIFICATION_QUOTA_NOTICE : receives

    PLAN {
        INTEGER monthly_notification_limit
    }

    EVENT_NOTIFICATION_DELIVERY {
        UUID id PK
        UUID user_id FK
        UUID event_id FK
        TIMESTAMPTZ occurrence_starts_at
        TIMESTAMPTZ notification_window_start
        TIMESTAMPTZ delivered_at
    }

    EVENT_NOTIFICATION_QUOTA_NOTICE {
        UUID user_id PK, FK
        TIMESTAMPTZ period_starts_at PK
        TEXT status
        TIMESTAMPTZ attempted_at
        TIMESTAMPTZ delivered_at
    }
```

- `PLAN.monthly_notification_limit` is separate from `monthly_request_limit`; the provisional free, basic, and max values are 15, 60, and 240.
- A delivery row represents one successfully delivered `user_event` or `system_event` occurrence. Monthly usage counts `delivered_at` inside inclusive-start and exclusive-end UTC boundaries.
- The event identifier, occurrence start, and notification window are unique together so a successful occurrence cannot consume allowance twice.
- Deleting an event sets the ledger's event reference to null instead of deleting its usage. Deleting the owning account removes its delivery and notice records under the account-deletion policy.
- The notice marker permits at most one static, non-Gemini quota-exhausted notice attempt per user and UTC month. It consumes neither conversation nor event-notification allowance.
- Process-local in-flight reservations remain outside PostgreSQL while deployment is limited to one process. Durable distributed reservations belong with later queue and worker design.

## Out Of Scope For This ERD

- Proposed actions and action audits
- Durable Telegram inbox and outbox queues
- Notification preferences and durable scheduler or delivery records beyond the confirmed quota ledger and notice marker
- OAuth credentials and multi-user Google integrations
- External registration, payment, and web-interface data
