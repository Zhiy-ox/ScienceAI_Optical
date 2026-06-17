"use client";

import { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import GlassCard, { StatCard, StatusBadge } from "@/components/GlassCard";
import PipelineProgress, { PIPELINE_STAGES } from "@/components/PipelineProgress";
import ApprovalCard, { type InterruptPayload } from "@/components/ApprovalCard";
import { api, type ResearchResult, type StreamEvent, type TraceResponse } from "@/lib/api";

const STAGE_INDEX: Record<string, number> = Object.fromEntries(
  PIPELINE_STAGES.map((s, i) => [s.key, i])
);

function SessionContent() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("id") || "";
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("overview");

  // Live streaming progress
  const [liveStage, setLiveStage] = useState<string | null>(null);
  const [liveMsg, setLiveMsg] = useState<string | null>(null);
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set());
  const [streaming, setStreaming] = useState(false);

  // Per-node execution trace (lazy-loaded on the Trace tab)
  const [trace, setTrace] = useState<TraceResponse | null>(null);

  // Human-in-the-loop gate
  const [interrupt, setInterrupt] = useState<InterruptPayload | null>(null);
  const [resuming, setResuming] = useState(false);

  // Refs mirror the latest values for the polling interval — reading the state
  // variables directly from the interval callback would capture the values
  // from the first render and poll forever after completion.
  const resultRef = useRef<ResearchResult | null>(null);
  const streamingRef = useRef(false);
  resultRef.current = result;
  streamingRef.current = streaming;

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

    // Try live SSE streaming first; falls back to polling on done/error.
    const markStage = (stage: string) => {
      const idx = STAGE_INDEX[stage];
      if (idx === undefined) return;
      setLiveStage(stage);
      setCompletedStages((prev) => {
        const next = new Set(prev);
        PIPELINE_STAGES.forEach((s, i) => {
          if (i < idx) next.add(s.key);
        });
        return next;
      });
    };

    const onEvent = (ev: StreamEvent) => {
      if (cancelled) return;
      if (ev.event === "progress" && ev.stage) {
        setStreaming(true);
        if (ev.stage !== "start" && ev.stage !== "resume") markStage(ev.stage);
        if (ev.msg) setLiveMsg(ev.msg);
      } else if (ev.event === "interrupt") {
        // Pipeline paused at a HITL gate — show the approval card.
        setStreaming(false);
        setLiveMsg(null);
        setInterrupt({
          type: ev.type,
          message: ev.message ?? ev.msg,
          plan: ev.plan,
          verified_gaps: ev.verified_gaps,
        });
      } else if (ev.event === "done" || ev.event === "error") {
        setStreaming(false);
        setLiveStage(null);
        if (ev.status === "awaiting_input") {
          // Reload/restart while paused at a gate: the stream won't replay the
          // interrupt event, so restore the approval card from /status.
          api.getStatus(sessionId)
            .then((s) => {
              if (!cancelled && s.interrupt) {
                setLoading(false);
                setInterrupt(s.interrupt as InterruptPayload);
              }
            })
            .catch(() => fetchResults());
        } else {
          fetchResults();
        }
      }
    };

    const unsubscribe = api.streamSession(sessionId, onEvent, () => {
      // SSE not available — fall back to polling.
      if (!cancelled) fetchResults();
    });

    fetchResults();

    // Auto-refresh polling fallback when not streaming; stops once terminal.
    const interval = setInterval(() => {
      const status = resultRef.current?.status;
      if (status === "completed" || status === "failed") return;
      if (!streamingRef.current) fetchResults();
    }, 5000);

    return () => {
      cancelled = true;
      clearInterval(interval);
      unsubscribe();
    };
  }, [sessionId]);

  // Lazy-load the per-node trace when its tab opens (refresh on result change).
  useEffect(() => {
    if (activeTab !== "trace" || !sessionId) return;
    api.getTrace(sessionId).then(setTrace).catch(() => setTrace(null));
  }, [activeTab, sessionId, result?.status]);

  const handleDecision = async (action: "approve" | "reject") => {
    setResuming(true);
    let gotNewInterrupt = false;

    const advance = (stage: string) => {
      const idx = STAGE_INDEX[stage];
      if (idx === undefined) return;
      setLiveStage(stage);
      setCompletedStages((prev) => {
        const next = new Set(prev);
        PIPELINE_STAGES.forEach((s, i) => {
          if (i < idx) next.add(s.key);
        });
        return next;
      });
    };

    try {
      await api.resumeSession(sessionId, { action }, (ev) => {
        if (ev.event === "progress" && ev.stage) {
          setStreaming(true);
          if (ev.stage !== "start" && ev.stage !== "resume") advance(ev.stage);
          if (ev.msg) setLiveMsg(ev.msg);
        } else if (ev.event === "interrupt") {
          gotNewInterrupt = true;
          setStreaming(false);
          setInterrupt({
            type: ev.type,
            message: ev.message ?? ev.msg,
            plan: ev.plan,
            verified_gaps: ev.verified_gaps,
          });
        } else if (ev.event === "done" || ev.event === "error") {
          setStreaming(false);
          setLiveStage(null);
        }
      });
    } catch {
      /* fall back to polling */
    } finally {
      setResuming(false);
      if (!gotNewInterrupt) {
        setInterrupt(null);
        api.getResults(sessionId).then(setResult).catch(() => {});
      }
    }
  };

  // HITL gate pending — focus the approval card.
  if (interrupt) {
    return (
      <div className="space-y-6">
        <div>
          <Link href="/" className="text-xs text-white/30 hover:text-white/50 transition-colors">
            ← Dashboard
          </Link>
          <h2 className="text-2xl font-bold text-white/90 mt-1">Approval Required</h2>
          <p className="text-sm text-white/40 font-mono mt-1">{sessionId}</p>
        </div>
        <PipelineProgress
          activeStage={liveStage}
          completedStages={completedStages}
          message={liveMsg}
        />
        <ApprovalCard payload={interrupt} onDecision={handleDecision} busy={resuming} />
      </div>
    );
  }

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
        {(streaming || liveStage) && (
          <PipelineProgress
            activeStage={liveStage}
            completedStages={completedStages}
            message={liveMsg}
          />
        )}
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="shimmer h-24" />)}
        </div>
        <div className="shimmer h-64" />
        {!error && (
          <div className="text-center">
            <p className="text-white/40 text-sm">
              {streaming
                ? "Pipeline is running — live progress above"
                : "Pipeline is running... auto-refreshing every 5s"}
            </p>
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
    { id: "papers", label: `Papers (${result.papers_found ?? 0})` },
    { id: "gaps", label: `Gaps (${result.gaps?.length ?? 0})` },
    { id: "ideas", label: `Ideas (${result.ideas?.length ?? 0})` },
    { id: "report", label: "Report" },
    { id: "trace", label: "Trace" },
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

      {/* Live pipeline progress (visible while streaming) */}
      {streaming && (
        <PipelineProgress
          activeStage={liveStage}
          completedStages={completedStages}
          message={liveMsg}
        />
      )}

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
            // Canonical gap_id is stamped on both gaps and verification
            // results; title equality is a fallback for older sessions.
            const verified = (result.verified_gaps ?? []).some((vg) => {
              const v = vg as Record<string, unknown>;
              return g.gap_id ? v.gap_id === g.gap_id : v.title === g.title;
            });
            return (
              <GlassCard key={i}>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      {typeof g.gap_id === "string" && (
                        <span className="text-[10px] font-mono text-[var(--accent-rose)]">{g.gap_id}</span>
                      )}
                      <p className="text-sm font-medium text-white/80">{g.title as string}</p>
                    </div>
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
            // Match the experiment plan by its stamped idea_id; positional
            // fallback covers older sessions without canonical IDs. Index
            // pairing alone mislinks when a plan failed mid-list.
            const plans = (result.experiment_plans ?? []) as Record<string, unknown>[];
            const plan = d.idea_id
              ? plans.find((p) => p.idea_id === d.idea_id)
              : plans[i];
            const strategy = (d.generation_strategy ?? d.strategy) as string | undefined;
            const expPlan = (plan?.experiment_plan ?? {}) as Record<string, unknown>;
            const phase1 = expPlan.phase_1_proof_of_concept as Record<string, unknown> | undefined;
            const phase2 = expPlan.phase_2_full_evaluation as Record<string, unknown> | undefined;
            const risks = (expPlan.risks as unknown[] | undefined)?.length ?? 0;
            return (
              <GlassCard key={i}>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {typeof d.idea_id === "string" && (
                        <span className="text-[10px] font-mono text-[var(--accent-purple)]">{d.idea_id}</span>
                      )}
                      <p className="text-sm font-medium text-white/80">{d.title as string}</p>
                    </div>
                    {strategy && (
                      <p className="text-xs text-white/35 mt-1">
                        Strategy: {strategy.replace(/_/g, " ")}
                      </p>
                    )}
                    {typeof d.description === "string" && (
                      <p className="text-xs text-white/50 mt-2 leading-relaxed line-clamp-3">
                        {d.description as string}
                      </p>
                    )}
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
                {plan && (phase1 || phase2 || risks > 0) && (
                  <div className="mt-4 pt-3 border-t border-white/5 space-y-2">
                    <p className="text-xs text-white/40 uppercase tracking-wider">Experiment Plan</p>
                    {phase1?.objective != null && (
                      <p className="text-xs text-white/55">
                        <span className="text-[var(--accent-teal)]">Phase 1:</span>{" "}
                        {phase1.objective as string}
                      </p>
                    )}
                    {phase2?.datasets != null && (
                      <p className="text-xs text-white/45">
                        <span className="text-[var(--accent-blue)]">Phase 2:</span>{" "}
                        {(phase2.datasets as string[]).join(", ")}
                      </p>
                    )}
                    {risks > 0 && (
                      <p className="text-[10px] text-white/30">{risks} risk(s) identified</p>
                    )}
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

      {activeTab === "trace" && (
        <GlassCard hover={false}>
          {trace && trace.node_count > 0 ? (
            <div className="space-y-6">
              <div className="flex items-baseline justify-between">
                <h3 className="text-base font-semibold text-white/80">Per-Node Execution Trace</h3>
                <span className="text-xs font-mono text-white/40">
                  {trace.node_count} node runs · {trace.total_duration_s.toFixed(2)}s total
                </span>
              </div>
              <div className="space-y-2">
                {trace.by_node.map((agg) => {
                  const pct = trace.total_duration_s > 0
                    ? (agg.total_s / trace.total_duration_s) * 100
                    : 0;
                  return (
                    <div key={agg.node}>
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-white/60 font-mono">
                          {agg.node}
                          {agg.calls > 1 && (
                            <span className="text-white/30"> ×{agg.calls}</span>
                          )}
                        </span>
                        <span className="text-white/50 font-mono">{agg.total_s.toFixed(2)}s</span>
                      </div>
                      <div className="glass-progress">
                        <div className="glass-progress-fill" style={{ width: `${Math.max(pct, 1)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="text-[10px] text-white/25">
                Durations come from the graph&apos;s observability layer; parallel fan-out nodes
                (deep_read_one, critique_one) overlap in wall-clock time.
              </p>
            </div>
          ) : (
            <p className="text-white/40 text-sm">
              No trace recorded yet. Node timings appear here once the pipeline has run.
            </p>
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
