-- ============================================================================
-- MIGRATION: Add Google Play Billing Support
-- Version: 001
-- Date: 2024-01-XX
-- Description: Add columns to support Google Play and multi-platform payments
-- ============================================================================

-- ============================================================================
-- TRANSACTIONS TABLE - Add Google Play columns
-- ============================================================================

-- Add platform column (web, android, ios)
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS platform VARCHAR(20) DEFAULT 'web';

-- Add Google Play purchase token
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS purchase_token TEXT;

-- Add Google Play order ID
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS google_order_id VARCHAR(100);

-- Add acknowledgement state for Google Play
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS acknowledgement_state VARCHAR(20) DEFAULT 'pending';

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_transactions_platform 
ON transactions(platform);

CREATE INDEX IF NOT EXISTS idx_transactions_purchase_token 
ON transactions(purchase_token) 
WHERE purchase_token IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_google_order 
ON transactions(google_order_id) 
WHERE google_order_id IS NOT NULL;

-- ============================================================================
-- USERS TABLE - Add subscription platform tracking
-- ============================================================================

-- Add column to track where user subscribed from
ALTER TABLE users
ADD COLUMN IF NOT EXISTS subscription_platform VARCHAR(20);

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON COLUMN transactions.platform IS 
'Payment platform: web (Razorpay), android (Google Play), ios (Apple IAP)';

COMMENT ON COLUMN transactions.purchase_token IS 
'Google Play purchase token for verification (can be very long)';

COMMENT ON COLUMN transactions.google_order_id IS 
'Google Play order ID (format: GPA.xxxx-xxxx-xxxx-xxxxx)';

COMMENT ON COLUMN transactions.acknowledgement_state IS 
'Google Play acknowledgement: pending, acknowledged, consumed';

COMMENT ON COLUMN users.subscription_platform IS 
'Platform where user subscribed: web, android, ios';

-- ============================================================================
-- VERIFY MIGRATION
-- ============================================================================

-- Check that columns were added
DO $$
BEGIN
    -- Check transactions table
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'transactions' AND column_name = 'platform'
    ) THEN
        RAISE EXCEPTION 'Migration failed: transactions.platform column not created';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'transactions' AND column_name = 'purchase_token'
    ) THEN
        RAISE EXCEPTION 'Migration failed: transactions.purchase_token column not created';
    END IF;
    
    -- Check users table
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'subscription_platform'
    ) THEN
        RAISE EXCEPTION 'Migration failed: users.subscription_platform column not created';
    END IF;
    
    RAISE NOTICE '✅ Migration 001_add_google_play_support completed successfully';
END $$;