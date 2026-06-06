"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import GlassCard, { StatusBadge } from "@/components/GlassCard";
import { api, type SessionListItem, type PipelineProgress, type StepProgress } from "@/lib/api";

// ── helpers ────────────────────────────────────────────────────────────────

function fmt(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString();
}

function stepStatusColor(status: StepProgress["status"]) {
  return status === "done"
    ? "var(--accent-teal)"
    : status === "running"
    ? "var(--accent-blue)"
    : status === "skipped"
    ? "var(--accent-amber)"
    : "var(--accent-rose)"; // failed
}

function stepStatusBadgeClass(status: StepProgress["status"]) {
  return status === "done"
    ? "badge-completed"
    : status === "running"
    ? "badge-running"
    : status === "skipped"
    ? "badge-started"
    : "badge-failed";
}

// ── step timeline ──────────────────────────────────────────────────────────

function StepRow({ step }: { step: StepProgress }) {
  const [expanded, setExpanded] = useState(step.status === "failed");
  const hasError = !!step.error;

  return (
    <div
      className={`glass-subtle rounded-xl overflow-hidden transition-all ${
        hasError ? "border border-[var(--accent-rose)]/20" : ""
      }`}
    >
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-4 px-5 py-3 text-left hover:bg-white/[0.03] transition-colors"
      >
        {/* step number */}
        <span
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
          style={{
            background: `${stepStatusColor(step.status)}22`,
            color: stepStatusColor(step.status),
            border: `1px solid ${stepStatusColor(step.status)}44`,
          }}
        >
          {step.step_number}
        </span>

        {/* name */}
        <span className="flex-1 text-sm font-medium text-white/80">
          {step.step_name}
        </span>

        {/* duration */}
        <span className="text-xs font-mono text-white/35 shrink-0">
          {step.duration_seconds}s
        </span>

        {/* badge */}
        <span className={`glass-badge ${stepStatusBadgeClass(step.status)} shrink-0`}>
          {step.status}
        </span>

        {/* expand arrow */}
        <svg
          className={`w-4 h-4 text-white/30 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="px-5 pb-4 space-y-3 border-t border-white/5">
          {/* timestamps */}
          <div className="flex gap-6 pt-3">
            <div>
              <p className="text-[10px] text-white/30 uppercase tracking-wider mb-1">Started</p>
              <p className="text-xs font-mono text-white/50">{fmt(step.started_at)}</p>
            </div>
            {step.finished_at && (
              <div>
                <p className="text-[10px] text-white/30 uppercase tracking-wider mb-1">Finished</p>
                <p className="text-xs font-mono text-white/50">{fmt(step.finished_at)}</p>
              </div>
            )}
          </div>

          {/* error */}
          {step.error && (
            <div className="rounded-lg p-3" style={{ background: "rgba(255,128,171,0.06)", border: "1px solid rgba(255,128,171,0.15)" }}>
              <p className="text-[10px] text-[var(--accent-rose)] uppercase tracking-wider mb-1 font-medium">
                Error
              </p>
              <pre className="text-xs font-mono text-[var(--accent-rose)]/80 whitespace-pre-wrap break-all leading-relaxed">
                {step.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── progress panel ─────────────────────────────────────────────────────────

function ProgressPanel({ sessionId }: { sessionId: string }) {
  const [progress, setProgress] = useState<PipelineProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const poll = () => {
      api.getProgress(sessionId)
        .then((p) => {
          if (!cancelled) {
            setProgress(p);
            setLoading(false);
            setFetchError("");
          }
        })
        .catch((err) => {
          if (!cancelled) {
            setFetchError(err.message || "Failed to fetch progress");
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
      </div>
    );
  }

  if (!progress || progress.steps.length === 0) {
    return (
      <div className="glass-subtle rounded-xl p-6 text-center">
        <p className="text-white/35 text-sm">No steps recorded yet for this session.</p>
        <p className="text-white/20 text-xs mt-1">The pipeline may not have started.</p>
      </div>
    );
  }

  const failed = progress.steps.filter((s) => s.status === "failed");
  const done = progress.steps.filter((s) => s.status === "done");
  const skipped = progress.steps.filter((s) => s.status === "skipped");
  const running = progress.steps.filter((s) => s.status === "running");

  return (
    <div className="space-y-4">
      {/* summary row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Done", count: done.length, color: "var(--accent-teal)" },
          { label: "Running", count: running.length, color: "var(--accent-blue)" },
          { label: "Skipped", count: skipped.length, color: "var(--accent-amber)" },
          { label: "Failed", count: failed.length, color: "var(--accent-rose)" },
        ].map(({ label, count, color }) => (
          <div key={label} className="glass-subtle rounded-xl p-4 text-center">
            <p className="text-2xl font-bold" style={{ color }}>{count}</p>
            <p className="text-[10px] text-white/35 uppercase tracking-wider mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* current step banner */}
      {progress.current_step && (
        <div
          className="rounded-xl px-5 py-3 flex items-center gap-3"
          style={{ background: "rgba(79,195,247,0.07)", border: "1px solid rgba(79,195,247,0.2)" }}
        >
          {/* spinner */}
          <svg className="w-4 h-4 text-[var(--accent-blue)] animate-spin shrink-0" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
          </svg>
          <p className="text-sm text-[var(--accent-blue)] font-medium">
            Step {progress.current_step_number}: {progress.current_step}
          </p>
          <span className="ml-auto text-xs font-mono text-white/35">
            {progress.elapsed_seconds}s elapsed
          </span>
        </div>
      )}

      {/* failed steps callout */}
      {failed.length > 0 && (
        <div
          className="rounded-xl px-5 py-3"
          style={{ background: "rgba(255,128,171,0.06)", border: "1px solid rgba(255,128,171,0.2)" }}
        >
          <p className="text-xs text-[var(--accent-rose)] font-medium uppercase tracking-wider mb-1">
            {failed.length} step{failed.length > 1 ? "s" : ""} failed — expand below for details
          </p>
          <p className="text-xs text-white/40">
            {failed.map((s) => `Step ${s.step_number}: ${s.step_name}`).join(" · ")}
          </p>
        </div>
      )}

      {/* step list */}
      <div className="space-y-2">
        {progress.steps.map((step) => (
          <StepRow key={step.step_number} step={step} />
        ))}
      </div>

      <p className="text-[10px] text-white/20 text-right">Auto-refreshing every 3s</p>
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
        <h2 className="text-2xl font-bold text-white/90">Pipeline Debugger</h2>
        <p className="text-sm text-white/40 mt-1">
          Inspect step-by-step progress and error details for any research session.
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

        {/* progress detail */}
        <div className="md:col-span-2">
          {selectedId ? (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <p className="text-xs text-white/35 uppercase tracking-wider">
                  Session progress
                </p>
                <p className="text-xs font-mono text-white/25 truncate">{selectedId}</p>
              </div>
              <ProgressPanel sessionId={selectedId} />
            </div>
          ) : (
            <GlassCard hover={false} className="h-full flex items-center justify-center min-h-[200px]">
              <div className="text-center">
                <svg className="w-10 h-10 text-white/15 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-white/30 text-sm">Select a session to inspect its pipeline steps.</p>
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
