import { X, Cpu, Brain, Sliders, Thermometer, ChevronRight } from "lucide-react";

const MODELS = [
  {
    id: "glm-4.7-flash",
    name: "GLM-4.7 Flash",
    desc: "Latest · fast · reasoning support",
    badge: "Recommended",
  },
  {
    id: "glm-4.5-flash",
    name: "GLM-4.5 Flash",
    desc: "Balanced speed and quality",
    badge: null,
  },
  {
    id: "glm-4-flash",
    name: "GLM-4 Flash",
    desc: "Stable · widely tested",
    badge: null,
  },
];

function Toggle({ checked, onChange }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative flex-shrink-0 w-12 h-6 rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
        checked ? "bg-brand-600" : "bg-gray-600"
      }`}
    >
      <span
        className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow transition-transform duration-200 ${
          checked ? "translate-x-6" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function Slider({ min, max, step, value, onChange, format }) {
  return (
    <div className="space-y-2">
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-700 accent-brand-500"
        style={{ touchAction: "none" }}
      />
      <div className="flex justify-between text-xs text-gray-500">
        <span>{format(min)}</span>
        <span className="text-brand-400 font-medium">{format(value)}</span>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}

export default function SettingsPanel({ settings, onChange, onClose }) {
  const update = (key, val) => onChange({ ...settings, [key]: val });

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      {/* Panel — bottom sheet on mobile, centred card on sm+ */}
      <div className="w-full sm:max-w-md bg-gray-900 border border-gray-700/80 rounded-t-3xl sm:rounded-2xl overflow-hidden shadow-2xl animate-slide-up">
        {/* Drag handle (mobile) */}
        <div className="flex justify-center pt-3 pb-1 sm:hidden">
          <div className="w-10 h-1 rounded-full bg-gray-600" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Sliders size={18} className="text-brand-400" />
            <h3 className="text-white font-semibold text-base">Chat Settings</h3>
          </div>
          <button
            onClick={onClose}
            className="w-9 h-9 flex items-center justify-center rounded-xl hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-6 overflow-y-auto max-h-[75vh]">
          {/* ── Model ─────────────────────────────────────────────────── */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <Cpu size={15} className="text-gray-400" />
              <span className="text-sm font-medium text-gray-300">Model</span>
            </div>
            <div className="space-y-2">
              {MODELS.map((m) => (
                <button
                  key={m.id}
                  onClick={() => update("model", m.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-colors min-h-[56px] ${
                    settings.model === m.id
                      ? "border-brand-500 bg-brand-500/10"
                      : "border-gray-700 bg-gray-800 hover:bg-gray-750"
                  }`}
                >
                  <div
                    className={`w-3 h-3 rounded-full flex-shrink-0 ${
                      settings.model === m.id ? "bg-brand-500" : "bg-gray-600"
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-sm font-medium ${
                          settings.model === m.id ? "text-white" : "text-gray-300"
                        }`}
                      >
                        {m.name}
                      </span>
                      {m.badge && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand-500/20 text-brand-400 font-medium">
                          {m.badge}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">{m.desc}</p>
                  </div>
                  {settings.model === m.id && (
                    <ChevronRight size={14} className="text-brand-400 flex-shrink-0" />
                  )}
                </button>
              ))}
            </div>
          </section>

          {/* ── Reasoning toggle ──────────────────────────────────────── */}
          <section className="flex items-center justify-between py-1">
            <div className="flex items-start gap-3">
              <Brain size={15} className="text-gray-400 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-gray-300">Reasoning Mode</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {settings.enableThinking
                    ? "Model shows its thinking process"
                    : "Faster — no chain-of-thought output"}
                </p>
              </div>
            </div>
            <Toggle
              checked={settings.enableThinking}
              onChange={(v) => update("enableThinking", v)}
            />
          </section>

          {/* ── Max tokens ────────────────────────────────────────────── */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-gray-400 text-sm">📝</span>
                <span className="text-sm font-medium text-gray-300">Max Tokens</span>
              </div>
              <span className="text-brand-400 font-mono text-sm font-medium">
                {settings.maxTokens.toLocaleString()}
              </span>
            </div>
            <Slider
              min={1024}
              max={8192}
              step={256}
              value={settings.maxTokens}
              onChange={(v) => update("maxTokens", v)}
              format={(v) => v.toLocaleString()}
            />
            <p className="text-xs text-gray-500 mt-2">
              Higher values allow longer responses but use more quota.
            </p>
          </section>

          {/* ── Temperature ───────────────────────────────────────────── */}
          <section className="pb-2">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Thermometer size={15} className="text-gray-400" />
                <span className="text-sm font-medium text-gray-300">Temperature</span>
              </div>
              <span className="text-brand-400 font-mono text-sm font-medium">
                {settings.temperature.toFixed(1)}
              </span>
            </div>
            <Slider
              min={0}
              max={1.0}
              step={0.1}
              value={settings.temperature}
              onChange={(v) => update("temperature", parseFloat(v.toFixed(1)))}
              format={(v) => v.toFixed(1)}
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>Focused / deterministic</span>
              <span>Creative / varied</span>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-800">
          <button
            onClick={onClose}
            className="w-full py-3 rounded-xl bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium transition-colors min-h-[48px]"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
