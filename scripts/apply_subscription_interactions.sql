BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS subscription_period_starts_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS subscription_period_ends_at TIMESTAMPTZ;

ALTER TABLE public.users
    DROP CONSTRAINT IF EXISTS users_subscription_period_complete,
    ADD CONSTRAINT users_subscription_period_complete CHECK (
        (
            subscription_period_starts_at IS NULL
            AND subscription_period_ends_at IS NULL
        )
        OR (
            subscription_period_starts_at IS NOT NULL
            AND subscription_period_ends_at IS NOT NULL
            AND subscription_period_starts_at < subscription_period_ends_at
        )
    );

ALTER TABLE public.conversations
    ALTER COLUMN prompt DROP NOT NULL;

ALTER TABLE public.conversations
    DROP CONSTRAINT IF EXISTS conversations_kind_valid,
    ADD CONSTRAINT conversations_kind_valid CHECK (
        kind IN ('conversation', 'tool_call', 'scheduled_message')
    ),
    DROP CONSTRAINT IF EXISTS conversations_prompt_valid,
    ADD CONSTRAINT conversations_prompt_valid CHECK (
        (kind = 'scheduled_message' AND prompt IS NULL)
        OR (kind <> 'scheduled_message' AND prompt IS NOT NULL)
    );

CREATE TABLE IF NOT EXISTS public.interaction_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',
    last_user_message_at TIMESTAMPTZ,
    last_agent_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT interaction_events_status_valid CHECK (
        status IN ('active', 'disabled')
    )
);

INSERT INTO public.interaction_events (user_id)
SELECT id
FROM public.users
ON CONFLICT (user_id) DO NOTHING;

CREATE OR REPLACE FUNCTION public.create_user_interaction_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.interaction_events (user_id)
    VALUES (NEW.id)
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS users_create_interaction_event ON public.users;

CREATE TRIGGER users_create_interaction_event
AFTER INSERT ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.create_user_interaction_event();

CREATE INDEX IF NOT EXISTS idx_interaction_events_scheduler
ON public.interaction_events (
    status,
    last_user_message_at,
    last_agent_message_at
);

COMMIT;
