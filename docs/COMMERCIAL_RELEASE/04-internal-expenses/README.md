# Workload 4: Internal Expenses

## Goal

Provide commercial users with user-owned PostgreSQL expense tracking while keeping Juan on Google Sheets.

## Scope

- Model amounts with `Decimal`, dates with `date`, and explicit expense/refund semantics.
- Persist ownership, currency, category, transaction date, description, installments, and timestamps.
- Support one-time expenses, refunds, 2–12 installments, daily reads, monthly summaries, corrections, and permanent deletion.
- Preserve the existing 00:00–04:00 previous-day rule.
- Split installment amounts deterministically without losing currency fractions.
- Use transaction UUIDs for updates and deletions.
- Expose this tool family only to commercial users.
- Execute writes only when explicitly requested in the current message.

## Decisions

- Version 1 stores Argentine pesos only.
- Categories are fixed for version 1.
- Updating an installment transaction updates its entire installment group while preserving the installment count.
- Deleting an expense permanently removes the transaction or its entire installment group.

Do not add a migration framework. Propose the expense schema and deployment approach before changing an existing database.

## Done when

- Commercial users can manage only their own expenses.
- Installments sum exactly to the requested total.
- Refunds subtract correctly from summaries.
- Juan receives Sheets expenses instead of internal expenses.

Depends on workloads 2 and 3.
