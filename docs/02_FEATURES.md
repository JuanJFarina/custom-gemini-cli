# Features

## Current Product

- **Prompt CLI**: A local development user can send prompts from the terminal and receive direct AI responses with file-backed conversation history.
- **Telegram assistant**: Subscribed beta users can talk to Harle through a private Telegram bot backed by one FastAPI process.
- **Shared assistant engine**: The CLI and Telegram paths share the assistant behavior, model integration, memory contract, and tool reasoning loop.
- **Multi-user access**: Every Telegram update resolves the sender to a manually provisioned internal account with an active plan and subscription.
- **User isolation**: Conversations, profiles, personal history, tools, permissions, expenses, and events are scoped to the resolved internal user UUID.
- **Conversation persistence**: Telegram conversations and tool interactions use PostgreSQL; recent user-owned context is loaded before answering.
- **User and assistant profiles**: PostgreSQL stores each user's identity, locale, timezone, location, personal history, and assistant profile separately.
- **Current context awareness**: Harle receives the current date, time, and weather for the user's local environment before responding.
- **Search-grounded answers**: Harle can use Google Search grounding when answering prompts that benefit from current information.
- **Concise conversational style**: Harle responds in the same language as the user and prefers short, natural answers unless more detail is truly needed.
- **Tool reasoning loop**: Harle can decide whether to answer directly or call an available tool, then continue reasoning with the tool result.
- **Selective tool loading**: A registry authorizes tool families per user, then selects likely expense or event families through explicit English and Spanish terms, falling back to all authorized families when no term matches.
- **Direct modification policy**: Modifying tools are instructed to execute only when the current user message directly requests the change.
- **Commercial expense tracking**: Commercial users can add expenses and refunds, split purchases into 2 to 12 installments, query a day, summarize a month, update a transaction or installment group, and permanently delete it.
- **Expense policy**: Commercial expenses use Argentine pesos and fixed categories for rent, essential services, non-essential services, home, transport, outings, shopping, and other expenses.
- **Expense date handling**: Transactions without an explicit date use the previous local day from 00:00 through 04:59, and Harle reports when this rule was applied.
- **Juan-only Google Sheets expenses**: Juan's stable internal UUID receives the existing private Google Sheets expense family instead of commercial PostgreSQL expenses.
- **Internal events**: Every entitled user can list, create, update, cancel, and permanently delete private one-time timed or all-day events.
- **Event policy**: Events preserve an IANA timezone, store UTC boundaries, hide cancelled events from normal reads, and create no reminders, notifications, recurrence, attendees, external synchronization, or background work.
- **Telegram deduplication**: Every Telegram `update_id` is persisted before assistant work so webhook retries do not create a second conversation or tool change.
- **Ordered message aggregation**: Consecutive messages join the active turn while reasoning is safe to restart; messages received after tool execution or delivery begins become the next turn.
- **Temporary safety bans**: The tenth valid message within two seconds triggers a per-identity cooldown that escalates from 60 seconds to 5 minutes and then 1 hour, with strike decay and at most one notice per cooldown.
- **Plan quotas**: Current-month completed conversations are limited by the user's configured plan, with UTC reset boundaries and in-flight reservations. The provisional free, basic, and max limits are 60, 480, and 1,920 monthly conversations.

## Pending Product MVP

- **Fast personal assistant**: Harle should optimize for the fastest useful response that still feels thoughtful and trustworthy.
- **Low-cost usage**: Harle should be cheap enough for frequent everyday use, choosing efficient models, prompts, memory, and tool calls.
- **User-scoped integrations**: Connected tools, credentials, polling context, stores, reminders, and permissions should belong to one user account and never leak across users.
- **Evolving user profile**: Harle should build and maintain a structured perception of the user's preferences, goals, routines, worries, communication style, and important life context.
- **Agent profile**: Harle should have its own configurable profile that can evolve under the user's direction without claiming to be human.
- **Long-term memory**: Harle should preserve all prior conversations, durable facts, user-provided personal history, and learned patterns separately from short-term conversation context.
- **Memory control**: The user should be able to inspect, correct, delete, or refine what Harle remembers.
- **Safety and privacy**: Harle should protect user data, keep personal context private, and treat safety as a core product capability.
- **Human conversation style**: Harle should feel warm, personal, and natural without becoming verbose or performative.
- **Personal finance**: Harle should help users manage personal finances through natural conversation and connected finance tools.
- **Productivity support**: Harle should build on internal events with reminders, notifications, or calendar integration when those capabilities have clear ownership and delivery guarantees.
- **General companionship**: Harle should help the user feel better, reflect, stay organized, and improve their life while staying within healthy assistant boundaries.
- **Read on request**: Harle may read or query connected tools such as expenses, reminders, or calendar data when the user asks a question.
- **User-authorized modifications**: Harle may modify expenses, reminders, calendar events, profiles, memories, or other user data when the user directly asks for that modification. If Harle infers, suggests, or initiates a modification itself, it must ask the user first.
- **Confirmation and audit**: Inferred modifications should become expiring proposed actions that the same user can confirm or cancel, and every executed modification should be auditable.
- **Automated subscription synchronization**: Harle should receive current plan and subscription state safely from the external registration and payment product.
- **Privacy controls**: Users should be able to export and delete their data according to defined retention, backup, and deletion policies.
- **Durable accepted work**: Work accepted from Telegram should survive process restarts without duplicate side effects or duplicate responses where the provider permits it.
- **Operational readiness**: Broad release requires automated quality gates, readiness checks, safe metrics and logs, backups, and exercised restoration.

## Possible Later Features

- **Autonomous action scheduler**: Harle may run scheduled background thoughts or checks that wake eligible agents at bounded intervals and create useful follow-ups without requiring a new user message.
- **Proactive check-ins**: Harle may follow up on tasks, situations, habits, or emotional context when the user enables it and notification preferences allow it.
- **External context injectors**: Harle may use cached or polled context providers for data such as weather, location, reminders, calendars, or other user-authorized topics.
- **Durable background queues**: Harle may use durable queues for scheduled agent wakeups, outbound messages, proposed actions, and integration polling when reliability requires it.
- **Multi-user Google integrations**: Users may connect Google Sheets or Google Calendar through OAuth with encrypted, revocable credentials after source-of-truth and synchronization rules are defined.
- **WhatsApp integration**: Harle should eventually support WhatsApp because of its broader market reach.
- **Additional communication channels**: Harle may later support voice, email, or native mobile surfaces if they improve everyday access.
- **Broader personal integrations**: Harle may integrate with email, notes, documents, task managers, banking exports, health data, or other services that help manage the user's life.
- **User-specific customization UI**: Harle may include a simple interface for editing preferences, memories, integrations, and notification rules.
- **Model routing**: Harle may route work across different models based on cost, latency, complexity, and required quality.

## Intentionally Out Of Scope

- **Generic model playground**: Harle should not become a tool for comparing models, tweaking prompts, or experimenting with AI APIs as the main product experience.
- **Cluttered productivity dashboard**: Harle should not become a heavy dashboard where the user has to manage the assistant manually.
- **First-product web platform**: The first Harle product should not include the landing page, registration, payments, or web interface inside this repository.
- **Commercial CLI access**: The CLI remains a development interface rather than a subscribed product channel.
- **Feature volume for its own sake**: New integrations should not be added unless they make the assistant more useful in real life.
- **Manipulative human simulation**: Harle should not hide that it is AI, create dependency, or use human-like behavior in ways that reduce the user's agency.
- **Unbounded autonomy**: Harle should not take important actions without appropriate user control, authorization, or recoverability.
- **Medical or psychological authority**: Harle should not act as a doctor, psychologist, therapist, or clinical authority.

## Needs Product Discovery

- **Privacy requirements**: Define the technical, legal, and product requirements needed to make user data safe and private.
- **Subscription boundaries**: Define what is included in each subscription, usage limits, trial behavior, and cancellation behavior.
- **Confirmation flow**: Define the exact user experience for approving environment modifications from Telegram.
- **Memory policy**: Define what Harle stores automatically, what requires explicit consent, and how users can review or delete memory.
- **Data lifecycle**: Define retention periods, deletion SLA, export format, backup retention, supported operating region, and credential revocation.
- **Quota policy**: Confirm plan names, final limits, upgrades, downgrades, failed-payment behavior, and whether unused requests carry over.
- **Google source of truth**: Decide whether internal expenses and events remain authoritative after multi-user Google integrations are introduced.
