BEGIN;

SET LOCAL search_path = public, pg_temp;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.expense_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL
        REFERENCES public.users(id)
        ON DELETE CASCADE,
    entry_type TEXT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'ARS',
    category TEXT NOT NULL,
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    installment_group_id UUID,
    installment_number SMALLINT,
    installment_count SMALLINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMPTZ,
    CONSTRAINT expense_transactions_entry_type_valid CHECK (
        entry_type IN ('expense', 'refund')
    ),
    CONSTRAINT expense_transactions_amount_positive CHECK (
        amount > 0
    ),
    CONSTRAINT expense_transactions_currency_valid CHECK (
        currency = 'ARS'
    ),
    CONSTRAINT expense_transactions_category_valid CHECK (
        category IN (
            'rent',
            'essential_services',
            'non_essential_services',
            'home',
            'transport',
            'outings',
            'shopping',
            'other'
        )
    ),
    CONSTRAINT expense_transactions_description_not_blank CHECK (
        BTRIM(description) <> ''
    ),
    CONSTRAINT expense_transactions_status_valid CHECK (
        status IN ('active', 'cancelled')
    ),
    CONSTRAINT expense_transactions_status_timestamp_valid CHECK (
        (status = 'active' AND cancelled_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL)
    ),
    CONSTRAINT expense_transactions_installments_complete CHECK (
        (
            installment_group_id IS NULL
            AND installment_number IS NULL
            AND installment_count IS NULL
        )
        OR (
            installment_group_id IS NOT NULL
            AND installment_number IS NOT NULL
            AND installment_count BETWEEN 2 AND 12
            AND installment_number BETWEEN 1 AND installment_count
            AND entry_type = 'expense'
        )
    ),
    CONSTRAINT expense_transactions_installment_number_unique
        UNIQUE (user_id, installment_group_id, installment_number)
);

CREATE INDEX IF NOT EXISTS idx_expense_transactions_user_date
ON public.expense_transactions (user_id, transaction_date DESC);

CREATE INDEX IF NOT EXISTS idx_expense_transactions_user_status_date
ON public.expense_transactions (user_id, status, transaction_date DESC);

CREATE INDEX IF NOT EXISTS idx_expense_transactions_user_category_date
ON public.expense_transactions (user_id, category, transaction_date DESC);

CREATE INDEX IF NOT EXISTS idx_expense_transactions_user_installment_group
ON public.expense_transactions (user_id, installment_group_id)
WHERE installment_group_id IS NOT NULL;

COMMIT;
