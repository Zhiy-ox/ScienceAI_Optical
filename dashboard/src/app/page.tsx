"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import GlassCard, { StatCard, StatusBadge } from "@/components/GlassCard";
import { api, type HealthResponse, type SessionListItem } from "@/lib/api";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [connected, setConnected] = useState(false);
  const [keysConfigured, setKeysConfigured] = useState(true);

  useEffect(() => {
    api.health()
      .then((h) => {
        setHealth(h);
        setConnected(true);
      })
      .catch(() => setConnected(false));

    api.listSessions()
      .then(setSessions)
      .catch(() => {});

    api.getSettings()
      .then((s) => {
        const hasKey = !!(s.openai_api_key || s.anthropic_api_key || s.google_api_key);
        setKeysConfigured(hasKey);
      })
      .catch(() => {});
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

      {/* API key warning */}
      {connected && !keysConfigured && (
        <GlassCard hover={false} className="border-[var(--accent-amber)]" style={{ borderColor: "var(--accent-amber)" }}>
          <div className="flex items-center gap-3">
            <svg className="w-5 h-5 text-[var(--accent-amber)] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <div>
              <p className="text-sm text-[var(--accent-amber)] font-medium">No API keys configured</p>
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

        {sessions.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-white/40 text-sm">No sessions yet — start your first research.</p>
            <Link href="/new" className="text-[var(--accent-blue)] text-sm mt-2 inline-block hover:text-[var(--accent-teal)]">
              Start Research →
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/5">
                  <th className="text-left text-xs text-white/30 uppercase tracking-wider pb-3 font-medium">
                    Question
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
                    <td className="py-4 max-w-xs">
                      <span className="text-sm text-white/70 truncate block">
                        {sess.question || sess.session_id.slice(0, 12) + "..."}
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
        )}
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
