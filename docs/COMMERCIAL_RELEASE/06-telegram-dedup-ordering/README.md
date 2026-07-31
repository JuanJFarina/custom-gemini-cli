# Workload 6: Telegram Deduplication and Ordering

## Goal

Prevent Telegram retries and concurrent requests from causing duplicate or conflicting work.

## Scope

- Parse and validate Telegram `update_id`.
- Claim each update before Gemini, quota checks, or tool execution.
- Persist enough deduplication state to reject the same update after a process restart.
- Serialize one user's conflicting work with a process-local coordinator.
- Keep different users independent.
- Use stable update-derived identifiers for conversation and tool writes where needed.

## Not included

- Durable inbox or outbox workers
- Background task leasing
- Guaranteed retry of accepted work after restart
- Telegram send-message exactly-once guarantees

Propose the minimal deduplication schema before changing an existing database. Do not introduce a general migration framework in this workload.

## Done when

- A duplicate update causes no second Gemini call, conversation, or tool change.
- Conflicting work for one user is serialized.
- One user's work does not block another user's work.

Depends on workload 2.
