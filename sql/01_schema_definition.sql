-- =============================================================================
-- FinTech Growth & Revenue Funnel — Schema Definition
-- Database: fintech_growth
-- Purpose: Model the user onboarding journey and monetization events
-- =============================================================================

-- Enable UUID generation (pgcrypto ships with PostgreSQL 15)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- -----------------------------------------------------------------------------
-- users: acquisition and segmentation attributes for each signed-up customer
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id             UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    signup_timestamp    TIMESTAMPTZ     NOT NULL,
    acquisition_channel VARCHAR(50)     NOT NULL,
    user_segment        VARCHAR(50)     NOT NULL
);

COMMENT ON TABLE users IS 'Core user registry with acquisition channel and segment.';
COMMENT ON COLUMN users.acquisition_channel IS 'e.g. organic_search, paid_social, referral, affiliate, app_store';
COMMENT ON COLUMN users.user_segment IS 'e.g. retail, mass_affluent, student, freelancer';

-- -----------------------------------------------------------------------------
-- user_events: onboarding funnel steps (account → docs → KYC → first deposit)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_events (
    event_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_name      VARCHAR(50)     NOT NULL,
    event_timestamp TIMESTAMPTZ     NOT NULL,
    device_type     VARCHAR(30)     NOT NULL,
    CONSTRAINT chk_event_name CHECK (
        event_name IN (
            'account_created',
            'document_uploaded',
            'kyc_approved',
            'first_deposit_initiated'
        )
    )
);

COMMENT ON TABLE user_events IS 'Funnel events along the FinTech onboarding journey.';
COMMENT ON COLUMN user_events.event_name IS 'Ordered funnel stages: account_created → document_uploaded → kyc_approved → first_deposit_initiated';

CREATE INDEX IF NOT EXISTS idx_user_events_user_id ON user_events (user_id);
CREATE INDEX IF NOT EXISTS idx_user_events_event_name ON user_events (event_name);
CREATE INDEX IF NOT EXISTS idx_user_events_timestamp ON user_events (event_timestamp);

-- -----------------------------------------------------------------------------
-- financial_transactions: monetization / deposit activity after KYC
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_transactions (
    transaction_id   UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID            NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    transaction_type VARCHAR(50)     NOT NULL,
    amount           DECIMAL(12, 2)  NOT NULL CHECK (amount > 0),
    status           VARCHAR(20)     NOT NULL,
    created_at       TIMESTAMPTZ     NOT NULL,
    CONSTRAINT chk_transaction_status CHECK (
        status IN ('completed', 'failed')
    )
);

COMMENT ON TABLE financial_transactions IS 'Deposit and related financial activity tied to monetized users.';
COMMENT ON COLUMN financial_transactions.transaction_type IS 'e.g. deposit, withdrawal, fee, transfer';
COMMENT ON COLUMN financial_transactions.status IS 'completed | failed';

CREATE INDEX IF NOT EXISTS idx_financial_tx_user_id ON financial_transactions (user_id);
CREATE INDEX IF NOT EXISTS idx_financial_tx_status ON financial_transactions (status);
CREATE INDEX IF NOT EXISTS idx_financial_tx_created_at ON financial_transactions (created_at);
