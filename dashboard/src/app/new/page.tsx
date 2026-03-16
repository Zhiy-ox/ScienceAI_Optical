"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import GlassCard from "@/components/GlassCard";
import { api } from "@/lib/api";

export default function NewResearchPage() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [maxPapers, setMaxPapers] = useState(15);
  const [phase, setPhase] = useState(3);
  const [background, setBackground] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
          <li>Searches Semantic Scholar & arXiv for relevant papers</li>
          <li>Triages papers with Gemini 3.1 Pro for relevance</li>
          <li>Deep-reads top papers with Claude Opus 4.6</li>
          <li>Detects research gaps using 4 mechanisms</li>
          <li>Generates novel research ideas and experiment plans</li>
          <li>Produces a comprehensive research report</li>
        </ol>
      </GlassCard>
    </div>
  );
}
