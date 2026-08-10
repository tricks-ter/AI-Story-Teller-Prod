import { BASE_URL, authHeaders } from "./auth";

export async function fetchStoriesArt(ids) {
  if (!ids || !ids.length) return {};
  try {
    const res = await fetch(`${BASE_URL}/art/stories?ids=${ids.join(",")}`, { headers: authHeaders() });
    if (!res.ok) return {};
    const data = await res.json();
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

export async function fetchCast(storyId) {
  try {
    const res = await fetch(`${BASE_URL}/stories/${storyId}/cast`, { headers: authHeaders() });
    if (!res.ok) return [];
    const d = await res.json();
    return Array.isArray(d) ? d : [];
  } catch {
    return [];
  }
}

export async function fetchPrologue(storyId) {
  try {
    const res = await fetch(`${BASE_URL}/stories/${storyId}/messages?limit=3&base_only=true`, { headers: authHeaders() });
    if (!res.ok) return "";
    const d = await res.json();
    const list = Array.isArray(d) ? d : [];
    const first = list.find(m => m.role === "assistant" || m.role === "system");
    return first?.content || "";
  } catch {
    return "";
  }
}

export async function uploadStoryArt(storyId, kind, dataUrl) {
  return fetch(`${BASE_URL}/stories/${storyId}/art`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ kind, data_url: dataUrl }),
  });
}

export async function uploadCharacterArt(storyId, charId, dataUrl) {
  return fetch(`${BASE_URL}/stories/${storyId}/characters/${charId}/art`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ data_url: dataUrl }),
  });
}

// Downscale on-device so DB rows stay small (rule 5: no bloat)
export function fileToDataUrl(file, maxDim = 640, quality = 0.82) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type || !file.type.startsWith("image/")) return reject(new Error("Please choose an image file"));
    if (file.size > 8 * 1024 * 1024) return reject(new Error("Image too large — max 8 MB"));
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL("image/jpeg", quality));
      };
      img.onerror = () => reject(new Error("Could not read that image"));
      img.src = reader.result;
    };
    reader.onerror = () => reject(new Error("Could not read the file"));
    reader.readAsDataURL(file);
  });
}
