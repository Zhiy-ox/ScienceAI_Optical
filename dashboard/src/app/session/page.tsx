"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import GlassCard, { StatCard, StatusBadge } from "@/components/GlassCard";
import { api, type ResearchResult } from "@/lib/api";

function SessionContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("id") || "";
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("overview");

  useEffect(() => {
    if (!sessionId) return;

    let cancelled = false;

    const fetchResults = () => {
      api.getResults(sessionId)
        .then((r) => {
          if (!cancelled) {
            setResult(r);
            setLoading(false);
            setError("");
          }
        })
        .catch((err) => {
          if (!cancelled) {
            // Check if still running (202)
            if (err.message?.includes("202")) {
              setError("");
              // Keep loading state, will retry via polling
            } else {
              setError(err.message || "Failed to load session");
              setLoading(false);
            }
          }
        });
    };

    fetchResults();

    // Auto-refresh polling when status is running
    const interval = setInterval(() => {
      if (result?.status === "completed" || result?.status === "failed") return;
      fetchResults();
    }, 5000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sessionId, result?.status]);

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

  if (loading && !result) {
    return (
      <div className="space-y-6">
        <div className="shimmer h-8 w-64" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="shimmer h-24" />)}
        </div>
        <div className="shimmer h-64" />
        {!error && (
          <div className="text-center">
            <p className="text-white/40 text-sm">Pipeline is running... auto-refreshing every 5s</p>
          </div>
        )}
      </div>
    );
  }

  if (error && !result) {
    return (
      <GlassCard>
        <p className="text-[var(--accent-rose)] text-sm">{error}</p>
        <Link href="/" className="text-[var(--accent-blue)] text-sm mt-2 inline-block">
          ← Back to Dashboard
        </Link>
      </GlassCard>
    );
  }

  if (!result) {
    return (
      <GlassCard>
        <p className="text-white/50">Session not found.</p>
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
