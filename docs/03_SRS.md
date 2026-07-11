# Software Requirements Specification

## Introduction

Harle is a Telegram-first AI assistant product that should become fast, low-cost, safe, private, deeply personal, and useful for multiple subscribed users. This SRS is based on [the vision](01_VISION.md), [the feature scope](02_FEATURES.md), the current CLI/API implementation, and the product decisions confirmed so far.

This repository owns the assistant engine, Telegram runtime, memory, user data handling, and life-management tools. A separate project owns landing pages, registration, payment gateways, and web interfaces. Harle must integrate with that external product boundary without duplicating it.

## Environment

- Users interact with Harle primarily through Telegram from mobile devices.
- Users may share sensitive personal information, personal history, financial data, routines, goals, worries, and emotional context.
- The product is intended to serve multiple subscribed users, each with isolated data, configuration, tools, memories, and permissions.
- Subscription, account registration, payment flows, and web UI are handled by a separate system.
- Telegram is the only first-product chat channel. WhatsApp is a future channel because of broader market reach.
- Harle uses an AI model provider for reasoning and response generation, currently Gemini through the official Google API.
- Harle can use Google Search grounding for current information when needed.
- Harle can query real-world context such as current date, time, and weather.
- Harle can connect to external user tools, currently Google Sheets for personal finance and later reminders or calendar systems.
- Some connected tools are read-only in effect, while others modify user data or external services.
- Users expect Harle to be human in tone while remaining transparent that it is AI.
- Users may rely on Harle for companionship and life improvement, but Harle must not act as a doctor, psychologist, therapist, or clinical authority.
- The current implementation supports a single configured Telegram user, local or PostgreSQL conversation persistence, CLI usage, and Google Sheets expense tools.

## User Requirements

- **UR-01 Telegram access**: A subscribed user shall be able to talk to Harle through Telegram.
- **UR-02 Multi-user isolation**: Each user shall experience Harle as a private personal assistant with isolated conversations, profile data, tools, credentials, and preferences.
- **UR-03 Natural conversation**: Harle shall respond in the user's language with a concise, natural, warm, and useful style.
- **UR-04 Personal memory**: Harle shall remember prior conversations, user-provided personal history, durable facts, preferences, routines, goals, and learned patterns.
- **UR-05 User profile**: Harle shall maintain a profile of the user that improves personalization over time.
- **UR-06 Agent profile**: Harle shall maintain its own configurable assistant profile, changeable under user direction, without pretending to be human.
- **UR-07 Memory control**: The user shall be able to inspect, correct, delete, and refine memory, user profile data, and agent profile data.
- **UR-08 Read without confirmation**: Harle may read or query connected data when the user asks a question and the action does not modify the environment.
- **UR-09 Confirmation before modification**: Harle shall never modify expenses, reminders, calendar events, memories, profiles, or external services without explicit user confirmation.
- **UR-10 Personal finance**: Harle shall help users query, add, correct, and understand personal finance data through natural conversation.
- **UR-11 Productivity support**: Harle shall provide at least one first-product productivity capability, either custom reminders, calendar integration, or both.
- **UR-12 Companionship**: Harle shall help users feel better, reflect, stay organized, and improve their lives while respecting healthy relationship boundaries.
- **UR-13 Proactive support**: Harle shall be able to follow up, remind, or check in when the user has enabled that behavior and the follow-up is useful.
- **UR-14 Privacy and safety**: Harle shall protect user data, minimize unnecessary exposure, and make safety a core product behavior.
- **UR-15 Transparency**: Harle shall not hide that it is AI or simulate human identity in manipulative ways.
- **UR-16 Reliability**: Harle shall report failures clearly when it cannot answer or complete a requested action.
- **UR-17 Efficiency**: Harle shall pursue fast and inexpensive responses suitable for frequent daily use.

## System Specification

### Identity, Access, and Subscription

- **FR-01**: The Telegram webhook shall validate Telegram's webhook secret before processing any update.
- **FR-02**: The system shall extract Telegram chat ID, Telegram user ID, display name, and text from incoming Telegram updates.
- **FR-03**: The system shall reject empty, unsupported, malformed, unauthorized, or unsubscribed messages without invoking the assistant engine.
- **FR-04**: The single `TELEGRAM_ALLOWED_USER_ID` model shall be replaced or extended with a multi-user account registry.
- **FR-05**: The system shall map each allowed Telegram user to one internal user account.
- **FR-06**: The system shall consume subscription state from the external registration and payment product.
- **FR-07**: The system shall deny assistant access when a user's subscription is inactive, expired, missing, or revoked.
- **FR-08**: User credentials and connected tool settings shall be scoped to the internal user account, not to global process configuration.

### Conversation Runtime

- **FR-09**: The Telegram runtime shall send a typing action before generating a response when possible.
- **FR-10**: The assistant engine shall load conversation context, user profile, agent profile, personal history, current date and time, and relevant environmental context before answering.
- **FR-11**: Context loading should run concurrently where safe, so slow data sources do not unnecessarily delay the response.
- **FR-12**: The assistant shall choose between answering directly and calling an available tool.
- **FR-13**: The assistant shall execute at most a configured number of reasoning and tool loops for one user message.
- **FR-14**: The assistant shall return a user-facing failure message when model output is invalid, unavailable, or cannot be parsed.
- **FR-15**: The Telegram runtime shall split long responses into Telegram-compatible message chunks.
- **FR-16**: The system shall persist the final user prompt and assistant response after each handled conversation.

### Memory and Profiles

- **FR-17**: The system shall persist all prior conversations in durable storage for product users.
- **FR-18**: The system shall make prior conversations available to Harle through retrieval, summarization, or another bounded-context strategy.
- **FR-19**: The system shall store user profile data separately from raw conversation history.
- **FR-20**: The system shall store agent profile data separately from user profile data.
- **FR-21**: The system shall preserve user-provided personal history as first-class memory.
- **FR-22**: The system shall provide commands or flows for users to view, correct, delete, and refine stored memory.
- **FR-23**: The system shall require confirmation before changing user memory, user profile data, or agent profile data.
- **FR-24**: Memory retrieval shall respect per-user isolation and must never include another user's data.

### Confirmation and Tool Safety

- **FR-25**: Every tool shall declare whether it is read-only or environment-modifying.
- **FR-26**: Read-only tools may run after a user request without an additional confirmation step.
- **FR-27**: Environment-modifying tools shall produce a pending action instead of executing immediately.
- **FR-28**: A pending action shall include the proposed change, affected service, affected data, and a clear confirmation prompt.
- **FR-29**: The system shall execute a pending action only after the same user explicitly confirms it.
- **FR-30**: Pending actions shall expire or be cancellable to avoid accidental later execution.
- **FR-31**: After execution, Harle shall report what changed and whether the operation succeeded.
- **FR-32**: Failed tool actions shall return a clear explanation and should not silently retry in ways that risk duplicate writes.
- **FR-33**: Tool results shall be included in the assistant's reasoning context for the current response.

### Personal Finance

- **FR-34**: Harle shall query a user's finance data for a specific day.
- **FR-35**: Harle shall query a user's finance data for a specific month.
- **FR-36**: Harle shall add one-time expenses and refunds after explicit confirmation.
- **FR-37**: Harle shall add installment purchases from 2 to 12 installments after explicit confirmation.
- **FR-38**: Harle shall remove or update an existing transaction after explicit confirmation.
- **FR-39**: Harle shall support the current expense categories for rent, essential services, non-essential services, home, transport, outings, shopping, and other expenses.
- **FR-40**: Harle shall apply the product-defined date handling rule for late-night or early-day transactions and tell the user when it assigns an expense to the previous day.
- **FR-41**: Finance tools shall validate amounts, dates, months, categories, refund flags, and installment counts before proposing or executing changes.
- **FR-42**: Finance tools shall not modify spreadsheet cells outside the configured expense ranges.
- **FR-43**: Finance tool credentials and spreadsheet IDs shall be user-scoped before multi-user release.

### Productivity

- **FR-44**: The first paid product shall include custom reminders, calendar integration, or both.
- **FR-45**: Harle may query reminders or calendar data without confirmation when answering a user's question.
- **FR-46**: Harle shall require explicit confirmation before creating, updating, deleting, or rescheduling reminders or calendar events.
- **FR-47**: Reminder notifications and proactive check-ins shall respect user preferences, quiet periods, and opt-in settings.
- **FR-48**: Calendar or reminder integrations shall be user-scoped and revocable.

### Companionship and Safety

- **FR-49**: Harle shall preserve a warm, useful, concise, and non-performative conversation style.
- **FR-50**: Harle shall be transparent that it is AI when identity or nature is relevant.
- **FR-51**: Harle shall not claim to be a human, doctor, psychologist, therapist, lawyer, financial advisor, or other professional authority.
- **FR-52**: Harle shall encourage appropriate human or professional help when user needs exceed the assistant's role.
- **FR-53**: Harle shall avoid manipulative behavior, dependency-building patterns, and advice that reduces user agency.
- **FR-54**: Harle shall allow proactive check-ins only when they are user-enabled, useful, and bounded by notification preferences.

### Nonfunctional Requirements

- **NFR-01 Privacy**: User data shall be private by default and isolated by account.
- **NFR-02 Security**: Secrets shall be loaded from secure configuration and never committed to source control.
- **NFR-03 Least privilege**: External tool credentials shall request the minimum practical permissions.
- **NFR-04 Auditability**: Environment-modifying actions shall be auditable with user, timestamp, proposed action, confirmation, and final result.
- **NFR-05 Sensitive logging**: Logs shall avoid storing full personal conversations, private profile content, credentials, or unnecessary tool payloads.
- **NFR-06 Transport security**: Production traffic shall use HTTPS and secure webhook configuration.
- **NFR-07 Data durability**: Product conversation data shall use durable storage, backups, and migration-safe schemas.
- **NFR-08 Data deletion**: The system shall support user data deletion consistent with the product's privacy policy.
- **NFR-09 Latency**: The system shall minimize user-perceived latency through concurrency, caching, concise prompts, and efficient model selection.
- **NFR-10 Cost**: The system shall minimize token usage and external API cost without degrading useful answer quality.
- **NFR-11 Reliability**: The system shall handle provider failures, malformed model output, Telegram failures, and tool failures gracefully.
- **NFR-12 Maintainability**: Assistant, API, storage, and tools shall remain modular enough to add new integrations without creating a brittle tool collection.
- **NFR-13 Observability**: Production operations shall expose enough logs, metrics, and health checks to detect failures and cost regressions.
- **NFR-14 Compliance discovery**: Legal, privacy, and security obligations for storing sensitive user data shall be investigated before broad paid release.

## Program

Harle is conceptually divided into five program areas:

- **Telegram interface**: Receives Telegram webhook updates, validates access, extracts messages, sends typing indicators, sends responses, and enforces Telegram message limits.
- **Assistant engine**: Builds the assistant context, calls the model, parses structured model output, decides whether to respond or call tools, caps tool loops, and returns final text.
- **Memory and profile stores**: Persist conversations, retrieve bounded context, store durable user profile data, store agent profile data, and support user-controlled memory operations.
- **Tool system**: Defines available tools, classifies them as read-only or modifying, validates arguments, handles confirmation flows, executes approved actions, and returns structured results.
- **External integrations**: Connects to AI providers, Telegram, PostgreSQL, Google Sheets, future productivity services, weather data, and external account or subscription systems.

The current code already contains the assistant engine, Telegram webhook, CLI entry point, local and PostgreSQL conversation storage, weather context, Google Search grounding, and Google Sheets finance tools. The main product gaps are multi-user account mapping, subscription entitlement checks, user-scoped credentials, explicit write confirmations, durable memory/profile management, privacy controls, and the first productivity integration.

The expected message flow is:

1. Telegram sends an update to the webhook.
2. The API validates the webhook secret and parses the text message.
3. The API resolves the Telegram user to an active subscribed Harle account.
4. The runtime builds user-scoped stores and tool configuration.
5. Harle loads relevant memory, profile data, current context, and available tools.
6. Harle calls the model and either responds or proposes a tool action.
7. Read-only actions may execute immediately; modifying actions become pending confirmations.
8. Harle sends the final response through Telegram.
9. The system persists the conversation and any confirmed action record.

## Machine

The current machine environment is Python 3.10 or newer with FastAPI, Uvicorn, Pydantic, asyncpg, httpx, google-genai, gspread, and Google service account authentication.

Runtime dependencies include:

- **Telegram Bot API** for webhook delivery and message sending.
- **Gemini API** for assistant reasoning and generation.
- **Google Search grounding** through the configured model provider.
- **PostgreSQL** for durable production storage.
- **SQLite** for local development or temporary fallback storage.
- **Google Sheets API** for current personal finance tools.
- **Open-Meteo** for current weather context.
- **Future productivity providers** for reminders or calendar data.
- **External product system** for registration, subscription, and payment status.

Production deployment shall provide:

- Secure environment variable management for API keys, Telegram secrets, database URLs, and service credentials.
- Durable PostgreSQL storage with schema migrations and backups.
- A webhook endpoint reachable through HTTPS.
- Health checks for platform availability.
- Connection pooling appropriate for expected user count.
- Monitoring for request failures, provider failures, latency, token usage, and tool execution failures.
- A strategy for scaling beyond a single personal bot configuration.

Open requirements that need product discovery:

- Exact privacy and legal requirements for storing conversations, profiles, personal history, and finance data.
- Subscription plan boundaries, usage limits, free trials, failed payments, and cancellation behavior.
- Telegram confirmation UX for approving, cancelling, and expiring pending modifications.
- The first productivity feature decision: custom reminders, calendar integration, or both.
- Data retention, deletion, export, and backup policies.
- Concrete latency, cost, and reliability targets for paid launch.
- WhatsApp integration requirements for a later product phase.
