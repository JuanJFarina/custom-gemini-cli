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
    status TEXT NOT NULL DEFAULT 'scheduled',
    notification_window_start TIMESTAMPTZ,
    notification_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ,
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
        status IN ('scheduled', 'cancelled')
    ),
    CONSTRAINT internal_events_event_type_valid CHECK (
        event_type IN ('user_event', 'system_event')
    ),
    CONSTRAINT internal_events_notification_window_valid CHECK (
        notification_window_start < starts_at
    ),
    CONSTRAINT internal_events_notification_status_valid CHECK (
        notification_status IN ('disabled', 'pending', 'delivered')
    ),
    CONSTRAINT internal_events_status_timestamps_valid CHECK (
        (
            status = 'scheduled'
            AND cancelled_at IS NULL
        )
        OR (
            status = 'cancelled'
            AND cancelled_at IS NOT NULL
        )
    )
);

DELETE FROM public.internal_events
WHERE status = 'deleted';

ALTER TABLE public.internal_events
    ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'user_event',
    ADD COLUMN IF NOT EXISTS notification_window_start TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS notification_status TEXT,
    DROP CONSTRAINT IF EXISTS internal_events_status_timestamps_valid,
    DROP CONSTRAINT IF EXISTS internal_events_status_valid,
    DROP CONSTRAINT IF EXISTS internal_events_event_type_valid,
    DROP CONSTRAINT IF EXISTS internal_events_notification_window_valid,
    DROP CONSTRAINT IF EXISTS internal_events_notification_status_valid,
    DROP COLUMN IF EXISTS deleted_at;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
            AND table_name = 'internal_events'
            AND column_name = 'notified'
    ) THEN
        EXECUTE '
            UPDATE public.internal_events
            SET notification_status = CASE
                WHEN notified THEN ''delivered''
                ELSE ''pending''
            END
            WHERE notification_status IS NULL
        ';
    ELSE
        UPDATE public.internal_events
        SET notification_status = 'pending'
        WHERE notification_status IS NULL;
    END IF;
END
$$;

UPDATE public.internal_events
SET notification_window_start = starts_at - INTERVAL '15 minutes'
WHERE notification_window_start IS NULL
    OR notification_window_start >= starts_at;

DROP INDEX IF EXISTS public.idx_internal_events_due_notifications;

ALTER TABLE public.internal_events
    DROP COLUMN IF EXISTS notified,
    ALTER COLUMN notification_window_start SET NOT NULL,
    ALTER COLUMN notification_status SET DEFAULT 'pending',
    ALTER COLUMN notification_status SET NOT NULL,
    ADD CONSTRAINT internal_events_status_valid CHECK (
        status IN ('scheduled', 'cancelled')
    ),
    ADD CONSTRAINT internal_events_event_type_valid CHECK (
        event_type IN ('user_event', 'system_event')
    ),
    ADD CONSTRAINT internal_events_notification_window_valid CHECK (
        notification_window_start < starts_at
    ),
    ADD CONSTRAINT internal_events_notification_status_valid CHECK (
        notification_status IN ('disabled', 'pending', 'delivered')
    ),
    ADD CONSTRAINT internal_events_status_timestamps_valid CHECK (
        (status = 'scheduled' AND cancelled_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS idx_internal_events_user_starts_at
ON public.internal_events (user_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_internal_events_user_status_starts_at
ON public.internal_events (user_id, status, starts_at);

CREATE INDEX idx_internal_events_due_notifications
ON public.internal_events (notification_window_start, starts_at, id)
WHERE status = 'scheduled'
    AND notification_status = 'pending';

COMMIT;
