BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE public.plans
    ADD COLUMN IF NOT EXISTS monthly_notification_limit INTEGER;

UPDATE public.plans
SET monthly_notification_limit = CASE code
    WHEN 'free' THEN 15
    WHEN 'basic' THEN 60
    WHEN 'max' THEN 240
    ELSE GREATEST(1, (monthly_request_limit + 3) / 4)
END
WHERE monthly_notification_limit IS NULL;

ALTER TABLE public.plans
    ALTER COLUMN monthly_notification_limit SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.plans'::regclass
            AND conname = 'plans_monthly_notification_limit_positive'
    ) THEN
        ALTER TABLE public.plans
            ADD CONSTRAINT plans_monthly_notification_limit_positive
            CHECK (monthly_notification_limit > 0);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS public.event_notification_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    event_id UUID
        REFERENCES public.internal_events(id)
        ON DELETE SET NULL,
    occurrence_starts_at TIMESTAMPTZ NOT NULL,
    notification_window_start TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT event_notification_delivery_window_valid CHECK (
        notification_window_start < occurrence_starts_at
    ),
    CONSTRAINT event_notification_delivery_occurrence_key UNIQUE (
        event_id,
        occurrence_starts_at,
        notification_window_start
    )
);

CREATE INDEX IF NOT EXISTS idx_event_notification_deliveries_monthly_usage
ON public.event_notification_deliveries (user_id, delivered_at);

CREATE TABLE IF NOT EXISTS public.event_notification_quota_notices (
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    period_starts_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'attempted',
    attempted_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, period_starts_at),
    CONSTRAINT event_notification_quota_notice_status_valid CHECK (
        status IN ('attempted', 'delivered')
    ),
    CONSTRAINT event_notification_quota_notice_delivery_valid CHECK (
        (status = 'attempted' AND delivered_at IS NULL)
        OR (status = 'delivered' AND delivered_at IS NOT NULL)
    )
);

COMMIT;
