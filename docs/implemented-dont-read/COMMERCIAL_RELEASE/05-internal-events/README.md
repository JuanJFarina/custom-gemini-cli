# Workload 5: Internal Events

## Goal

Provide every entitled user with private, passive, one-time events stored in PostgreSQL.

## Scope

- Persist owner, title, description, start, end, IANA timezone, status, and timestamps.
- List events within a bounded date range.
- Create, update, cancel, and delete only events owned by the requesting user.
- Convert user-local input to UTC while preserving the originating timezone.
- Require the end time to be after the start time.
- Exclude cancelled or deleted events from normal reads.
- Execute writes only when explicitly requested in the current message.

## Decisions

- Version 1 supports timed and all-day events.
- Cancellation retains the event and hides it from normal reads.
- Deletion permanently removes a scheduled or cancelled event.
- Cancelled events have no automatic retention deadline or purge in version 1.

## Not included

- Google Calendar
- Recurrence, attendees, reminders, notifications, or background scheduling

Do not add a migration framework. Propose the event schema and deployment approach before changing an existing database.

## Done when

- Users can access and modify only their own events.
- Juan and commercial users receive the same event family.
- Event operations create no external or background work.

Depends on workloads 2 and 3.
