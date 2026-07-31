# Workload 3: Tool Registry and Sheets Isolation

## Goal

Build tools per request and make Juan's existing Google Sheets expenses inaccessible to every other user.

## Scope

- Replace global `TOOLS` with a process-scoped metadata registry and request-scoped handlers.
- Describe each tool by name, family, typed arguments, and read or modify effect.
- Select authorized families from the resolved internal user UUID.
- Expose legacy Google Sheets expenses only when the UUID equals `LEGACY_GOOGLE_SHEETS_USER_ID`.
- Move Sheets client construction and settings into infrastructure with explicit injection.
- Add authorization guards before client construction and again before modifying Sheets.
- Preserve existing Google Sheets expense behavior.
- Permit modifying tools only when the current user message explicitly requests the change.

## Not included

- Model-based tool relevance ranking
- Multi-user Google OAuth or Sheets access
- Persisted proposed actions, audits, or confirmation buttons
- Internal PostgreSQL expense tools

## Done when

- Commercial users receive no Sheets tool names, descriptions, handlers, settings, or client.
- A forced non-Juan Sheets call fails before client construction.
- Juan's current expense operations still work.

Depends on workloads 1 and 2.
