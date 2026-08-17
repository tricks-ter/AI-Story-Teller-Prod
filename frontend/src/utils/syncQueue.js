import { saveLocalLibrary, saveLocalStory, saveLocalPlaythrough, saveLocalMessages, setHudCache, saveLocalWorldNodes } from './localDb';
import { authHeaders, BASE_URL, parseJsonSafe } from './auth';
import { toast } from './toast';

class FIFOQueue {
  constructor() {
    this.queue = [];
    this.processing = false;
    this.activeTasks = new Set();
    this.processors = {};
    this._registerDefaultProcessors();
  }

  _registerDefaultProcessors() {
    this.processors['SYNC_LIBRARY'] = async (payload) => {
      const res = await fetch(`${BASE_URL}/stories?scope=all`, { headers: authHeaders() });
      if (res.ok) {
        const data = await parseJsonSafe(res);
        if (data) await saveLocalLibrary(payload.userId, data);
      }
    };

    this.processors['FETCH_STORY_DETAILS'] = async (payload) => {
      const res = await fetch(`${BASE_URL}/stories/${payload.storyId}`, { headers: authHeaders() });
      if (res.ok) {
        const data = await parseJsonSafe(res);
        if (data && data.story) await saveLocalStory(data.story);
      }
    };

    this.processors['FETCH_PLAYTHROUGH'] = async (payload) => {
      const res = await fetch(`${BASE_URL}/playthroughs/${payload.ptId}`, { headers: authHeaders() });
      if (res.ok) {
        const data = await parseJsonSafe(res);
        if (data) await saveLocalPlaythrough(data);
      }
    };

    this.processors['FETCH_MESSAGES'] = async (payload) => {
      const isPt = !!payload.playthroughId;
      const url = isPt
        ? `${BASE_URL}/playthroughs/${payload.playthroughId}/messages?limit=100`
        : `${BASE_URL}/stories/${payload.storyId}/messages?limit=50&base_only=true`;
      const res = await fetch(url, { headers: authHeaders() });
      if (res.ok) {
        const data = await parseJsonSafe(res);
        if (Array.isArray(data)) {
          await saveLocalMessages(isPt ? payload.playthroughId : payload.storyId, data, isPt);
        }
      }
    };

    // Phase 6: Background memory compression
    this.processors['COMPRESS_MEMORY'] = async (payload) => {
      const res = await fetch(`${BASE_URL}/playthroughs/${payload.ptId}/messages?limit=100`, { headers: authHeaders() });
      if (res.ok) {
        const data = await parseJsonSafe(res);
        if (Array.isArray(data) && data.length > 50) {
          await fetch(`${BASE_URL}/playthroughs/${payload.ptId}/compress`, {
            method: 'POST',
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({})
          });
        }
      }
    };

    // Phase 6/7: Fetch fresh HUD data from cloud and update local cache
    this.processors['SYNC_HUD'] = async (payload) => {
      const { ptId, key } = payload;
      if (key === 'inventory') {
        const res = await fetch(`${BASE_URL}/playthroughs/${ptId}/inventory`, { headers: authHeaders() });
        if (res.ok) {
          const data = await parseJsonSafe(res);
          if (data) await setHudCache(ptId, 'inventory', data);
        }
      } else if (key === 'map') {
        const res = await fetch(`${BASE_URL}/playthroughs/${ptId}/map`, { headers: authHeaders() });
        if (res.ok) {
          const data = await parseJsonSafe(res);
          if (data) await setHudCache(ptId, 'map', data);
        }
      } else if (key === 'world') {
        // FE-BUG-2 FIX: refresh world codex cache (nodes + events) in the background
        try {
          const [nr, er] = await Promise.all([
            fetch(`${BASE_URL}/playthroughs/${ptId}/world-nodes`, { headers: authHeaders() }),
            fetch(`${BASE_URL}/playthroughs/${ptId}/world-events`, { headers: authHeaders() }),
          ]);
          const nodes = nr.ok ? await parseJsonSafe(nr) : [];
          const events = er.ok ? await parseJsonSafe(er) : [];
          await setHudCache(ptId, 'world', {
            nodes: Array.isArray(nodes) ? nodes : [],
            events: Array.isArray(events) ? events : [],
            updated_at: Date.now()
          });
        } catch (e) { console.warn('[SYNC_HUD:world]', e); }
      }
    };

    // Phase 6: Execute an inventory mutation against the cloud, then reconcile cache
    this.processors['HUD_ACTION'] = async (payload) => {
      const { ptId, action, itemId } = payload;
      try {
        const res = await fetch(`${BASE_URL}/playthroughs/${ptId}/${action}`, {
          method: 'POST',
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ item_id: itemId })
        });
        // Reconcile: always refresh inventory cache from server after action
        const invRes = await fetch(`${BASE_URL}/playthroughs/${ptId}/inventory`, { headers: authHeaders() });
        if (invRes.ok) {
          const data = await parseJsonSafe(invRes);
          if (data) await setHudCache(ptId, 'inventory', data);
        }
        if (!res.ok) console.warn(`[HUD_ACTION] ${action} failed on server`);
      } catch (e) {
        console.warn('[HUD_ACTION] error', e);
      }
    };

    // Phase 7: Sync Procedural World Graph from cloud
    this.processors['SYNC_WORLD_NODES'] = async (payload) => {
      const { ptId } = payload;
      const res = await fetch(`${BASE_URL}/playthroughs/${ptId}/world-nodes`, { headers: authHeaders() });
      if (res.ok) {
        const data = await parseJsonSafe(res);
        if (Array.isArray(data)) {
          await saveLocalWorldNodes(ptId, data);
        }
      }
    };

    // Optimistic social writes: UI updates instantly, DB reconciles here.
    this.processors['SOCIAL_ACTION'] = async (payload) => {
      const { storyId, action } = payload;
      try {
        if (action === 'like') {
          // Idempotent explicit set — safe if the queue retries
          const res = await fetch(`${BASE_URL}/stories/${storyId}/like`, {
            method: 'POST',
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ liked: !!payload.liked })
          });
          if (!res.ok) console.warn('[SOCIAL_ACTION] like failed on server');
        } else if (action === 'comment_add') {
          const res = await fetch(`${BASE_URL}/stories/${storyId}/comments`, {
            method: 'POST',
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ content: payload.content })
          });
          if (!res.ok) {
            // Roll back the optimistic comment in the UI
            window.dispatchEvent(new CustomEvent('inkmind-social-fail', {
              detail: { storyId, kind: 'comment', tempId: payload.tempId }
            }));
            try { toast.error('Comment could not be posted'); } catch {}
          }
        } else if (action === 'comment_delete') {
          const res = await fetch(`${BASE_URL}/stories/${storyId}/comments/${payload.commentId}`, {
            method: 'DELETE',
            headers: authHeaders()
          });
          // 404 means already gone — fine. Anything else: surface it.
          if (!res.ok && res.status !== 404) {
            try { toast.error('Could not delete the comment'); } catch {}
          }
        }
      } catch (e) {
        console.warn('[SOCIAL_ACTION] error', e);
        if (action === 'comment_add') {
          window.dispatchEvent(new CustomEvent('inkmind-social-fail', {
            detail: { storyId, kind: 'comment', tempId: payload.tempId }
          }));
          try { toast.error('Comment could not be posted (offline)'); } catch {}
        }
      }
    };
  }

  enqueue(type, payload = {}, priority = 'normal') {
    const signature = `${type}:${JSON.stringify(payload)}`;
    if (this.activeTasks.has(signature)) return;
    const exists = this.queue.some(t => `${t.type}:${JSON.stringify(t.payload)}` === signature);
    if (exists) return;

    this.queue.push({ id: crypto.randomUUID(), type, payload, priority, attempts: 0, signature });
    this._processNext();
  }

  async _processNext() {
    if (this.processing || this.queue.length === 0 || !navigator.onLine) return;
    this.processing = true;

    this.queue.sort((a, b) => (a.priority === 'high' ? -1 : 1));
    const task = this.queue.shift();
    this.activeTasks.add(task.signature);

    try {
      if (this.processors[task.type]) {
        await this.processors[task.type](task.payload);
      }
    } catch (e) {
      console.warn(`[SyncQueue] Task ${task.type} failed.`, e);
    } finally {
      this.activeTasks.delete(task.signature);
    }

    this.processing = false;

    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(() => this._processNext());
    } else {
      setTimeout(() => this._processNext(), 50);
    }
  }
}

export const syncQueue = new FIFOQueue();

window.addEventListener('online', () => syncQueue._processNext());
