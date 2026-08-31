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
    status TEXT NOT NULL DEFAULT 'scheduled',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
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
        status IN ('scheduled', 'cancelled', 'deleted')
    ),
    CONSTRAINT internal_events_status_timestamps_valid CHECK (
        (
            status = 'scheduled'
            AND cancelled_at IS NULL
            AND deleted_at IS NULL
        )
        OR (
            status = 'cancelled'
            AND cancelled_at IS NOT NULL
            AND deleted_at IS NULL
        )
        OR (
            status = 'deleted'
            AND deleted_at IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_internal_events_user_starts_at
ON public.internal_events (user_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_internal_events_user_status_starts_at
ON public.internal_events (user_id, status, starts_at);

COMMIT;
