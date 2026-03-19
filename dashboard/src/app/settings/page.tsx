"use client";

import { useEffect, useState } from "react";
import GlassCard from "@/components/GlassCard";
import {
  api,
  type SettingsResponse,
  type ProviderTestResult,
  type ZoteroCollection,
} from "@/lib/api";

type TestState = Record<string, { ok: boolean; message: string } | null>;

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState<TestState>({});
  const [saveMsg, setSaveMsg] = useState("");
  const [collections, setCollections] = useState<ZoteroCollection[]>([]);

  // Form fields (raw input — only sent on save)
  const [openaiKey, setOpenaiKey] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [googleKey, setGoogleKey] = useState("");
  const [zoteroLibId, setZoteroLibId] = useState("");
  const [zoteroApiKey, setZoteroApiKey] = useState("");
  const [zoteroLibType, setZoteroLibType] = useState("user");
  const [budget, setBudget] = useState("10.00");
  const [backend, setBackend] = useState<"api" | "cli">("api");

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s);
        setZoteroLibId(s.zotero_library_id);
        setZoteroLibType(s.zotero_library_type);
        setBudget(s.cost_budget_usd.toString());
        setBackend(s.llm_backend || "cli");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Fetch collections when zotero creds exist
  useEffect(() => {
    if (settings && settings.zotero_library_id && settings.zotero_api_key) {
      api.listZoteroCollections().then(setCollections).catch(() => {});
    }
  }, [settings]);

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      const update: Record<string, unknown> = {};
      if (openaiKey) update.openai_api_key = openaiKey;
      if (anthropicKey) update.anthropic_api_key = anthropicKey;
      if (googleKey) update.google_api_key = googleKey;
      if (zoteroLibId) update.zotero_library_id = zoteroLibId;
      if (zoteroApiKey) update.zotero_api_key = zoteroApiKey;
      update.zotero_library_type = zoteroLibType;
      update.cost_budget_usd = parseFloat(budget) || 10.0;
      update.llm_backend = backend;

      const updated = await api.updateSettings(update);
      setSettings(updated);
      // Clear raw key inputs after save
      setOpenaiKey("");
      setAnthropicKey("");
      setGoogleKey("");
      setZoteroApiKey("");
      setSaveMsg("Settings saved successfully.");
    } catch (err) {
      setSaveMsg(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResults({});
    try {
      const resp = await api.testSettings();
      const map: TestState = {};
      resp.results.forEach((r: ProviderTestResult) => {
        map[r.provider] = { ok: r.ok, message: r.message };
      });
      setTestResults(map);
    } catch {
      setTestResults({});
    } finally {
      setTesting(false);
    }
  };

  const StatusDot = ({ provider }: { provider: string }) => {
    const result = testResults[provider];
    if (!result) return null;
    return (
      <span
        className={`inline-block w-2 h-2 rounded-full ml-2 ${
          result.ok ? "bg-[var(--accent-teal)]" : "bg-[var(--accent-rose)]"
        }`}
        title={result.message}
        style={result.ok ? { boxShadow: "0 0 6px var(--accent-teal)" } : {}}
      />
    );
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="shimmer h-8 w-48" />
        <div className="shimmer h-64" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white/90">Settings</h2>
        <p className="text-sm text-white/40 mt-1">
          Configure API keys, Zotero integration, and budget
        </p>
      </div>

      {/* LLM Backend Toggle */}
      <GlassCard hover={false}>
        <h3 className="text-base font-semibold text-white/80 mb-4">LLM Backend</h3>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => setBackend("cli")}
            className={`glass-subtle p-5 text-left transition-all cursor-pointer ${
              backend === "cli"
                ? "border-[var(--accent-teal)] bg-white/[0.06]"
                : "hover:bg-white/[0.03]"
            }`}
            style={backend === "cli" ? { borderColor: "var(--accent-teal)", borderWidth: 1 } : {}}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-sm font-semibold ${
                backend === "cli" ? "text-[var(--accent-teal)]" : "text-white/70"
              }`}>
                CLI Mode
              </span>
              <span className="glass-badge badge-completed text-[10px]">FREE</span>
            </div>
            <p className="text-xs text-white/35">
              Uses locally installed Gemini CLI, Codex CLI, and Claude Code via subprocess. No API costs.
            </p>
          </button>
          <button
            type="button"
            onClick={() => setBackend("api")}
            className={`glass-subtle p-5 text-left transition-all cursor-pointer ${
              backend === "api"
                ? "border-[var(--accent-blue)] bg-white/[0.06]"
                : "hover:bg-white/[0.03]"
            }`}
            style={backend === "api" ? { borderColor: "var(--accent-blue)", borderWidth: 1 } : {}}
          >
            <span className={`text-sm font-semibold ${
              backend === "api" ? "text-[var(--accent-blue)]" : "text-white/70"
            }`}>
              API Mode
            </span>
            <p className="text-xs text-white/35 mt-2">
              Uses LLM provider APIs via litellm. Requires API keys. Faster, more reliable, costs money.
            </p>
          </button>
        </div>
        {backend === "cli" && (
          <div className="mt-4 glass-subtle p-3 space-y-3">
            <p className="text-xs text-white/60 font-medium">Setup CLI tools (one-time install)</p>
            <pre className="text-xs text-[var(--accent-teal)] font-mono bg-black/20 rounded p-2 select-all leading-relaxed">{`npm install -g @anthropic-ai/claude-code   # claude
npm install -g @openai/codex               # codex
npm install -g @google/gemini-cli          # gemini`}</pre>
            <p className="text-xs text-white/40">
              After installing, use{" "}
              <span className="text-white/60">&quot;Test Connections&quot;</span>{" "}
              below to verify each tool is accessible. No API keys required in CLI mode.
            </p>
          </div>
        )}
      </GlassCard>

      {/* LLM API Keys */}
      <GlassCard hover={false}>
        <h3 className="text-base font-semibold text-white/80 mb-5">
          LLM API Keys
          {backend === "cli" && (
            <span className="text-xs text-white/25 font-normal ml-2">(not required in CLI mode)</span>
          )}
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-white/60 mb-1">
              OpenAI <StatusDot provider="openai" />
            </label>
            <input
              type="password"
              className="glass-input"
              placeholder={settings?.openai_api_key || "sk-..."}
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-white/60 mb-1">
              Anthropic <StatusDot provider="anthropic" />
            </label>
            <input
              type="password"
              className="glass-input"
              placeholder={settings?.anthropic_api_key || "sk-ant-..."}
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-white/60 mb-1">
              Google <StatusDot provider="google" />
            </label>
            <input
              type="password"
              className="glass-input"
              placeholder={settings?.google_api_key || "AI..."}
              value={googleKey}
              onChange={(e) => setGoogleKey(e.target.value)}
            />
          </div>
        </div>
      </GlassCard>

      {/* Zotero */}
      <GlassCard hover={false}>
        <h3 className="text-base font-semibold text-white/80 mb-5">
          Zotero Integration <StatusDot provider="zotero" />
        </h3>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-white/60 mb-1">Library ID</label>
            <input
              className="glass-input"
              placeholder="e.g. 12345678"
              value={zoteroLibId}
              onChange={(e) => setZoteroLibId(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-white/60 mb-1">API Key</label>
            <input
              type="password"
              className="glass-input"
              placeholder={settings?.zotero_api_key || "Enter Zotero API key"}
              value={zoteroApiKey}
              onChange={(e) => setZoteroApiKey(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-white/60 mb-2">Library Type</label>
            <div className="flex gap-3">
              {(["user", "group"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setZoteroLibType(t)}
                  className={`glass-subtle px-4 py-2 text-sm capitalize cursor-pointer transition-all ${
                    zoteroLibType === t
                      ? "border-[var(--accent-blue)] bg-white/[0.06] text-white/80"
                      : "text-white/40 hover:bg-white/[0.03]"
                  }`}
                  style={zoteroLibType === t ? { borderColor: "var(--accent-blue)", borderWidth: 1 } : {}}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {collections.length > 0 && (
            <div>
              <label className="block text-sm text-white/60 mb-2">Collections</label>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {collections.map((c) => (
                  <div
                    key={c.key}
                    className="flex justify-between text-sm glass-subtle px-3 py-2"
                  >
                    <span className="text-white/60">{c.name}</span>
                    <span className="text-white/30 font-mono text-xs">{c.num_items} items</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <p className="text-xs text-white/25 mt-4">
          Get your API key at zotero.org/settings/keys. Library ID is in your Zotero profile URL.
        </p>
      </GlassCard>

      {/* General */}
      <GlassCard hover={false}>
        <h3 className="text-base font-semibold text-white/80 mb-5">General</h3>
        <div>
          <label className="block text-sm text-white/60 mb-1">Cost Budget (USD)</label>
          <input
            type="number"
            step="0.50"
            min="0"
            className="glass-input w-40"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
          <p className="text-xs text-white/25 mt-1">Pipeline stops when this budget is exceeded.</p>
        </div>
      </GlassCard>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className={`glass-btn glass-btn-primary px-6 py-2.5 text-sm font-semibold ${
            saving ? "opacity-50 cursor-wait" : ""
          }`}
        >
          {saving ? "Saving..." : "Save All"}
        </button>
        <button
          onClick={handleTest}
          disabled={testing}
          className={`glass-btn px-6 py-2.5 text-sm ${testing ? "opacity-50 cursor-wait" : ""}`}
        >
          {testing ? "Testing..." : "Test Connections"}
        </button>
        {saveMsg && (
          <span
            className={`text-sm ${
              saveMsg.includes("success") ? "text-[var(--accent-teal)]" : "text-[var(--accent-rose)]"
            }`}
          >
            {saveMsg}
          </span>
        )}
      </div>

      {/* Test results summary */}
      {Object.keys(testResults).length > 0 && (
        <GlassCard hover={false}>
          <h3 className="text-base font-semibold text-white/80 mb-4">Connection Status</h3>
          <div className="space-y-2">
            {Object.entries(testResults).map(([provider, result]) =>
              result ? (
                <div key={provider} className="flex items-center justify-between text-sm">
                  <span className="text-white/60 capitalize">{provider}</span>
                  <span
                    className={`font-mono text-xs ${
                      result.ok ? "text-[var(--accent-teal)]" : "text-[var(--accent-rose)]"
                    }`}
                  >
                    {result.ok ? "Connected" : result.message}
                  </span>
                </div>
              ) : null
            )}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
