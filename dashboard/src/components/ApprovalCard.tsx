"use client";

/** Human-in-the-loop approval card shown when the pipeline pauses at a gate. */

import { useState } from "react";

export interface InterruptPayload {
  type?: string;
  message?: string;
  plan?: Record<string, unknown>;
  verified_gaps?: Record<string, unknown>[];
}

interface Props {
  payload: InterruptPayload;
  onDecision: (action: "approve" | "reject") => void;
  busy?: boolean;
}

export default function ApprovalCard({ payload, onDecision, busy }: Props) {
  const [expanded, setExpanded] = useState(false);

  const isPlan = payload.type === "approve_plan";
  const title = isPlan ? "Approve Research Plan" : "Approve Verified Gaps";

  const preview = isPlan
    ? JSON.stringify(payload.plan ?? {}, null, 2)
    : JSON.stringify(payload.verified_gaps ?? [], null, 2);

  return (
    <div
      className="glass p-6 border border-[var(--accent-amber)]/30"
      style={{ borderRadius: "20px" }}
    >
      <div className="flex items-center gap-3 mb-3">
        <span className="w-2.5 h-2.5 rounded-full bg-[var(--accent-amber)] animate-pulse" />
        <h3 className="text-base font-semibold text-white/90">{title}</h3>
        <span className="glass-badge badge-started text-[10px] ml-auto">
          Awaiting your approval
        </span>
      </div>

      {payload.message && (
        <p className="text-sm text-white/50 mb-4">{payload.message}</p>
      )}

      <button
        onClick={() => setExpanded((v) => !v)}
        className="text-xs text-[var(--accent-blue)] mb-2"
      >
        {expanded ? "Hide details" : "Show details"}
      </button>

      {expanded && (
        <pre className="glass-subtle p-3 text-xs text-white/60 overflow-auto max-h-64 mb-4 rounded-xl">
          {preview}
        </pre>
      )}

      <div className="flex gap-3 mt-2">
        <button
          disabled={busy}
          onClick={() => onDecision("approve")}
          className="px-5 py-2.5 rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-200 text-sm font-medium hover:bg-emerald-500/30 transition-all disabled:opacity-40"
        >
          {busy ? "Resuming…" : "Approve & Continue"}
        </button>
        <button
          disabled={busy}
          onClick={() => onDecision("reject")}
          className="px-5 py-2.5 rounded-xl bg-rose-500/20 border border-rose-500/40 text-rose-200 text-sm font-medium hover:bg-rose-500/30 transition-all disabled:opacity-40"
        >
          Reject & Stop
        </button>
      </div>
    </div>
  );
}
