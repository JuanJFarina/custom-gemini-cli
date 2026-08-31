BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE TABLE IF NOT EXISTS public.telegram_update_claims (
    update_id BIGINT PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT telegram_update_claims_update_id_valid CHECK (
        update_id >= 0
    ),
    CONSTRAINT telegram_update_claims_user_id_valid CHECK (
        telegram_user_id > 0
    ),
    CONSTRAINT telegram_update_claims_chat_id_valid CHECK (
        telegram_chat_id <> 0
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

COMMIT;
