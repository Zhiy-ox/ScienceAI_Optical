"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import GlassCard, { StatCard, StatusBadge } from "@/components/GlassCard";
import { api, type HealthResponse, type SessionStatus } from "@/lib/api";

/** Demo sessions for when API is not available. */
const DEMO_SESSIONS: SessionStatus[] = [
  { session_id: "demo-001", status: "completed", cost_so_far: 2.34 },
  { session_id: "demo-002", status: "running", cost_so_far: 0.89 },
  { session_id: "demo-003", status: "completed", cost_so_far: 4.12 },
  { session_id: "demo-004", status: "failed", cost_so_far: 0.45 },
  { session_id: "demo-005", status: "started", cost_so_far: 0.0 },
];

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sessions] = useState<SessionStatus[]>(DEMO_SESSIONS);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    api.health()
      .then((h) => {
        setHealth(h);
        setConnected(true);
      })
      .catch(() => setConnected(false));
  }, []);

  const totalCost = sessions.reduce((s, sess) => s + sess.cost_so_far, 0);
  const completed = sessions.filter((s) => s.status === "completed").length;
  const running = sessions.filter((s) => s.status === "running").length;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white/90">Dashboard</h2>
          <p className="text-sm text-white/40 mt-1">
            Research session overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-[var(--accent-teal)]" : "bg-white/20"
            }`}
            style={connected ? { boxShadow: "0 0 8px var(--accent-teal)" } : {}}
          />
          <span className="text-xs text-white/40 font-mono">
            {connected ? `API v${health?.version}` : "Offline mode"}
          </span>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="Total Sessions" value={sessions.length} />
        <StatCard label="Completed" value={completed} variant="purple" />
        <StatCard label="Running" value={running} />
        <StatCard
          label="Total Cost"
          value={`$${totalCost.toFixed(2)}`}
          variant="amber"
          subtitle="across all sessions"
        />
      </div>

      {/* Sessions table */}
      <GlassCard hover={false} className="overflow-hidden">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white/80">Recent Sessions</h3>
          <Link href="/new" className="glass-btn text-sm">
            + New Research
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/5">
                <th className="text-left text-xs text-white/30 uppercase tracking-wider pb-3 font-medium">
                  Session ID
                </th>
                <th className="text-left text-xs text-white/30 uppercase tracking-wider pb-3 font-medium">
                  Status
                </th>
                <th className="text-right text-xs text-white/30 uppercase tracking-wider pb-3 font-medium">
                  Cost
                </th>
                <th className="text-right text-xs text-white/30 uppercase tracking-wider pb-3 font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((sess) => (
                <tr
                  key={sess.session_id}
                  className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                >
                  <td className="py-4">
                    <span className="font-mono text-sm text-white/70">
                      {sess.session_id.slice(0, 12)}...
                    </span>
                  </td>
                  <td className="py-4">
                    <StatusBadge status={sess.status} />
                  </td>
                  <td className="py-4 text-right">
                    <span className="font-mono text-sm text-white/60">
                      ${sess.cost_so_far.toFixed(4)}
                    </span>
                  </td>
                  <td className="py-4 text-right">
                    <Link
                      href={`/session?id=${sess.session_id}`}
                      className="text-xs text-[var(--accent-blue)] hover:text-[var(--accent-teal)] transition-colors"
                    >
                      View Details →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* Pipeline visualization */}
      <GlassCard hover={false}>
        <h3 className="text-lg font-semibold text-white/80 mb-6">Pipeline Stages</h3>
        <div className="flex items-center gap-3 overflow-x-auto pb-2">
          {[
            { name: "Plan", color: "var(--accent-blue)" },
            { name: "Search", color: "var(--accent-blue)" },
            { name: "Triage", color: "var(--accent-purple)" },
            { name: "Deep Read", color: "var(--accent-purple)" },
            { name: "Critique", color: "var(--accent-rose)" },
            { name: "Gap Detect", color: "var(--accent-rose)" },
            { name: "Verify", color: "var(--accent-teal)" },
            { name: "Ideate", color: "var(--accent-teal)" },
            { name: "Experiment", color: "var(--accent-amber)" },
            { name: "Report", color: "var(--accent-amber)" },
          ].map((stage, i) => (
            <div key={stage.name} className="flex items-center gap-3 shrink-0">
              <div
                className="glass-subtle px-4 py-2 text-xs font-medium whitespace-nowrap"
                style={{ borderColor: stage.color, borderWidth: 1 }}
              >
                <span style={{ color: stage.color }}>{i + 1}.</span>{" "}
                <span className="text-white/70">{stage.name}</span>
              </div>
              {i < 9 && (
                <svg className="w-4 h-4 text-white/15 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
