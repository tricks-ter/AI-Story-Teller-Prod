// Central mapping: public futuristic names <-> real API model IDs.
// The IDs are machine identifiers required by the Z.AI backend.
// They are NEVER displayed in the UI.
export const MODELS = [
  {
    id: "glm-4.7-flash",
    name: "InkMind Nova",
    desc: "Latest · fastest · deep reasoning",
    badge: "Recommended",
  },
  {
    id: "glm-4.5-flash",
    name: "InkMind Pulse",
    desc: "Balanced speed and quality",
    badge: null,
  },
];

export const DEFAULT_MODEL_ID = "glm-4.7-flash";

export function modelName(id) {
  const m = MODELS.find((x) => x.id === id);
  return m ? m.name : MODELS[0].name;
}
