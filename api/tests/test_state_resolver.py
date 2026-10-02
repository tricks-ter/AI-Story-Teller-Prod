import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.state_resolver import resolve_state

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
    assert ups == [{"type": "LOCATION_UPDATE", "location": "Sunset Forest", "description": ""}]


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
    assert "Town" not in clean

def test_saga_end_without_colon():
    clean, ups = resolve_state("The hero rested. [SAGA_END]")
    assert any(u["type"] == "SAGA_END" for u in ups)
    assert "[SAGA_END]" not in clean

def test_saga_end_with_colon():
    clean, ups = resolve_state("The hero rested. [SAGA_END: victory achieved]")
    assert any(u["type"] == "SAGA_END" for u in ups)
    assert "[SAGA_END" not in clean

def test_hyphenated_and_apostrophe_names():
    _, ups1 = resolve_state("[STAT_UPDATE: Jean-Luc.Health = 50]")
    assert ups1[0]["character"] == "Jean-Luc" and ups1[0]["value"] == 50

    _, ups2 = resolve_state("[ITEM_UPDATE: Kael'thas + Mystic Orb | type=accessory, rarity=epic]")
    assert ups2[0]["character"] == "Kael'thas" and ups2[0]["item"] == "Mystic Orb"

def test_comma_in_description():
    _, ups = resolve_state("[ITEM_UPDATE: Kael + Herb | type=consumable, desc=A soothing herb, gathered near the river]")
    assert ups[0]["attrs"]["description"] == "A soothing herb, gathered near the river"

