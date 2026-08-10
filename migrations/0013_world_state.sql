-- 0013_world_state.sql — Living world: entity state columns + event ledger
-- Additive-only; deploy-order safe (0012 creates world_nodes first).
ALTER TABLE world_nodes ADD COLUMN IF NOT EXISTS status VARCHAR(64) NOT NULL DEFAULT 'stable';
ALTER TABLE world_nodes ADD COLUMN IF NOT EXISTS is_alive BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE world_nodes ADD COLUMN IF NOT EXISTS relationship INT NOT NULL DEFAULT 0;
ALTER TABLE world_nodes ADD COLUMN IF NOT EXISTS wealth INT NOT NULL DEFAULT 0;
ALTER TABLE world_nodes ADD COLUMN IF NOT EXISTS power INT NOT NULL DEFAULT 50;
ALTER TABLE world_nodes ADD COLUMN IF NOT EXISTS allegiance VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE world_nodes ADD COLUMN IF NOT EXISTS last_state_change_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS world_events (
    id VARCHAR(36) PRIMARY KEY,
    playthrough_id VARCHAR(36) NOT NULL REFERENCES playthroughs(id) ON DELETE CASCADE,
    node_id VARCHAR(36) NOT NULL DEFAULT '',
    node_name VARCHAR(255) NOT NULL DEFAULT '',
    event_type VARCHAR(32) NOT NULL DEFAULT 'event',
    description TEXT NOT NULL DEFAULT '',
    day INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_world_events_pt ON world_events (playthrough_id, day DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_world_nodes_state ON world_nodes (playthrough_id, node_type);
