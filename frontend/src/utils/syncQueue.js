import { saveLocalLibrary, saveLocalStory, saveLocalPlaythrough, saveLocalMessages } from './localDb';
import { authHeaders, BASE_URL, parseJsonSafe } from './auth';

class FIFOQueue {
  constructor() {
    this.queue = [];
    this.processing = false;
    this.activeTasks = new Set(); // FIX: Track active signatures to prevent race conditions
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
  }

  enqueue(type, payload = {}, priority = 'normal') {
    const signature = `${type}:${JSON.stringify(payload)}`;
    // FIX: Prevent duplicate enqueuing if task is currently processing or already queued
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
