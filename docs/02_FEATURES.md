# Features

## Current Product

- **Prompt CLI**: The user can send a prompt to Harle from the terminal and receive a direct AI response.
- **Shared assistant engine**: The CLI and Telegram bot use the same assistant behavior, tools, memory, and model configuration.
- **Telegram assistant**: The user can talk to Harle from a private Telegram bot, with webhook-based message handling and replies sent back to the same chat.
- **Allowed-user access**: Telegram messages are accepted only from the configured allowed user.
- **Conversation persistence**: Harle stores conversations and reloads recent context before answering, so responses can account for previous exchanges.
- **Local and remote storage**: Conversations can be stored locally for development or persisted remotely through PostgreSQL for production usage.
- **Personal history context**: Harle can load a curated personal history file and use it to understand the user beyond the latest message.
- **Current context awareness**: Harle receives the current date, time, and weather for the user's local environment before responding.
- **Search-grounded answers**: Harle can use Google Search grounding when answering prompts that benefit from current information.
- **Concise conversational style**: Harle responds in the same language as the user and prefers short, natural answers unless more detail is truly needed.
- **Tool reasoning loop**: Harle can decide whether to answer directly or call an available tool, then continue reasoning with the tool result.
- **One-time expense tracking**: Harle can add one-time expenses or refunds to the user's Google Sheets finance tracker.
- **Installment expense tracking**: Harle can split a purchase into 2 to 12 monthly installments and update the corresponding monthly sheets.
- **Expense categories**: Harle supports the current finance categories for rent, essential services, non-essential services, home, transport, outings, shopping, and other expenses.
- **Expense lookup**: Harle can read expenses for a given day or month from the user's spreadsheet.
- **Expense correction**: Harle can remove or update an existing transaction when the user identifies the transaction to change.
- **Expense date handling**: Harle applies the existing rule for late-night or early-day transactions and tells the user when it assigns the transaction to the previous day.

## Product MVP

- **Fast personal assistant**: Harle should optimize for the fastest useful response that still feels thoughtful and trustworthy.
- **Low-cost usage**: Harle should be cheap enough for frequent everyday use, choosing efficient models, prompts, memory, and tool calls.
- **Multi-user subscription product**: Harle should become available to multiple subscribed users as soon as possible, with isolated data, memory, tools, and permissions per user.
- **Evolving user profile**: Harle should build and maintain a structured perception of the user's preferences, goals, routines, worries, communication style, and important life context.
- **Agent profile**: Harle should have its own configurable profile that can evolve under the user's direction without pretending to be a human.
- **Long-term memory**: Harle should preserve all prior conversations, durable facts, user-provided personal history, and learned patterns separately from short-term conversation context.
- **Memory control**: The user should be able to inspect, correct, delete, or refine what Harle remembers.
- **Safety and privacy**: Harle should protect user data, keep personal context private, and treat safety as a core product capability.
- **Human conversation style**: Harle should feel warm, personal, and natural without becoming verbose or performative.
- **Proactive check-ins**: Harle should be able to follow up on tasks, situations, habits, or emotional context when doing so would help the user.
- **Personal finance**: Harle should help users manage personal finances through natural conversation and connected finance tools.
- **Productivity support**: Harle should provide at least one strong productivity capability for the first paid product, such as custom reminders or calendar integration.
- **General companionship**: Harle should help the user feel better, reflect, stay organized, and improve their life while staying within healthy assistant boundaries.
- **Read without confirmation**: Harle may read or query connected tools such as expenses, reminders, or calendar data without explicit confirmation when the user asks a question.
- **Confirm before modification**: Harle must ask for explicit confirmation before modifying its environment, including expenses, reminders, calendar events, profiles, memories, or other user data.
- **Telegram-first access**: Harle should use Telegram as the only first-product chat interface while the landing page, registration, payment gateways, and web interface are handled by a separate project.
- **Reliable tool execution**: Harle should report what changed after confirmed actions and fail clearly when an action cannot be completed.

## Possible Later Features

- **Autonomous action scheduler**: Harle may run scheduled background thoughts or checks that create useful follow-ups without requiring a new user message.
- **WhatsApp integration**: Harle should eventually support WhatsApp because of its broader market reach.
- **Additional communication channels**: Harle may later support voice, email, or native mobile surfaces if they improve everyday access.
- **Broader personal integrations**: Harle may integrate with email, notes, documents, task managers, banking exports, health data, or other services that help manage the user's life.
- **User-specific customization UI**: Harle may include a simple interface for editing preferences, memories, integrations, and notification rules.
- **Model routing**: Harle may route work across different models based on cost, latency, complexity, and required quality.

## Intentionally Out Of Scope

- **Generic model playground**: Harle should not become a tool for comparing models, tweaking prompts, or experimenting with AI APIs as the main product experience.
- **Cluttered productivity dashboard**: Harle should not become a heavy dashboard where the user has to manage the assistant manually.
- **First-product web platform**: The first Harle product should not include the landing page, registration, payments, or web interface inside this repository.
- **Feature volume for its own sake**: New integrations should not be added unless they make the assistant more useful in real life.
- **Manipulative human simulation**: Harle should not hide that it is AI, create dependency, or use human-like behavior in ways that reduce the user's agency.
- **Unbounded autonomy**: Harle should not take important actions without appropriate user control, confirmation, or recoverability.
- **Medical or psychological authority**: Harle should not act as a doctor, psychologist, therapist, or clinical authority.

## Needs Product Discovery

- **Privacy requirements**: Define the technical, legal, and product requirements needed to make user data safe and private.
- **Subscription boundaries**: Define what is included in each subscription, usage limits, trial behavior, and cancellation behavior.
- **Confirmation flow**: Define the exact user experience for approving environment modifications from Telegram.
- **Memory policy**: Define what Harle stores automatically, what requires explicit consent, and how users can review or delete memory.
- **First productivity feature**: Decide whether the first paid product should prioritize custom reminders, calendar integration, or both.
