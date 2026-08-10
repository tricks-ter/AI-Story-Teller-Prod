-- Phase 7: Procedural World Expansion Foundation
-- Adjacency list with JSONB metadata for infinite-depth entity graphs

CREATE TABLE IF NOT EXISTS world_nodes (
    id VARCHAR(36) PRIMARY KEY,
    playthrough_id VARCHAR(36) NOT NULL REFERENCES playthroughs(id) ON DELETE CASCADE,
    parent_id VARCHAR(36) REFERENCES world_nodes(id) ON DELETE CASCADE,
    node_type VARCHAR(20) NOT NULL CHECK (node_type IN ('region', 'faction', 'settlement', 'location', 'npc', 'item', 'economy_state')),
    name VARCHAR(255) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_world_nodes_uniq_name 
ON world_nodes (playthrough_id, node_type, LOWER(name));

CREATE INDEX IF NOT EXISTS idx_world_nodes_parent 
ON world_nodes (parent_id);
