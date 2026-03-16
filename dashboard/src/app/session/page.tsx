"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import GlassCard, { StatCard, StatusBadge } from "@/components/GlassCard";
import { api, type ResearchResult } from "@/lib/api";

/** Demo data for offline mode. */
const DEMO_RESULT: ResearchResult = {
  session_id: "demo-001",
  status: "completed",
  plan: {
    decomposed_questions: [
      "What are the current silicon photonic OPA architectures?",
      "How do OPA beam steering mechanisms compare?",
      "What are the scaling limitations of current OPAs?",
    ],
    search_queries: [
      { keywords: ["optical phased array", "silicon photonics", "beam steering"], source: "semantic_scholar" },
      { keywords: ["OPA", "LiDAR", "integrated photonics"], source: "arxiv" },
    ],
  },
  papers_found: 47,
  triage_results: [
    { paper_id: "p1", title: "Large-Scale Silicon Photonic OPA", relevance_score: 0.95, priority: "must_read" },
    { paper_id: "p2", title: "Beam Steering with Liquid Crystal OPA", relevance_score: 0.88, priority: "must_read" },
    { paper_id: "p3", title: "Thermal Tuning in Integrated Photonics", relevance_score: 0.72, priority: "worth_reading" },
  ],
  knowledge_objects: [
    { paper_id: "p1", title: "Large-Scale Silicon Photonic OPA", method: { core_idea: "Cascaded phase shifter array" } },
    { paper_id: "p2", title: "Beam Steering with Liquid Crystal OPA", method: { core_idea: "LC-based phase modulation" } },
  ],
  critiques: [
    { paper_id: "p1", assumption_issues: ["Assumes uniform waveguide loss"], experimental_weaknesses: ["Limited to 1D steering"] },
  ],
  gaps: [
    { gap_type: "method_gap", title: "No hybrid LC-silicon OPA architecture explored", confidence: 0.82 },
    { gap_type: "evaluation_blindspot", title: "Power consumption not benchmarked across architectures", confidence: 0.76 },
  ],
  verified_gaps: [
    { gap_type: "method_gap", title: "No hybrid LC-silicon OPA architecture explored", status: "verified_gap" },
  ],
  ideas: [
    { title: "Hybrid LC-Silicon Cascaded OPA", strategy: "method_transfer", feasibility_score: 0.78 },
  ],
  experiment_plans: [
    { idea_title: "Hybrid LC-Silicon Cascaded OPA", feasibility_score: 0.78, phases: ["Simulation", "Fabrication", "Characterization"] },
  ],
  report: {
    title: "Research Report: Silicon-Based Optical Phased Arrays for LiDAR",
    sections: [
      { heading: "Executive Summary", content: "This report surveys the state of silicon-based OPA technology..." },
      { heading: "Literature Review", content: "We analyzed 47 papers spanning 2020-2025..." },
      { heading: "Research Gaps", content: "Two primary gaps were identified..." },
      { heading: "Proposed Ideas", content: "We propose a hybrid LC-silicon cascaded OPA..." },
    ],
  },
  cost_summary: { session_id: "demo-001", total_usd: 2.34, by_model: { "claude-opus-4-6": 1.52, "gpt-5.4": 0.62, "gemini/gemini-3.1-pro": 0.20 }, call_count: 18 },
};

function SessionContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("id") || "";
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => {
    if (!sessionId) return;

    api.getResults(sessionId)
      .then(setResult)
      .catch(() => {
        // Use demo data in offline mode
        if (sessionId.startsWith("demo")) {
          setResult({ ...DEMO_RESULT, session_id: sessionId });
        }
      })
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (!sessionId) {
    return (
      <GlassCard>
        <p className="text-white/50">No session ID provided.</p>
        <Link href="/" className="text-[var(--accent-blue)] text-sm mt-2 inline-block">
          ← Back to Dashboard
        </Link>
      </GlassCard>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="shimmer h-8 w-64" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="shimmer h-24" />)}
        </div>
        <div className="shimmer h-64" />
      </div>
    );
  }

  if (!result) {
    return (
      <GlassCard>
        <p className="text-white/50">Session not found or still running.</p>
        <Link href="/" className="text-[var(--accent-blue)] text-sm mt-2 inline-block">
          ← Back to Dashboard
        </Link>
      </GlassCard>
    );
  }

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "papers", label: `Papers (${result.papers_found})` },
    { id: "gaps", label: `Gaps (${result.gaps.length})` },
    { id: "ideas", label: `Ideas (${result.ideas.length})` },
    { id: "report", label: "Report" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <Link href="/" className="text-xs text-white/30 hover:text-white/50 transition-colors">
            ← Dashboard
          </Link>
          <h2 className="text-2xl font-bold text-white/90 mt-1">Session Results</h2>
          <p className="text-sm text-white/40 font-mono mt-1">{sessionId}</p>
        </div>
        <StatusBadge status={result.status} />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Papers Found" value={result.papers_found} />
        <StatCard label="Knowledge Objects" value={result.knowledge_objects.length} variant="purple" />
        <StatCard label="Gaps Found" value={result.gaps.length} />
        <StatCard label="Verified Gaps" value={result.verified_gaps.length} variant="purple" />
        <StatCard
          label="Total Cost"
          value={`$${result.cost_summary?.total_usd.toFixed(2) || "0.00"}`}
          variant="amber"
          subtitle={`${result.cost_summary?.call_count || 0} API calls`}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 glass-subtle p-1 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm rounded-xl transition-all ${
              activeTab === tab.id
                ? "bg-white/10 text-white font-medium"
                : "text-white/40 hover:text-white/60 hover:bg-white/[0.03]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "overview" && (
        <div className="space-y-4">
          {/* Plan */}
          {result.plan && (
            <GlassCard hover={false}>
              <h3 className="text-base font-semibold text-white/80 mb-4">Research Plan</h3>
              {Array.isArray((result.plan as Record<string, unknown>).decomposed_questions) && (
                <div className="mb-4">
                  <p className="text-xs text-white/40 uppercase tracking-wider mb-2">Decomposed Questions</p>
                  <ul className="space-y-2">
                    {((result.plan as Record<string, unknown>).decomposed_questions as string[]).map((q, i) => (
                      <li key={i} className="flex gap-3 text-sm text-white/60">
                        <span className="text-[var(--accent-blue)] font-mono text-xs mt-0.5">{i + 1}.</span>
                        {q}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Cost by model */}
              {result.cost_summary?.by_model && (
                <div>
                  <p className="text-xs text-white/40 uppercase tracking-wider mb-3">Cost by Model</p>
                  <div className="space-y-2">
                    {Object.entries(result.cost_summary.by_model).map(([model, cost]) => {
                      const total = result.cost_summary!.total_usd || 1;
                      const pct = (cost / total) * 100;
                      return (
                        <div key={model}>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-white/50 font-mono">{model}</span>
                            <span className="text-white/60">${cost.toFixed(4)}</span>
                          </div>
                          <div className="glass-progress">
                            <div className="glass-progress-fill" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </GlassCard>
          )}
        </div>
      )}

      {activeTab === "papers" && (
        <div className="space-y-3">
          {result.triage_results.map((tr, i) => (
            <GlassCard key={i} className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white/80 truncate">
                  {(tr as Record<string, unknown>).title as string}
                </p>
                <p className="text-xs text-white/35 font-mono mt-1">
                  {(tr as Record<string, unknown>).paper_id as string}
                </p>
              </div>
              <div className="flex items-center gap-3 ml-4 shrink-0">
                <span className="text-xs text-white/40">
                  {((tr as Record<string, unknown>).relevance_score as number)?.toFixed(2)}
                </span>
                <span className={`glass-badge ${
                  (tr as Record<string, unknown>).priority === "must_read"
                    ? "badge-completed"
                    : (tr as Record<string, unknown>).priority === "worth_reading"
                      ? "badge-started"
                      : "badge-failed"
                }`}>
                  {(tr as Record<string, unknown>).priority as string}
                </span>
              </div>
            </GlassCard>
          ))}
          {result.triage_results.length === 0 && (
            <GlassCard hover={false}>
              <p className="text-white/40 text-sm">No triage results available.</p>
            </GlassCard>
          )}
        </div>
      )}

      {activeTab === "gaps" && (
        <div className="space-y-3">
          {result.gaps.map((gap, i) => {
            const g = gap as Record<string, unknown>;
            const verified = result.verified_gaps.some(
              (vg) => (vg as Record<string, unknown>).title === g.title
            );
            return (
              <GlassCard key={i}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-white/80">{g.title as string}</p>
                    <p className="text-xs text-white/35 mt-1">{g.gap_type as string}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {typeof g.confidence === "number" && (
                      <span className="text-xs font-mono text-white/40">
                        {((g.confidence as number) * 100).toFixed(0)}%
                      </span>
                    )}
                    <span className={`glass-badge ${verified ? "badge-completed" : "badge-started"}`}>
                      {verified ? "Verified" : "Unverified"}
                    </span>
                  </div>
                </div>
              </GlassCard>
            );
          })}
          {result.gaps.length === 0 && (
            <GlassCard hover={false}>
              <p className="text-white/40 text-sm">No gaps detected.</p>
            </GlassCard>
          )}
        </div>
      )}

      {activeTab === "ideas" && (
        <div className="space-y-3">
          {result.ideas.map((idea, i) => {
            const d = idea as Record<string, unknown>;
            return (
              <GlassCard key={i}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-white/80">{d.title as string}</p>
                    <p className="text-xs text-white/35 mt-1">Strategy: {d.strategy as string}</p>
                  </div>
                  {typeof d.feasibility_score === "number" && (
                    <div className="shrink-0 text-right">
                      <p className="text-xs text-white/35">Feasibility</p>
                      <p className="text-lg font-bold stat-value">
                        {((d.feasibility_score as number) * 100).toFixed(0)}%
                      </p>
                    </div>
                  )}
                </div>
                {/* Experiment plan if available */}
                {result.experiment_plans[i] && (
                  <div className="mt-4 pt-3 border-t border-white/5">
                    <p className="text-xs text-white/40 uppercase tracking-wider mb-2">Experiment Phases</p>
                    <div className="flex gap-2">
                      {((result.experiment_plans[i] as Record<string, unknown>).phases as string[] || []).map((ph, j) => (
                        <span key={j} className="glass-badge badge-started text-[10px]">{ph}</span>
                      ))}
                    </div>
                  </div>
                )}
              </GlassCard>
            );
          })}
          {result.ideas.length === 0 && (
            <GlassCard hover={false}>
              <p className="text-white/40 text-sm">No ideas generated.</p>
            </GlassCard>
          )}
        </div>
      )}

      {activeTab === "report" && (
        <GlassCard hover={false}>
          {result.report ? (
            <div className="space-y-6">
              <h3 className="text-lg font-bold text-white/90">
                {(result.report as Record<string, unknown>).title as string}
              </h3>
              {((result.report as Record<string, unknown>).sections as Array<Record<string, string>> || []).map((section, i) => (
                <div key={i}>
                  <h4 className="text-sm font-semibold text-[var(--accent-blue)] mb-2">
                    {section.heading}
                  </h4>
                  <p className="text-sm text-white/60 leading-relaxed">{section.content}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-white/40 text-sm">No report generated. Run Phase 3 for a full report.</p>
          )}
        </GlassCard>
      )}
    </div>
  );
}

export default function SessionPage() {
  return (
    <Suspense fallback={
      <div className="space-y-6">
        <div className="shimmer h-8 w-64" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="shimmer h-24" />)}
        </div>
      </div>
    }>
      <SessionContent />
    </Suspense>
  );
}
