import { getHudCache, setHudCache } from './localDb';

// Central manager for lightning-fast HUD state.
// All reads hit IndexedDB first; mutations apply optimistically before cloud sync.

export async function getCachedInventory(playthroughId) {
  return await getHudCache(playthroughId, 'inventory');
}

export async function getCachedMap(playthroughId) {
  return await getHudCache(playthroughId, 'map');
}

export async function cacheInventory(playthroughId, data) {
  if (!data) return;
  await setHudCache(playthroughId, 'inventory', data);
}

export async function cacheMap(playthroughId, data) {
  if (!data) return;
  await setHudCache(playthroughId, 'map', data);
}

// Optimistic mutation: apply an item action to the cached inventory instantly.
export async function optimisticItemAction(playthroughId, action, itemId) {
  const inv = await getCachedInventory(playthroughId);
  if (!inv || !Array.isArray(inv.items)) return;

  const item = inv.items.find(i => i.id === itemId);
  if (!item) return;

  if (action === 'use' || action === 'drop') {
    if ((item.quantity || 1) <= 1) {
      inv.items = inv.items.filter(i => i.id !== itemId);
      inv.equipment = (inv.equipment || []).filter(e => e.item_id !== itemId);
    } else {
      item.quantity = item.quantity - 1;
    }
    if (action === 'use') item.equipped = false;
  } else if (action === 'equip') {
    inv.items.forEach(i => { if (i.slot === item.slot && i.id !== itemId) i.equipped = false; });
    item.equipped = true;
    inv.equipment = (inv.equipment || []).filter(e => e.slot !== item.slot);
    inv.equipment.push({ item_id: itemId, slot: item.slot, item_name: item.name, rarity: item.rarity, item_level: item.item_level });
  } else if (action === 'unequip') {
    item.equipped = false;
    inv.equipment = (inv.equipment || []).filter(e => e.item_id !== itemId);
  }

  await cacheInventory(playthroughId, inv);
}

// Optimistic mutation: apply an AI state_update to cached stats/location.
export async function applyStateUpdateToCache(playthroughId, storyContext) {
  if (!storyContext) return;
  await setHudCache(playthroughId, 'story_context', {
    current_day: storyContext.current_day,
    time_of_day: storyContext.time_of_day,
    current_location: storyContext.current_location,
    status: storyContext.status,
    characters: storyContext.characters || []
  });
}

export async function getCachedStoryContext(playthroughId) {
  return await getHudCache(playthroughId, 'story_context');
}
