BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE TABLE IF NOT EXISTS public.telegram_update_claims (
    update_id BIGINT PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    message_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tool_started_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    conversation_id BIGINT
        REFERENCES public.conversations(id)
        ON DELETE SET NULL,
    CONSTRAINT telegram_update_claims_update_id_valid CHECK (
        update_id >= 0
    ),
    CONSTRAINT telegram_update_claims_user_id_valid CHECK (
        telegram_user_id > 0
    ),
    CONSTRAINT telegram_update_claims_chat_id_valid CHECK (
        telegram_chat_id <> 0
    ),
    CONSTRAINT telegram_update_claims_message_text_not_blank CHECK (
        BTRIM(message_text) <> ''
    ),
    CONSTRAINT telegram_update_claims_status_valid CHECK (
        status IN (
            'received',
            'processing',
            'tool_started',
            'delivering',
            'delivered',
            'failed',
            'rate_limited',
            'interrupted',
            'rejected'
        )
    )
);

ALTER TABLE public.telegram_update_claims
    ADD COLUMN IF NOT EXISTS message_text TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'received',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS tool_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS conversation_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.telegram_update_claims'::regclass
            AND conname = 'telegram_update_claims_conversation_id_fkey'
    ) THEN
        ALTER TABLE public.telegram_update_claims
            ADD CONSTRAINT telegram_update_claims_conversation_id_fkey
            FOREIGN KEY (conversation_id)
            REFERENCES public.conversations(id)
            ON DELETE SET NULL;
    END IF;

END
$$;

ALTER TABLE public.telegram_update_claims
    DROP CONSTRAINT IF EXISTS telegram_update_claims_status_valid,
    ADD CONSTRAINT telegram_update_claims_status_valid CHECK (
        status IN (
            'received',
            'processing',
            'tool_started',
            'delivering',
            'delivered',
            'failed',
            'rate_limited',
            'interrupted',
            'rejected'
        )
    );

ALTER TABLE public.conversations
    ADD COLUMN IF NOT EXISTS telegram_update_id BIGINT,
    ADD COLUMN IF NOT EXISTS tool_interaction_index SMALLINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.conversations'::regclass
            AND conname = 'conversations_telegram_update_id_valid'
    ) THEN
        ALTER TABLE public.conversations
            ADD CONSTRAINT conversations_telegram_update_id_valid
            CHECK (
                telegram_update_id IS NULL
                OR telegram_update_id >= 0
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.conversations'::regclass
            AND conname = 'conversations_tool_interaction_index_valid'
    ) THEN
        ALTER TABLE public.conversations
            ADD CONSTRAINT conversations_tool_interaction_index_valid
            CHECK (
                tool_interaction_index IS NULL
                OR (
                    kind = 'tool_call'
                    AND tool_interaction_index >= 0
                )
            );
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_telegram_update_conversation
ON public.conversations (telegram_update_id)
WHERE telegram_update_id IS NOT NULL
    AND kind = 'conversation';

CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_telegram_update_tool_call
ON public.conversations (telegram_update_id, tool_interaction_index)
WHERE telegram_update_id IS NOT NULL
    AND kind = 'tool_call'
    AND tool_interaction_index IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telegram_update_claims_status_updated_at
ON public.telegram_update_claims (status, updated_at);

COMMIT;
