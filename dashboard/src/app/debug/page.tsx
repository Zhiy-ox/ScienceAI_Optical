"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import GlassCard, { StatusBadge } from "@/components/GlassCard";
import { api, type SessionListItem, type TraceResponse, type NodeMetric } from "@/lib/api";

// ── helpers ────────────────────────────────────────────────────────────────

const NODE_COLORS: Record<string, string> = {
  plan: "var(--accent-blue)",
  search: "var(--accent-blue)",
  triage: "var(--accent-purple)",
  select_papers: "var(--accent-purple)",
  deep_read_one: "var(--accent-purple)",
  collect_reads: "var(--accent-purple)",
  index: "var(--accent-teal)",
  critique_one: "var(--accent-rose)",
  collect_critiques: "var(--accent-rose)",
  gap_detect: "var(--accent-rose)",
  verify: "var(--accent-teal)",
  idea: "var(--accent-teal)",
  experiment: "var(--accent-amber)",
  report: "var(--accent-amber)",
};

function nodeColor(node: string) {
  return NODE_COLORS[node] ?? "var(--accent-blue)";
}

// ── trace row ──────────────────────────────────────────────────────────────

function TraceRow({ metric, index, maxDuration }: {
  metric: NodeMetric;
  index: number;
  maxDuration: number;
}) {
  const pct = maxDuration > 0 ? (metric.duration_s / maxDuration) * 100 : 0;
  const color = nodeColor(metric.node);

  return (
    <div className="glass-subtle rounded-xl px-5 py-3">
      <div className="flex items-center gap-4">
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
          style={{
            background: `${color}22`,
            color,
            border: `1px solid ${color}44`,
          }}
        >
          {index + 1}
        </span>
        <span className="flex-1 text-sm font-mono text-white/80">{metric.node}</span>
        {metric.status && (
          <span className="text-[10px] font-mono text-white/30">{metric.status}</span>
        )}
        <span className="text-xs font-mono text-white/45 shrink-0 w-16 text-right">
          {metric.duration_s.toFixed(2)}s
        </span>
      </div>
      <div className="glass-progress mt-2">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.max(pct, 1)}%`, background: color }}
        />
      </div>
    </div>
  );
}

// ── trace panel ────────────────────────────────────────────────────────────

function TracePanel({ sessionId }: { sessionId: string }) {
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const poll = () => {
      api.getTrace(sessionId)
        .then((t) => {
          if (!cancelled) {
            setTrace(t);
            setLoading(false);
            setFetchError("");
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setFetchError(err.message || "Failed to fetch trace");
            setLoading(false);
          }
        });
    };

    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sessionId]);

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => <div key={i} className="shimmer h-12 rounded-xl" />)}
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="glass-subtle rounded-xl p-4">
        <p className="text-[var(--accent-rose)] text-sm">{fetchError}</p>
        <p className="text-white/30 text-xs mt-1">
          Sessions started before this server run may have no checkpointed trace.
        </p>
      </div>
    );
  }

  if (!trace || trace.node_count === 0) {
    return (
      <div className="glass-subtle rounded-xl p-6 text-center">
        <p className="text-white/35 text-sm">No node executions recorded yet for this session.</p>
        <p className="text-white/20 text-xs mt-1">The pipeline may not have started.</p>
      </div>
    );
  }

  const maxDuration = Math.max(...trace.trace.map((m) => m.duration_s), 0);
  const slowest = trace.by_node[0];
  const running = trace.status !== "completed" && trace.status !== "failed";

  return (
    <div className="space-y-4">
      {/* summary row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Node Runs", value: String(trace.node_count), color: "var(--accent-blue)" },
          { label: "Total Time", value: `${trace.total_duration_s.toFixed(1)}s`, color: "var(--accent-teal)" },
          { label: "Slowest Node", value: slowest?.node ?? "—", color: "var(--accent-amber)", mono: true },
          { label: "Status", value: trace.status, color: "var(--accent-purple)", mono: true },
        ].map(({ label, value, color, mono }) => (
          <div key={label} className="glass-subtle rounded-xl p-4 text-center">
            <p
              className={`font-bold truncate ${mono ? "text-sm font-mono" : "text-2xl"}`}
              style={{ color }}
              title={value}
            >
              {value}
            </p>
            <p className="text-[10px] text-white/35 uppercase tracking-wider mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* aggregate by node */}
      <div className="glass-subtle rounded-xl p-5">
        <p className="text-[10px] text-white/35 uppercase tracking-wider mb-3">Time by node</p>
        <div className="space-y-3">
          {trace.by_node.map((agg) => {
            const pct = trace.total_duration_s > 0
              ? (agg.total_s / trace.total_duration_s) * 100
              : 0;
            return (
              <div key={agg.node}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-white/60 font-mono">
                    {agg.node}
                    {agg.calls > 1 && <span className="text-white/30"> ×{agg.calls}</span>}
                  </span>
                  <span className="text-white/45 font-mono">
                    {agg.total_s.toFixed(2)}s · {pct.toFixed(0)}%
                  </span>
                </div>
                <div className="glass-progress">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${Math.max(pct, 1)}%`, background: nodeColor(agg.node) }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* execution order */}
      <p className="text-[10px] text-white/35 uppercase tracking-wider px-1">Execution order</p>
      <div className="space-y-2">
        {trace.trace.map((m, i) => (
          <TraceRow key={i} metric={m} index={i} maxDuration={maxDuration} />
        ))}
      </div>

      {running && (
        <p className="text-[10px] text-white/20 text-right">Auto-refreshing every 3s</p>
      )}
    </div>
  );
}

// ── main content ───────────────────────────────────────────────────────────

function DebugContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const selectedId = searchParams.get("id") || "";

  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);

  useEffect(() => {
    api.listSessions()
      .then((s) => setSessions(s))
      .catch(() => {})
      .finally(() => setLoadingSessions(false));
  }, []);

  function selectSession(id: string) {
    router.push(`/debug?id=${id}`);
  }

  return (
    <div className="space-y-6">
      {/* header */}
      <div>
        <h2 className="text-2xl font-bold text-white/90">Pipeline Inspector</h2>
        <p className="text-sm text-white/40 mt-1">
          Per-node execution timing for any research session, straight from the graph&apos;s checkpointed trace.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* session list */}
        <div className="space-y-3">
          <p className="text-xs text-white/35 uppercase tracking-wider px-1">Sessions</p>

          {loadingSessions ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <div key={i} className="shimmer h-16 rounded-xl" />)}
            </div>
          ) : sessions.length === 0 ? (
            <GlassCard hover={false}>
              <p className="text-white/40 text-sm">No sessions yet.</p>
              <Link href="/new" className="text-[var(--accent-blue)] text-xs mt-1 inline-block">
                Start one →
              </Link>
            </GlassCard>
          ) : (
            sessions.map((s) => {
              const active = s.session_id === selectedId;
              const hasFailed = s.status === "failed";
              return (
                <button
                  key={s.session_id}
                  onClick={() => selectSession(s.session_id)}
                  className={`w-full text-left glass-subtle rounded-xl px-4 py-3 transition-all hover:bg-white/[0.06] ${
                    active ? "border border-white/15 bg-white/[0.06]" : "border border-transparent"
                  } ${hasFailed ? "border-[var(--accent-rose)]/20" : ""}`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <StatusBadge status={s.status} />
                    <span className="text-[10px] font-mono text-white/25">
                      ${s.cost_so_far.toFixed(4)}
                    </span>
                  </div>
                  <p className="text-xs text-white/60 line-clamp-2 leading-relaxed">
                    {s.question}
                  </p>
                  <p className="text-[10px] text-white/25 font-mono mt-1 truncate">
                    {s.session_id}
                  </p>
                </button>
              );
            })
          )}
        </div>

        {/* trace detail */}
        <div className="md:col-span-2">
          {selectedId ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <p className="text-xs text-white/35 uppercase tracking-wider">
                  Node trace
                </p>
                <p className="text-xs font-mono text-white/25 truncate">{selectedId}</p>
              </div>
              <TracePanel sessionId={selectedId} />
            </div>
          ) : (
            <GlassCard hover={false} className="h-full flex items-center justify-center min-h-[200px]">
              <div className="text-center">
                <svg className="w-10 h-10 text-white/15 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-white/30 text-sm">Select a session to inspect its node timings.</p>
              </div>
            </GlassCard>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DebugPage() {
  return (
    <Suspense fallback={
      <div className="space-y-6">
        <div className="shimmer h-8 w-48" />
        <div className="grid grid-cols-3 gap-6">
          <div className="space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="shimmer h-16 rounded-xl" />)}
          </div>
          <div className="col-span-2 shimmer h-64 rounded-xl" />
        </div>
      </div>
    }>
      <DebugContent />
    </Suspense>
  );
}
