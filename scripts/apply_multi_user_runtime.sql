BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    telegram_id BIGINT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.plans (
    code TEXT PRIMARY KEY,
    monthly_request_limit INTEGER NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT plans_code_valid CHECK (
        code = LOWER(BTRIM(code))
        AND code ~ '^[a-z][a-z0-9_]*$'
    ),
    CONSTRAINT plans_monthly_request_limit_positive CHECK (
        monthly_request_limit > 0
    )
);

INSERT INTO public.plans (code, monthly_request_limit, active)
VALUES
    ('free', 60, TRUE),
    ('basic', 480, TRUE),
    ('max', 1920, TRUE)
ON CONFLICT (code) DO NOTHING;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS display_name TEXT,
    ADD COLUMN IF NOT EXISTS plan_code TEXT,
    ADD COLUMN IF NOT EXISTS subscription_status TEXT,
    ADD COLUMN IF NOT EXISTS subscription_valid_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS subscription_synced_at TIMESTAMPTZ;

UPDATE public.users
SET display_name = COALESCE(
    NULLIF(BTRIM(display_name), ''),
    NULLIF(BTRIM(name), ''),
    'User ' || id::TEXT
)
WHERE display_name IS NULL OR BTRIM(display_name) = '';

UPDATE public.users
SET name = display_name
WHERE name IS NULL OR BTRIM(name) = '';

UPDATE public.users
SET plan_code = 'free'
WHERE plan_code IS NULL OR BTRIM(plan_code) = '';

UPDATE public.users
SET subscription_status = 'inactive'
WHERE subscription_status IS NULL OR BTRIM(subscription_status) = '';

ALTER TABLE public.users
    ALTER COLUMN display_name SET NOT NULL,
    ALTER COLUMN display_name SET DEFAULT 'Pending provisioning',
    ALTER COLUMN plan_code SET NOT NULL,
    ALTER COLUMN plan_code SET DEFAULT 'free',
    ALTER COLUMN subscription_status SET NOT NULL,
    ALTER COLUMN subscription_status SET DEFAULT 'inactive';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.users'::regclass
            AND conname = 'users_display_name_not_blank'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_display_name_not_blank
            CHECK (BTRIM(display_name) <> '');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.users'::regclass
            AND conname = 'users_name_not_blank'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_name_not_blank
            CHECK (BTRIM(name) <> '');
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.users'::regclass
            AND conname = 'users_plan_code_fkey'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_plan_code_fkey
            FOREIGN KEY (plan_code)
            REFERENCES public.plans(code);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.users'::regclass
            AND conname = 'users_subscription_status_valid'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT users_subscription_status_valid
            CHECK (
                subscription_status IN (
                    'active',
                    'inactive',
                    'past_due',
                    'cancelled',
                    'revoked'
                )
            );
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_users_subscription_access
ON public.users (
    subscription_status,
    plan_code,
    subscription_valid_until
);

CREATE TABLE IF NOT EXISTS public.external_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    provider TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT external_identities_provider_valid CHECK (
        provider = LOWER(BTRIM(provider))
        AND provider ~ '^[a-z][a-z0-9_]*$'
    ),
    CONSTRAINT external_identities_external_user_id_not_blank CHECK (
        BTRIM(external_user_id) <> ''
    ),
    CONSTRAINT external_identities_display_name_not_blank CHECK (
        BTRIM(display_name) <> ''
    ),
    CONSTRAINT external_identities_provider_external_user_id_key
        UNIQUE (provider, external_user_id)
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.users AS users
        JOIN public.external_identities AS identities
            ON identities.provider = 'telegram'
            AND identities.external_user_id = users.telegram_id::TEXT
        WHERE users.telegram_id IS NOT NULL
            AND identities.user_id <> users.id
    ) THEN
        RAISE EXCEPTION 'A Telegram identity conflicts with a legacy users.telegram_id row';
    END IF;
END
$$;

INSERT INTO public.external_identities (
    user_id,
    provider,
    external_user_id,
    display_name
)
SELECT
    id,
    'telegram',
    telegram_id::TEXT,
    display_name
FROM public.users
WHERE telegram_id IS NOT NULL
ON CONFLICT (provider, external_user_id) DO UPDATE
SET user_id = EXCLUDED.user_id,
    display_name = EXCLUDED.display_name,
    updated_at = NOW()
WHERE external_identities.user_id IS DISTINCT FROM EXCLUDED.user_id
    OR external_identities.display_name IS DISTINCT FROM EXCLUDED.display_name;

CREATE INDEX IF NOT EXISTS idx_external_identities_user_id
ON public.external_identities (user_id);

CREATE TABLE IF NOT EXISTS public.user_profiles (
    user_id UUID PRIMARY KEY
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    preferred_name TEXT NOT NULL,
    locale TEXT NOT NULL,
    timezone TEXT NOT NULL,
    latitude NUMERIC(9, 6),
    longitude NUMERIC(9, 6),
    personal_history TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_profiles_preferred_name_not_blank CHECK (
        BTRIM(preferred_name) <> ''
    ),
    CONSTRAINT user_profiles_locale_not_blank CHECK (
        BTRIM(locale) <> ''
    ),
    CONSTRAINT user_profiles_timezone_not_blank CHECK (
        BTRIM(timezone) <> ''
    ),
    CONSTRAINT user_profiles_location_complete CHECK (
        (latitude IS NULL AND longitude IS NULL)
        OR (latitude IS NOT NULL AND longitude IS NOT NULL)
    ),
    CONSTRAINT user_profiles_latitude_valid CHECK (
        latitude IS NULL OR latitude BETWEEN -90 AND 90
    ),
    CONSTRAINT user_profiles_longitude_valid CHECK (
        longitude IS NULL OR longitude BETWEEN -180 AND 180
    )
);

CREATE TABLE IF NOT EXISTS public.assistant_profiles (
    user_id UUID PRIMARY KEY
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    profile_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT assistant_profiles_display_name_not_blank CHECK (
        BTRIM(display_name) <> ''
    ),
    CONSTRAINT assistant_profiles_profile_text_not_blank CHECK (
        BTRIM(profile_text) <> ''
    )
);

CREATE TABLE IF NOT EXISTS public.conversations (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    telegram_chat_id BIGINT,
    prompt TEXT NOT NULL,
    response TEXT NOT NULL,
    model TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'conversation',
    tool_call_response JSONB,
    tool_result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.conversations
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'conversation',
    ADD COLUMN IF NOT EXISTS tool_call_response JSONB,
    ADD COLUMN IF NOT EXISTS tool_result JSONB;

CREATE INDEX IF NOT EXISTS idx_conversations_chat_user_created_at
ON public.conversations (
    user_id,
    telegram_chat_id,
    created_at DESC,
    id DESC
);

COMMIT;
