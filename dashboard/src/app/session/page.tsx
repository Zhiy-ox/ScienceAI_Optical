"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import GlassCard, { StatCard, StatusBadge } from "@/components/GlassCard";
import { api, type ResearchResult, type PipelineProgress, type StepProgress } from "@/lib/api";

// All 10 pipeline steps in order
const ALL_STEPS = [
  { number: 1, name: "Query Planning" },
  { number: 2, name: "Paper Search" },
  { number: 3, name: "Paper Triage" },
  { number: 4, name: "Deep Reading" },
  { number: 5, name: "Critique" },
  { number: 6, name: "Gap Detection" },
  { number: 7, name: "Gap Verification" },
  { number: 8, name: "Idea Generation" },
  { number: 9, name: "Experiment Planning" },
  { number: 10, name: "Report Generation" },
];

function fmtDuration(secs: number): string {
  if (secs < 60) return `${secs.toFixed(0)}s`;
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
}

function StepIcon({ status }: { status: string }) {
  if (status === "done") {
    return (
      <span className="w-6 h-6 rounded-full flex items-center justify-center bg-emerald-500/20 text-emerald-400 shrink-0">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
      </span>
    );
  }
  if (status === "running") {
    return (
      <span className="w-6 h-6 rounded-full flex items-center justify-center bg-blue-500/20 text-blue-400 shrink-0">
        <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="30 70" />
        </svg>
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="w-6 h-6 rounded-full flex items-center justify-center bg-rose-500/20 text-rose-400 shrink-0">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </span>
    );
  }
  if (status === "skipped") {
    return (
      <span className="w-6 h-6 rounded-full flex items-center justify-center bg-white/5 text-white/25 shrink-0">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14" />
        </svg>
      </span>
    );
  }
  // pending
  return (
    <span className="w-6 h-6 rounded-full flex items-center justify-center border border-white/10 text-white/20 shrink-0 text-xs font-mono" />
  );
}

function PipelineProgressPanel({ progress, pipelineStatus }: {
  progress: PipelineProgress | null;
  pipelineStatus?: string;
}) {
  const stepMap = new Map<number, StepProgress>(
    (progress?.steps ?? []).map((s) => [s.step_number, s])
  );

  const currentNum = progress?.current_step_number ?? null;

  return (
    <GlassCard hover={false}>
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-base font-semibold text-white/80">Pipeline Progress</h3>
        {progress?.current_step && (
          <span className="text-xs text-blue-400 font-medium">
            {progress.current_step}
            {progress.elapsed_seconds != null && (
              <span className="text-white/30 ml-1">· {fmtDuration(progress.elapsed_seconds)}</span>
            )}
          </span>
        )}
        {pipelineStatus === "completed" && !progress?.current_step && (
          <span className="text-xs text-emerald-400 font-medium">Complete</span>
        )}
        {pipelineStatus === "failed" && (
          <span className="text-xs text-rose-400 font-medium">Failed</span>
        )}
      </div>

      <div className="space-y-1">
        {ALL_STEPS.map((def, idx) => {
          const record = stepMap.get(def.number);
          const status = record?.status ?? (
            currentNum != null && def.number < currentNum ? "done" : "pending"
          );
          const isActive = status === "running";

          return (
            <div key={def.number} className="relative">
              {/* connector line */}
              {idx < ALL_STEPS.length - 1 && (
                <span
                  className={`absolute left-[11px] top-[28px] w-px h-4 ${
                    status === "done" ? "bg-emerald-500/30" : "bg-white/8"
                  }`}
                />
              )}

              <div className={`flex items-center gap-3 px-2 py-1.5 rounded-lg transition-all ${
                isActive ? "bg-blue-500/8" : ""
              }`}>
                <StepIcon status={status} />

                <span className={`text-sm flex-1 ${
                  status === "done"     ? "text-white/70" :
                  status === "running"  ? "text-white/90 font-medium" :
                  status === "failed"   ? "text-rose-400" :
                  status === "skipped"  ? "text-white/25 line-through" :
                                          "text-white/30"
                }`}>
                  {def.name}
                </span>

                <span className="text-xs font-mono text-right shrink-0">
                  {status === "done" && record && (
                    <span className="text-white/30">{fmtDuration(record.duration_seconds)}</span>
                  )}
                  {status === "running" && progress?.elapsed_seconds != null && (
                    <span className="text-blue-400/70">{fmtDuration(progress.elapsed_seconds)}</span>
                  )}
                  {status === "failed" && record?.error && (
                    <span className="text-rose-400/70" title={record.error}>error</span>
                  )}
                </span>
              </div>

              {status === "failed" && record?.error && (
                <p className="ml-9 text-xs text-rose-400/60 mt-0.5 mb-1 leading-relaxed">
                  {record.error.slice(0, 120)}{record.error.length > 120 ? "…" : ""}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
}

function SessionContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("id") || "";
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [progress, setProgress] = useState<PipelineProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("overview");

  // Poll for results
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
            if (err.message?.includes("202")) {
              setError("");
            } else {
              setError(err.message || "Failed to load session");
              setLoading(false);
            }
          }
        });
    };

    fetchResults();
    const interval = setInterval(() => {
      if (result?.status === "completed" || result?.status === "failed") return;
      fetchResults();
    }, 5000);

    return () => { cancelled = true; clearInterval(interval); };
  }, [sessionId, result?.status]);

  // Poll for pipeline progress while running
  useEffect(() => {
    if (!sessionId) return;
    if (result?.status === "completed" || result?.status === "failed") return;

    let cancelled = false;
    const fetchProgress = () => {
      api.getProgress(sessionId)
        .then((p) => { if (!cancelled) setProgress(p); })
        .catch(() => {});
    };

    fetchProgress();
    const interval = setInterval(fetchProgress, 2000);
    return () => { cancelled = true; clearInterval(interval); };
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

  // Show progress while pipeline is running
  if (loading && !result) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Link href="/" className="text-xs text-white/30 hover:text-white/50 transition-colors">
              ← Dashboard
            </Link>
            <h2 className="text-2xl font-bold text-white/90 mt-1">Research Pipeline</h2>
            <p className="text-sm text-white/40 font-mono mt-1">{sessionId}</p>
          </div>
          <span className="glass-badge badge-running">running</span>
        </div>

        <PipelineProgressPanel progress={progress} pipelineStatus="running" />

        {!error && (
          <p className="text-center text-white/25 text-xs">Auto-refreshing every 2s</p>
        )}
        {error && (
          <GlassCard>
            <p className="text-[var(--accent-rose)] text-sm">{error}</p>
          </GlassCard>
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
    { id: "papers", label: `Papers (${result.papers_found ?? 0})` },
    { id: "gaps", label: `Gaps (${result.gaps?.length ?? 0})` },
    { id: "ideas", label: `Ideas (${result.ideas?.length ?? 0})` },
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
        <StatCard label="Papers Found" value={result.papers_found ?? 0} />
        <StatCard label="Knowledge Objects" value={result.knowledge_objects?.length ?? 0} variant="purple" />
        <StatCard label="Gaps Found" value={result.gaps?.length ?? 0} />
        <StatCard label="Verified Gaps" value={result.verified_gaps?.length ?? 0} variant="purple" />
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
          {/* Pipeline step history */}
          {progress && progress.steps.length > 0 && (
            <PipelineProgressPanel progress={progress} pipelineStatus={result.status} />
          )}

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
          {(result.gaps ?? []).map((gap, i) => {
            const g = gap as Record<string, unknown>;
            const verified = (result.verified_gaps ?? []).some(
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
          {(result.gaps?.length ?? 0) === 0 && (
            <GlassCard hover={false}>
              <p className="text-white/40 text-sm">No gaps detected.</p>
            </GlassCard>
          )}
        </div>
      )}

      {activeTab === "ideas" && (
        <div className="space-y-3">
          {(result.ideas ?? []).map((idea, i) => {
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
                {result.experiment_plans?.[i] && (
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
          {(result.ideas?.length ?? 0) === 0 && (
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
