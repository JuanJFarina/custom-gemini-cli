BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.external_identities
        GROUP BY user_id, provider
        HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'A user has more than one identity for the same provider';
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_external_identities_user_provider
ON public.external_identities (user_id, provider);

CREATE TABLE IF NOT EXISTS public.web_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    session_token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT web_sessions_token_hash_valid CHECK (
        session_token_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT web_sessions_expiry_valid CHECK (
        expires_at > created_at
    ),
    CONSTRAINT web_sessions_revocation_valid CHECK (
        revoked_at IS NULL OR revoked_at >= created_at
    )
);

CREATE INDEX IF NOT EXISTS idx_web_sessions_user_active
ON public.web_sessions (user_id, expires_at)
WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS public.telegram_link_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT telegram_link_tokens_hash_valid CHECK (
        token_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT telegram_link_tokens_expiry_valid CHECK (
        expires_at > created_at
    ),
    CONSTRAINT telegram_link_tokens_consumption_valid CHECK (
        consumed_at IS NULL OR consumed_at >= created_at
    )
);

WITH ranked_pending_tokens AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY created_at DESC, id DESC
        ) AS pending_rank
    FROM public.telegram_link_tokens
    WHERE consumed_at IS NULL
)
UPDATE public.telegram_link_tokens AS tokens
SET consumed_at = GREATEST(tokens.created_at, NOW())
FROM ranked_pending_tokens
WHERE tokens.id = ranked_pending_tokens.id
    AND ranked_pending_tokens.pending_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_link_tokens_user_pending
ON public.telegram_link_tokens (user_id)
WHERE consumed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_telegram_link_tokens_user_pending
ON public.telegram_link_tokens (user_id, expires_at DESC)
WHERE consumed_at IS NULL;

COMMIT;
