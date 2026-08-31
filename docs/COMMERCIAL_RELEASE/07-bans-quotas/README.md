# Workload 7: Bans and Quotas

## Goal

Reject abusive or over-quota requests before they invoke Gemini or tools.

## Scope

- Keep a process-local rolling timestamp window per Telegram identity.
- Trigger a temporary ban on the tenth valid message within two seconds.
- Escalate cooldowns from at least 60 seconds to 5 minutes and 1 hour.
- Decay strikes after normal use and send at most one notice per cooldown.
- Count only successfully completed current-month conversations.
- Use explicit UTC month boundaries.
- Include process-local in-flight reservations so concurrent requests cannot exceed the limit.
- Return remaining usage and the reset boundary without calling Gemini.
- Inject a clock for deterministic tests.

Plan limits must come from account or plan configuration. Treat the documented `60`, `480`, and `1,920` limits as provisional rather than policy constants.

## Not included

- Distributed rate limiting
- Multiple application processes
- Cost-based or token-based quotas

## Done when

- Banned and over-quota requests invoke neither Gemini nor tools.
- Tool calls, failed conversations, malformed updates, and duplicates consume no quota.
- A ban affects only the triggering Telegram identity.
- In-flight reservations are released on every outcome.

Depends on workloads 2 and 6.
