-- Migration 003: Add spread_at_entry column to positions table
-- Records the bid-ask spread percentage at the time of position entry
-- Used for analytics and strategy calibration

ALTER TABLE monitoring.positions
    ADD COLUMN IF NOT EXISTS spread_at_entry DECIMAL(10, 4);

COMMENT ON COLUMN monitoring.positions.spread_at_entry
    IS 'Bid-ask spread percentage at time of entry';
