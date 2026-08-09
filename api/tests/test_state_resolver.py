import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.state_resolver import resolve_state, clean_entity_name, split_name_attrs

def test_time_update():
    clean, ups = resolve_state("Text [TIME_UPDATE: Day 3, Evening] more")
    assert ups == [{"type": "TIME_UPDATE", "day": 3, "time_of_day": "Evening"}]
    assert "[TIME_UPDATE" not in clean

def test_time_invalid_rejected():
    _, ups = resolve_state("[TIME_UPDATE: Day 3, Noon]")
    assert ups == []

def test_stat_equal():
    _, ups = resolve_state("[STAT_UPDATE: Kael.Health = 40]")
    assert ups[0]["stat"] == "Health" and ups[0]["value"] == 40 and not ups[0]["is_delta"]

def test_stat_delta():
    _, ups = resolve_state("[STAT_UPDATE: Kael.Mana -10]")
    assert ups[0]["is_delta"] and ups[0]["value"] == -10

def test_location():
    _, ups = resolve_state("[LOCATION_UPDATE: Sunset Forest]")
    assert ups == [{"type": "LOCATION_UPDATE", "location": "Sunset Forest"}]

def test_item_with_attrs():
    _, ups = resolve_state("[ITEM_UPDATE: Kael + Iron Sword | type=weapon, rarity=rare, level=4, weight=3, bonus.Health=10, desc=A blade]")
    u = ups[0]
    assert u["add"] and u["item"] == "Iron Sword"
    a = u["attrs"]
    assert a["type"] == "weapon" and a["rarity"] == "rare" and a["level"] == 4 and a["weight"] == 3
    assert a["bonuses"]["Health"] == 10 and a["description"] == "A blade"

def test_item_consume():
    _, ups = resolve_state("[ITEM_UPDATE: Kael - Healing Potion]")
    assert not ups[0]["add"] and ups[0]["item"] == "Healing Potion"

def test_ability():
    _, ups = resolve_state("[ABILITY_UPDATE: Kael + Spatial Step | desc=Blink short distances]")
    u = ups[0]
    assert u["type"] == "ABILITY_UPDATE" and u["ability"] == "Spatial Step" and u["description"] == "Blink short distances"

def test_bag():
    _, ups = resolve_state("[BAG_UPDATE: Kael level 2]")
    assert ups == [{"type": "BAG_UPDATE", "character": "Kael", "level": 2}]

def test_tags_stripped():
    clean, _ = resolve_state("Before [LOCATION_UPDATE: Town] After")
    assert clean == "Before After" or clean == "Before  After"

# ── Phase 5.5 additions ──
def test_item_comma_attrs_salvaged():
    _, ups = resolve_state("[ITEM_UPDATE: Lin + Soul Ring (1,000 years, Corrupted), slot=ring, rarity=rare | type=accessory, desc=Violet ring]")
    u = ups[0]
    assert u["item"] == "Soul Ring (1,000 years, Corrupted)"
    assert u["attrs"].get("slot") == "ring" and u["attrs"].get("rarity") == "rare"
    assert u["attrs"].get("type") == "accessory"

def test_item_comma_only_attrs():
    _, ups = resolve_state("[ITEM_UPDATE: Lin + Obsidian Shard, type=material, weight=2]")
    u = ups[0]
    assert u["item"] == "Obsidian Shard"
    assert u["attrs"].get("type") == "material" and u["attrs"].get("weight") == 2

def test_clean_entity_name():
    assert clean_entity_name("Weird Name, slot=ring, rarity=common") == "Weird Name"
    assert clean_entity_name("  Too   Many   Spaces ") == "Too Many Spaces"
    assert len(clean_entity_name("x" * 200)) <= 60

def test_split_name_attrs_no_tail():
    name, tail = split_name_attrs("Kael + Iron Sword")
    assert name == "Kael + Iron Sword" and tail == ""

def test_next_tick():
    from core.state_sync import next_tick
    assert next_tick(1, "Morning") == (1, "Afternoon")
    assert next_tick(1, "Night") == (2, "Morning")
