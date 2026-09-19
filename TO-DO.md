# Implementation Handoff

Implement the subscription-period, scheduled-message, and interaction-event design documented in:

- `docs/02_FEATURES.md`
- `docs/03_SRS.md`, especially FR-109 through FR-120
- `docs/04_PMP.md`
- `docs/05_ERD.md`

Do not redesign these decisions during implementation. Work only in the primary `/workspace` project, not the nested `custom-gemini-cli` copy.

## Current Behavior

- Conversation and event-notification quotas use UTC calendar months.
- Users do not store exact subscription-period boundaries.
- `AgentsScheduler` processes only timed `user_event` and `system_event` occurrences.
- Scheduled notifications reuse the core agent and load profiles, conversation history, weather, and Google Search grounding.
- Scheduled notifications currently receive an empty application-tool store.
- Delivered scheduled notifications are not persisted in conversation history.
- Ordinary internal events can be disabled, re-enabled, and permanently deleted.
- Conversation history supports `conversation` and `tool_call` rows, but no standalone assistant message.

## Required Subscription Changes

- Add exact UTC `subscription_period_starts_at` and `subscription_period_ends_at` values for every subscribed user.
- Treat these as current-period boundaries synchronized from the external account product.
- Keep `subscription_valid_until` as a separate access-expiration value.
- Validate that the period start precedes the period end.
- Use the start inclusively and the end exclusively for both conversation and event-notification quota calculations.
- Do not derive periods from account creation, an original subscription date, or UTC calendar months.
- Update account models, PostgreSQL mapping, schema validation, provisioning, quota status, reset messages, and integration tests.
- Provide an explicit safe migration/backfill strategy for existing users.

## Required Scheduled-Message Changes

- Persist every successfully delivered `user_event`, `system_event`, and `interaction_event` message as a standalone assistant message.
- Do not fabricate or store a synthetic user prompt.
- Add an explicit history representation such as `kind = 'scheduled_message'`.
- Include scheduled messages in later model context.
- Exclude scheduled messages from conversation quota.
- Persist read-only tool interactions from scheduled runs through the existing tool-interaction history contract.
- Persist scheduled output only after successful Telegram delivery.
- Failed generation or delivery must create no scheduled history message.

The current conversation schema requires a prompt. Change the persistence contract so a scheduled assistant message can genuinely have no user prompt instead of representing one with misleading text.

## Interaction Event

Create a special `interaction_event` aggregate rather than forcing it into timed-event fields.

- Every user owns exactly one interaction event.
- It has `active` or `disabled` status.
- Users can disable and re-enable it.
- Users cannot delete it.
- It has no start, end, notification window, recurrence, or materialized occurrence.
- Expose its status and lifecycle through the event-management experience without allowing ordinary schedule updates or deletion.
- Persist at least:
  - its identifier and owner;
  - status;
  - latest actual user-message time;
  - latest successfully delivered assistant-message time;
  - creation and update timestamps.
- Keep ownership checks and account-deletion behavior consistent with other user-owned data.

Update `last_user_message_at` from actual accepted inbound user activity. Update `last_agent_message_at` only after a successful assistant delivery, including:

- a normal conversation response;
- a `user_event` notification;
- a `system_event` notification;
- an `interaction_event` message.

Use monotonic timestamp updates so delayed work cannot move either value backward.

## Scheduler Ordering

Keep the five-minute scheduler interval.

For each scheduler pass:

1. Select and process ordinary due `user_event` and `system_event` occurrences first.
2. Track every user who had an ordinary due occurrence in that pass.
3. Do not evaluate that same user's interaction event, even if ordinary generation or delivery fails.
4. Evaluate other users independently; one user's due event must not suppress another user's interaction event.
5. Continue only for an active subscription and active interaction event.
6. Stop when the latest actual user message is more than seven days old.
7. Apply the probability calculation.
8. If selected, invoke the scheduled agent, deliver the message, persist it, and advance assistant contact time.

An interaction message does not create a pending-response state. If the user does not answer, probability starts growing again from the delivered assistant message. An active event that crossed the seven-day cutoff remains active and becomes eligible automatically when the user returns.

## Probability Policy

Use a shape-2 Weibull policy with a 96-hour scale.

For elapsed time `t` since latest contact and scheduler interval `Δ`:

`p = 1 - exp(-(((t + Δ) / 96 hours)^2 - (t / 96 hours)^2))`

Latest contact is:

`max(last_user_message_at, last_agent_message_at)`

This gives cumulative trigger probabilities of approximately:

- 6% after one day;
- 22% after two days;
- 43% after three days;
- 63% after four days.

The formula must use the real scheduler interval so behavior remains stable if that interval changes. Inject the clock and random-number source for deterministic tests.

## Scheduled Agent Capabilities

All scheduled runs should receive:

- user and assistant profiles;
- conversation history;
- current time;
- current weather;
- Google Search grounding;
- every authorized application tool declared with `ToolEffect.READ`.

Modifying tools must be absent from the runtime tool store. Do not rely only on prompt instructions to prevent writes.

Use a scheduler-specific prompt that clearly states there is no new user message. Interaction events should ask the agent to choose a natural, useful conversational action based on available context.

## Quota and Timing Policy

- Ordinary `user_event` and `system_event` deliveries continue to consume event-notification allowance.
- Interaction-event messages consume neither conversation nor event-notification allowance.
- Interaction events have no separate quota.
- Interaction events have no quiet period.
- Scheduled messages never consume conversation quota.
- Failed generation, delivery, or persistence must not consume event-notification allowance or advance interaction contact state.

## Suggested Implementation Order

1. Add idempotent SQL for subscription boundaries, standalone scheduled messages, and interaction events.
2. Update schema validation and account/domain models.
3. Replace UTC-calendar quota periods with synchronized subscription periods.
4. Add standalone assistant-message persistence and context formatting.
5. Add runtime filtering for authorized read-only tools.
6. Add interaction-event repository, service, and lifecycle operations.
7. Record inbound and successful outbound contact activity.
8. Extend `AgentsScheduler` with per-user ordinary-event suppression and probabilistic interaction evaluation.
9. Persist ordinary and interaction scheduled messages.
10. Add focused unit and PostgreSQL integration tests.

## Essential Tests

- Different users use their own exact subscription boundaries.
- Invalid or missing current-period boundaries fail before quota admission.
- Conversation and event-notification counts use inclusive start and exclusive end.
- Scheduled messages appear in later context without a user prompt and do not consume conversation quota.
- Scheduled runs receive read-only tools and cannot resolve modifying tools.
- An ordinary due event suppresses only the same user's interaction event.
- Suppression still applies when ordinary delivery fails.
- Disabled interaction events never trigger and can be re-enabled.
- Interaction-event deletion is rejected.
- Probability tests use injected deterministic randomness and the configured scheduler interval.
- Successful assistant delivery resets probability; failed delivery does not.
- No interaction message is sent after seven days without an actual user message.
- A new user message restores eligibility without re-enabling the event.
- Interaction messages consume no quota.
- PostgreSQL ownership and two-user isolation remain intact.

Keep tests focused on essential behavior and no more than three tests per function or method. Run the repository's pre-commit checks and relevant unit and PostgreSQL integration tests before handoff.
