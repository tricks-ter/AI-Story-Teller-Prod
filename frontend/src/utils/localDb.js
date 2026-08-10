import { openDB } from 'idb';

const DB_NAME = 'inkmind_local';
const DB_VERSION = 2;

let dbPromise = null;

export function getDB() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion) {
        if (!db.objectStoreNames.contains('user_session')) {
          db.createObjectStore('user_session', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('stories')) {
          db.createObjectStore('stories', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('playthroughs')) {
          db.createObjectStore('playthroughs', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('messages')) {
          const msgStore = db.createObjectStore('messages', { keyPath: 'id' });
          msgStore.createIndex('session_id', 'session_id');
          msgStore.createIndex('playthrough_id', 'playthrough_id');
        }
        if (!db.objectStoreNames.contains('library_feed')) {
          db.createObjectStore('library_feed', { keyPath: 'user_id' });
        }
        // Phase 6: HUD state cache for lightning-fast inventory/map/stats
        if (!db.objectStoreNames.contains('hud_cache')) {
          const hudStore = db.createObjectStore('hud_cache', { keyPath: 'cache_key' });
          hudStore.createIndex('playthrough_id', 'playthrough_id');
        }
      }
    });
  }
  return dbPromise;
}

// --- HOT DATA HELPERS ---
export async function getLocalUser() {
  const db = await getDB();
  const users = await db.getAll('user_session');
  return users.length > 0 ? users[0] : null;
}

export async function saveLocalUser(user) {
  if (!user || !user.id) return;
  const db = await getDB();
  await db.put('user_session', user);
}

export async function getLocalLibrary(userId) {
  const db = await getDB();
  const feed = await db.get('library_feed', userId || 'default');
  return feed ? feed.stories : null;
}

export async function saveLocalLibrary(userId, stories) {
  const db = await getDB();
  await db.put('library_feed', { user_id: userId || 'default', stories, updated_at: Date.now() });
}

// --- WARM DATA HELPERS ---
export async function getLocalStory(storyId) {
  const db = await getDB();
  return await db.get('stories', storyId);
}

export async function saveLocalStory(story) {
  if (!story || !story.id) return;
  const db = await getDB();
  await db.put('stories', { ...story, cached_at: Date.now() });
}

export async function getLocalPlaythrough(ptId) {
  const db = await getDB();
  return await db.get('playthroughs', ptId);
}

export async function saveLocalPlaythrough(pt) {
  if (!pt || !pt.id) return;
  const db = await getDB();
  await db.put('playthroughs', { ...pt, cached_at: Date.now() });
}

export async function getLocalMessages(contextId) {
  const db = await getDB();
  let msgs = await db.getAllFromIndex('messages', 'playthrough_id', contextId);
  if (!msgs || msgs.length === 0) {
    msgs = await db.getAllFromIndex('messages', 'session_id', contextId);
  }
  return msgs || [];
}

export async function saveLocalMessages(contextId, messages, isPlaythrough = false) {
  const db = await getDB();
  const tx = db.transaction('messages', 'readwrite');
  const indexName = isPlaythrough ? 'playthrough_id' : 'session_id';
  const index = tx.store.index(indexName);
  
  for await (const cursor of index.iterate(contextId)) {
    await cursor.delete();
  }
  
  for (const msg of messages) {
    await tx.store.put({
      ...msg,
      session_id: isPlaythrough ? null : contextId,
      playthrough_id: isPlaythrough ? contextId : null
    });
  }
  await tx.done;
}

// --- HUD CACHE HELPERS (Phase 6: Lightning-fast HUD) ---
export async function getHudCache(playthroughId, key) {
  try {
    const db = await getDB();
    const row = await db.get('hud_cache', `${playthroughId}:${key}`);
    return row ? row.data : null;
  } catch { return null; }
}

export async function setHudCache(playthroughId, key, data) {
  try {
    const db = await getDB();
    await db.put('hud_cache', {
      cache_key: `${playthroughId}:${key}`,
      playthrough_id: playthroughId,
      key: key,
      data: data,
      cached_at: Date.now()
    });
  } catch (e) { console.warn('[hudCache] set failed', e); }
}

export async function clearHudCache(playthroughId) {
  try {
    const db = await getDB();
    const tx = db.transaction('hud_cache', 'readwrite');
    const index = tx.store.index('playthrough_id');
    for await (const cursor of index.iterate(playthroughId)) {
      await cursor.delete();
    }
    await tx.done;
  } catch (e) { console.warn('[hudCache] clear failed', e); }
}

// --- SECURITY / LIFECYCLE ---
export async function clearLocalDB() {
  const db = await getDB();
  const storeNames = ['user_session', 'stories', 'playthroughs', 'messages', 'library_feed', 'hud_cache'];
  const tx = db.transaction(storeNames, 'readwrite');
  for (const name of storeNames) {
    await tx.objectStore(name).clear();
  }
  await tx.done;
}
