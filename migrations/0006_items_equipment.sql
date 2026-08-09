-- 0006: Item levels, equipment slots, backpack capacity

CREATE TABLE IF NOT EXISTS playthrough_items (
    id VARCHAR(36) PRIMARY KEY,
    playthrough_id VARCHAR(36) NOT NULL REFERENCES playthroughs(id) ON DELETE CASCADE,
    character_id VARCHAR(36) NOT NULL REFERENCES playthrough_characters(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    item_type VARCHAR(50) NOT NULL DEFAULT 'material',
    slot VARCHAR(50) NOT NULL DEFAULT '',
    rarity VARCHAR(20) NOT NULL DEFAULT 'common',
    item_level INT NOT NULL DEFAULT 1,
    weight INT NOT NULL DEFAULT 1,
    quantity INT NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_items_type CHECK (item_type IN ('weapon','armor','accessory','consumable','material','quest')),
    CONSTRAINT chk_items_slot CHECK (slot IN ('','main_hand','off_hand','head','body','ring','amulet','trinket')),
    CONSTRAINT chk_items_rarity CHECK (rarity IN ('common','uncommon','rare','epic','legendary')),
    CONSTRAINT chk_items_level CHECK (item_level BETWEEN 1 AND 99),
    CONSTRAINT chk_items_weight CHECK (weight BETWEEN 0 AND 99),
    CONSTRAINT chk_items_qty CHECK (quantity BETWEEN 1 AND 99)
);

CREATE TABLE IF NOT EXISTS playthrough_equipment (
    id VARCHAR(36) PRIMARY KEY,
    playthrough_id VARCHAR(36) NOT NULL REFERENCES playthroughs(id) ON DELETE CASCADE,
    character_id VARCHAR(36) NOT NULL REFERENCES playthrough_characters(id) ON DELETE CASCADE,
    item_id VARCHAR(36) NOT NULL REFERENCES playthrough_items(id) ON DELETE CASCADE,
    slot VARCHAR(50) NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playthrough_backpacks (
    id VARCHAR(36) PRIMARY KEY,
    playthrough_id VARCHAR(36) NOT NULL REFERENCES playthroughs(id) ON DELETE CASCADE,
    character_id VARCHAR(36) NOT NULL REFERENCES playthrough_characters(id) ON DELETE CASCADE,
    level INT NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_backpack_level CHECK (level BETWEEN 1 AND 20)
);

-- Invariants & hot paths
CREATE UNIQUE INDEX IF NOT EXISTS uniq_equipment_slot ON playthrough_equipment(character_id, slot);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_backpack_character ON playthrough_backpacks(character_id);
CREATE INDEX IF NOT EXISTS idx_items_playthrough ON playthrough_items(playthrough_id);
CREATE INDEX IF NOT EXISTS idx_items_character ON playthrough_items(character_id);
CREATE INDEX IF NOT EXISTS idx_equipment_playthrough ON playthrough_equipment(playthrough_id);
CREATE INDEX IF NOT EXISTS idx_equipment_character ON playthrough_equipment(character_id);
CREATE INDEX IF NOT EXISTS idx_backpacks_playthrough ON playthrough_backpacks(playthrough_id);

-- Auto updated_at (function re-declared idempotently for safety)
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_items_updated_at ON playthrough_items;
CREATE TRIGGER trg_items_updated_at BEFORE UPDATE ON playthrough_items
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_backpacks_updated_at ON playthrough_backpacks;
CREATE TRIGGER trg_backpacks_updated_at BEFORE UPDATE ON playthrough_backpacks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
