BEGIN;

SET LOCAL search_path = public, pg_temp;

ALTER TABLE public.conversations
    ADD COLUMN IF NOT EXISTS status TEXT,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS failure_code TEXT;

UPDATE public.conversations
SET status = 'completed'
WHERE status IS NULL;

UPDATE public.conversations
SET completed_at = created_at
WHERE status = 'completed'
    AND completed_at IS NULL;

ALTER TABLE public.conversations
    ALTER COLUMN status DROP DEFAULT,
    ALTER COLUMN status SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.conversations'::regclass
            AND conname = 'conversations_status_valid'
    ) THEN
        ALTER TABLE public.conversations
            ADD CONSTRAINT conversations_status_valid
            CHECK (status IN ('processing', 'completed', 'failed'));
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conrelid = 'public.conversations'::regclass
            AND conname = 'conversations_completion_timestamp_valid'
    ) THEN
        ALTER TABLE public.conversations
            ADD CONSTRAINT conversations_completion_timestamp_valid
            CHECK (status <> 'completed' OR completed_at IS NOT NULL);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_conversations_completed_monthly_usage
ON public.conversations (user_id, created_at)
WHERE kind = 'conversation'
    AND status = 'completed';

COMMIT;
