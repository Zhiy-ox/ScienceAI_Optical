"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import GlassCard from "@/components/GlassCard";
import { api, type ZoteroCollection } from "@/lib/api";

export default function NewResearchPage() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [maxPapers, setMaxPapers] = useState(15);
  const [phase, setPhase] = useState(3);
  const [background, setBackground] = useState("");
  const [source, setSource] = useState<"web" | "zotero" | "both">("web");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [keysConfigured, setKeysConfigured] = useState(true);
  const [zoteroConfigured, setZoteroConfigured] = useState(false);
  const [collections, setCollections] = useState<ZoteroCollection[]>([]);

  useEffect(() => {
    api.getSettings()
      .then((s) => {
        const hasKey = !!(s.openai_api_key || s.anthropic_api_key || s.google_api_key);
        setKeysConfigured(hasKey);
        setZoteroConfigured(!!(s.zotero_library_id && s.zotero_api_key));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (zoteroConfigured) {
      api.listZoteroCollections().then(setCollections).catch(() => {});
    }
  }, [zoteroConfigured]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError("");

    try {
      const res = await api.startResearch({
        question: question.trim(),
        max_papers: maxPapers,
        phase,
        user_background: background.trim(),
        source,
      });
      router.push(`/session?id=${res.session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start research");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white/90">New Research</h2>
        <p className="text-sm text-white/40 mt-1">
          Start a new AI-powered literature review
        </p>
      </div>

      {/* API key warning */}
      {!keysConfigured && (
        <GlassCard hover={false}>
          <div className="flex items-center gap-3">
            <svg className="w-5 h-5 text-[var(--accent-amber)] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <div>
              <p className="text-sm text-[var(--accent-amber)] font-medium">API keys not configured</p>
              <p className="text-xs text-white/40 mt-0.5">
                <Link href="/settings" className="text-[var(--accent-blue)] hover:text-[var(--accent-teal)]">
                  Configure your API keys in Settings
                </Link>{" "}
                before starting research.
              </p>
            </div>
          </div>
        </GlassCard>
      )}

      <GlassCard hover={false}>
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Research Question */}
          <div>
            <label className="block text-sm font-medium text-white/60 mb-2">
              Research Question
            </label>
            <textarea
              className="glass-input min-h-[100px] resize-y"
              placeholder="e.g., What are the latest advances in silicon-based optical phased arrays for LiDAR?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              required
            />
          </div>

          {/* Paper Source */}
          <div>
            <label className="block text-sm font-medium text-white/60 mb-3">
              Paper Source
            </label>
            <div className="grid grid-cols-3 gap-3">
              {([
                { value: "web" as const, label: "Web Search", desc: "Semantic Scholar + arXiv" },
                { value: "zotero" as const, label: "Zotero Library", desc: "Your personal library" },
                { value: "both" as const, label: "Both", desc: "Web + Zotero combined" },
              ]).map((s) => (
                <button
                  key={s.value}
                  type="button"
                  onClick={() => setSource(s.value)}
                  disabled={s.value !== "web" && !zoteroConfigured}
                  className={`glass-subtle p-4 text-left transition-all ${
                    s.value !== "web" && !zoteroConfigured
                      ? "opacity-30 cursor-not-allowed"
                      : "cursor-pointer"
                  } ${
                    source === s.value
                      ? "border-[var(--accent-blue)] bg-white/[0.06]"
                      : "hover:bg-white/[0.03]"
                  }`}
                  style={source === s.value ? { borderColor: "var(--accent-blue)", borderWidth: 1 } : {}}
                >
                  <span className={`text-sm font-semibold ${
                    source === s.value ? "text-[var(--accent-blue)]" : "text-white/70"
                  }`}>
                    {s.label}
                  </span>
                  <p className="text-xs text-white/35 mt-1">{s.desc}</p>
                </button>
              ))}
            </div>
            {!zoteroConfigured && (
              <p className="text-xs text-white/25 mt-2">
                <Link href="/settings" className="text-[var(--accent-blue)]">Configure Zotero</Link> to use library sources.
              </p>
            )}
          </div>

          {/* Zotero collections hint */}
          {(source === "zotero" || source === "both") && collections.length > 0 && (
            <div className="glass-subtle p-3">
              <p className="text-xs text-white/40 mb-2">Available collections in your library:</p>
              <div className="flex flex-wrap gap-2">
                {collections.slice(0, 8).map((c) => (
                  <span key={c.key} className="glass-badge badge-started text-[10px]">
                    {c.name} ({c.num_items})
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Phase selector */}
          <div>
            <label className="block text-sm font-medium text-white/60 mb-3">
              Pipeline Phase
            </label>
            <div className="grid grid-cols-3 gap-3">
              {[
                { value: 1, label: "Phase 1", desc: "Search + Triage + Read" },
                { value: 2, label: "Phase 2", desc: "+ Critique + Gap Detection" },
                { value: 3, label: "Phase 3", desc: "+ Ideas + Experiments + Report" },
              ].map((p) => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setPhase(p.value)}
                  className={`glass-subtle p-4 text-left transition-all cursor-pointer ${
                    phase === p.value
                      ? "border-[var(--accent-blue)] bg-white/[0.06]"
                      : "hover:bg-white/[0.03]"
                  }`}
                  style={phase === p.value ? { borderColor: "var(--accent-blue)", borderWidth: 1 } : {}}
                >
                  <span className={`text-sm font-semibold ${
                    phase === p.value ? "text-[var(--accent-blue)]" : "text-white/70"
                  }`}>
                    {p.label}
                  </span>
                  <p className="text-xs text-white/35 mt-1">{p.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Max papers */}
          <div>
            <label className="block text-sm font-medium text-white/60 mb-2">
              Max Papers to Deep-Read
            </label>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={5}
                max={50}
                value={maxPapers}
                onChange={(e) => setMaxPapers(Number(e.target.value))}
                className="flex-1 accent-[var(--accent-blue)]"
              />
              <span className="glass-subtle px-3 py-1 text-sm font-mono text-white/70 min-w-[3rem] text-center">
                {maxPapers}
              </span>
            </div>
          </div>

          {/* User background */}
          <div>
            <label className="block text-sm font-medium text-white/60 mb-2">
              Your Background <span className="text-white/25">(optional)</span>
            </label>
            <input
              className="glass-input"
              placeholder="e.g., Photonics researcher with 5 years in OPA design"
              value={background}
              onChange={(e) => setBackground(e.target.value)}
            />
          </div>

          {/* Error */}
          {error && (
            <div className="glass-subtle p-4 border-[var(--accent-rose)]" style={{ borderColor: "var(--accent-rose)" }}>
              <p className="text-sm text-[var(--accent-rose)]">{error}</p>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className={`glass-btn glass-btn-primary w-full py-3 text-base font-semibold ${
              loading ? "opacity-50 cursor-wait" : ""
            } ${!question.trim() ? "opacity-30 cursor-not-allowed" : ""}`}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="30 70" />
                </svg>
                Starting Pipeline...
              </span>
            ) : (
              "Start Research Pipeline"
            )}
          </button>
        </form>
      </GlassCard>

      {/* Info card */}
      <GlassCard hover={false} className="text-sm text-white/40 space-y-2">
        <p className="font-medium text-white/60">How it works:</p>
        <ol className="list-decimal list-inside space-y-1">
          <li>AI plans search queries from your research question</li>
          <li>Searches Semantic Scholar, arXiv, & your Zotero library for papers</li>
          <li>Triages papers with Gemini 3.1 Pro for relevance</li>
          <li>Deep-reads top papers with Claude Opus 4.6</li>
          <li>Detects research gaps using 4 mechanisms</li>
          <li>Generates novel research ideas and experiment plans</li>
          <li>Produces a comprehensive research report</li>
          <li>Exports results to your Zotero library (if configured)</li>
        </ol>
      </GlassCard>
    </div>
  );
}
