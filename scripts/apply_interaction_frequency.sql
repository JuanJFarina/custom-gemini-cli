BEGIN;

SET LOCAL search_path = public, pg_temp;

ALTER TABLE public.assistant_profiles
    ADD COLUMN IF NOT EXISTS interaction_frequency TEXT NOT NULL DEFAULT 'high';

ALTER TABLE public.assistant_profiles
    DROP CONSTRAINT IF EXISTS assistant_profiles_interaction_frequency_valid,
    ADD CONSTRAINT assistant_profiles_interaction_frequency_valid CHECK (
        interaction_frequency IN ('high', 'medium', 'low')
    );

COMMIT;
