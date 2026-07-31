# Workload 4: Internal Expenses

## Goal

Provide commercial users with user-owned PostgreSQL expense tracking while keeping Juan on Google Sheets.

## Scope

- Model amounts with `Decimal`, dates with `date`, and explicit expense/refund semantics.
- Persist ownership, currency, category, transaction date, description, status, installments, and timestamps.
- Support one-time expenses, refunds, 2–12 installments, daily reads, monthly summaries, corrections, and cancellation.
- Preserve the existing 00:00–04:00 previous-day rule.
- Split installment amounts deterministically without losing currency fractions.
- Use transaction UUIDs for updates and cancellations.
- Expose this tool family only to commercial users.
- Execute writes only when explicitly requested in the current message.

## Decisions required before affected code

- Supported and default currencies
- Whether categories are fixed
- Installment correction behavior
- Cancellation versus deletion behavior

Do not add a migration framework. Propose the expense schema and deployment approach before changing an existing database.

## Done when

- Commercial users can manage only their own expenses.
- Installments sum exactly to the requested total.
- Refunds subtract correctly from summaries.
- Juan receives Sheets expenses instead of internal expenses.

Depends on workloads 2 and 3.
