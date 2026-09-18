BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.internal_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    timezone TEXT NOT NULL,
    all_day BOOLEAN NOT NULL DEFAULT FALSE,
    event_type TEXT NOT NULL DEFAULT 'user_event',
    status TEXT NOT NULL DEFAULT 'active',
    notification_window_start TIMESTAMPTZ NOT NULL,
    last_notified_at TIMESTAMPTZ,
    recurrence_rule JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT internal_events_title_not_blank CHECK (
        BTRIM(title) <> ''
    ),
    CONSTRAINT internal_events_timezone_not_blank CHECK (
        BTRIM(timezone) <> ''
    ),
    CONSTRAINT internal_events_interval_valid CHECK (
        ends_at > starts_at
    ),
    CONSTRAINT internal_events_status_valid CHECK (
        status IN ('active', 'disabled')
    ),
    CONSTRAINT internal_events_event_type_valid CHECK (
        event_type IN ('user_event', 'system_event')
    ),
    CONSTRAINT internal_events_notification_window_valid CHECK (
        notification_window_start <= starts_at
    ),
    CONSTRAINT internal_events_recurrence_rule_valid CHECK (
        recurrence_rule IS NULL
        OR (
            JSONB_TYPEOF(recurrence_rule) = 'object'
            AND (
                (
                    recurrence_rule ? 'week_days'
                    AND NOT (recurrence_rule ? 'month_days')
                    AND JSONB_TYPEOF(recurrence_rule -> 'week_days') = 'array'
                    AND JSONB_ARRAY_LENGTH(recurrence_rule -> 'week_days') > 0
                )
                OR (
                    recurrence_rule ? 'month_days'
                    AND NOT (recurrence_rule ? 'week_days')
                    AND JSONB_TYPEOF(recurrence_rule -> 'month_days') = 'array'
                    AND JSONB_ARRAY_LENGTH(recurrence_rule -> 'month_days') > 0
                )
            )
        )
    )
);

DELETE FROM public.internal_events
WHERE status = 'deleted';

ALTER TABLE public.internal_events
    ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'user_event',
    ADD COLUMN IF NOT EXISTS notification_window_start TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_notified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS recurrence_rule JSONB,
    DROP CONSTRAINT IF EXISTS internal_events_status_valid,
    DROP CONSTRAINT IF EXISTS internal_events_event_type_valid,
    DROP CONSTRAINT IF EXISTS internal_events_notification_window_valid,
    DROP CONSTRAINT IF EXISTS internal_events_notification_status_valid,
    DROP CONSTRAINT IF EXISTS internal_events_status_timestamps_valid,
    DROP CONSTRAINT IF EXISTS internal_events_recurrence_rule_valid,
    DROP COLUMN IF EXISTS deleted_at;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
            AND table_name = 'internal_events'
            AND column_name = 'notification_status'
    ) THEN
        EXECUTE '
            UPDATE public.internal_events
            SET last_notified_at = updated_at
            WHERE notification_status = ''delivered''
                AND last_notified_at IS NULL
        ';
    END IF;
END
$$;

UPDATE public.internal_events
SET status = CASE status
    WHEN 'scheduled' THEN 'active'
    WHEN 'cancelled' THEN 'disabled'
    ELSE status
END
WHERE status IN ('scheduled', 'cancelled');

UPDATE public.internal_events
SET notification_window_start = starts_at
WHERE notification_window_start IS NULL
    OR notification_window_start > starts_at;

DROP INDEX IF EXISTS public.idx_internal_events_due_notifications;
DROP INDEX IF EXISTS public.idx_internal_events_active_recurrence;

ALTER TABLE public.internal_events
    DROP COLUMN IF EXISTS notified,
    DROP COLUMN IF EXISTS notification_status,
    DROP COLUMN IF EXISTS cancelled_at,
    ALTER COLUMN notification_window_start SET NOT NULL,
    ALTER COLUMN status SET DEFAULT 'active',
    ADD CONSTRAINT internal_events_status_valid CHECK (
        status IN ('active', 'disabled')
    ),
    ADD CONSTRAINT internal_events_event_type_valid CHECK (
        event_type IN ('user_event', 'system_event')
    ),
    ADD CONSTRAINT internal_events_notification_window_valid CHECK (
        notification_window_start <= starts_at
    ),
    ADD CONSTRAINT internal_events_recurrence_rule_valid CHECK (
        recurrence_rule IS NULL
        OR (
            JSONB_TYPEOF(recurrence_rule) = 'object'
            AND (
                (
                    recurrence_rule ? 'week_days'
                    AND NOT (recurrence_rule ? 'month_days')
                    AND JSONB_TYPEOF(recurrence_rule -> 'week_days') = 'array'
                    AND JSONB_ARRAY_LENGTH(recurrence_rule -> 'week_days') > 0
                )
                OR (
                    recurrence_rule ? 'month_days'
                    AND NOT (recurrence_rule ? 'week_days')
                    AND JSONB_TYPEOF(recurrence_rule -> 'month_days') = 'array'
                    AND JSONB_ARRAY_LENGTH(recurrence_rule -> 'month_days') > 0
                )
            )
        )
    );

CREATE INDEX IF NOT EXISTS idx_internal_events_user_starts_at
ON public.internal_events (user_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_internal_events_user_status_starts_at
ON public.internal_events (user_id, status, starts_at);

CREATE INDEX idx_internal_events_due_notifications
ON public.internal_events (notification_window_start, starts_at, id)
WHERE status = 'active'
    AND recurrence_rule IS NULL
    AND last_notified_at IS NULL;

CREATE INDEX idx_internal_events_active_recurrence
ON public.internal_events (user_id, id)
WHERE status = 'active'
    AND recurrence_rule IS NOT NULL;

COMMIT;
