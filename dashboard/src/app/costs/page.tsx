"use client";

import { useEffect, useState } from "react";
import GlassCard, { StatCard } from "@/components/GlassCard";
import { api, type DetailedCostReport } from "@/lib/api";

const MODEL_COLORS: Record<string, string> = {
  "claude-opus-4-6": "var(--accent-purple)",
  "claude-sonnet-4-6": "var(--accent-blue)",
  "gpt-5.4": "var(--accent-teal)",
  "gemini/gemini-3.1-pro": "var(--accent-amber)",
};

const AGENT_COLORS: Record<string, string> = {
  deep_reader: "var(--accent-purple)",
  report_writer: "var(--accent-blue)",
  gap_detector: "var(--accent-rose)",
  critique: "var(--accent-teal)",
  query_planner: "var(--accent-amber)",
  paper_triage: "var(--accent-teal)",
  verification: "var(--accent-blue)",
  idea_generator: "var(--accent-purple)",
};

interface AggregatedCosts {
  total_usd: number;
  by_model: Record<string, number>;
  by_agent: Record<string, number>;
  call_count: number;
  cache_savings: number;
  sessions: number;
}

export default function CostsPage() {
  const [data, setData] = useState<AggregatedCosts>({
    total_usd: 0,
    by_model: {},
    by_agent: {},
    call_count: 0,
    cache_savings: 0,
    sessions: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadCosts() {
      try {
        const sessions = await api.listSessions();
        if (sessions.length === 0) {
          setLoading(false);
          return;
        }

        const agg: AggregatedCosts = {
          total_usd: 0,
          by_model: {},
          by_agent: {},
          call_count: 0,
          cache_savings: 0,
          sessions: sessions.length,
        };

        // Fetch cost reports for completed sessions
        const completed = sessions.filter((s) => s.status === "completed");
        const reports = await Promise.allSettled(
          completed.map((s) => api.getCost(s.session_id))
        );

        for (const r of reports) {
          if (r.status !== "fulfilled") continue;
          const report: DetailedCostReport = r.value;
          agg.total_usd += report.total_usd;
          agg.call_count += report.call_count;
          agg.cache_savings += report.cache_savings_estimate_usd;

          for (const [model, cost] of Object.entries(report.by_model)) {
            agg.by_model[model] = (agg.by_model[model] || 0) + cost;
          }
          for (const [agent, cost] of Object.entries(report.by_agent)) {
            agg.by_agent[agent] = (agg.by_agent[agent] || 0) + cost;
          }
        }

        setData(agg);
      } catch {
        // Stay with empty data
      } finally {
        setLoading(false);
      }
    }
    loadCosts();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="shimmer h-8 w-48" />
        <div className="grid grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map((i) => <div key={i} className="shimmer h-24" />)}
        </div>
        <div className="shimmer h-64" />
      </div>
    );
  }

  const hasData = data.total_usd > 0;
  const maxModelCost = hasData ? Math.max(...Object.values(data.by_model)) : 1;
  const maxAgentCost = hasData ? Math.max(...Object.values(data.by_agent)) : 1;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-white/90">Cost Analytics</h2>
        <p className="text-sm text-white/40 mt-1">
          API usage and cost breakdown across sessions
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Total Spend" value={`$${data.total_usd.toFixed(2)}`} variant="amber" />
        <StatCard label="API Calls" value={data.call_count} />
        <StatCard label="Sessions" value={data.sessions} variant="purple" />
        <StatCard
          label="Cache Savings"
          value={`$${data.cache_savings.toFixed(2)}`}
          subtitle="from prompt caching"
        />
        <StatCard
          label="Avg per Session"
          value={`$${data.sessions > 0 ? (data.total_usd / data.sessions).toFixed(2) : "0.00"}`}
          variant="amber"
        />
      </div>

      {!hasData ? (
        <GlassCard hover={false}>
          <div className="text-center py-12">
            <p className="text-white/40 text-sm">No cost data yet. Complete a research session to see analytics.</p>
          </div>
        </GlassCard>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Cost by model */}
          <GlassCard hover={false}>
            <h3 className="text-base font-semibold text-white/80 mb-6">Cost by Model</h3>
            <div className="space-y-4">
              {Object.entries(data.by_model)
                .sort(([, a], [, b]) => b - a)
                .map(([model, cost]) => {
                  const pct = (cost / maxModelCost) * 100;
                  const color = MODEL_COLORS[model] || "var(--accent-blue)";
                  return (
                    <div key={model}>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-white/60 font-mono text-xs">{model}</span>
                        <span className="text-white/70 font-semibold">${cost.toFixed(2)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${pct}%`, background: color }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>

            <div className="mt-6 pt-4 border-t border-white/5 flex flex-wrap gap-3">
              {Object.entries(data.by_model).map(([model, cost]) => {
                const pct = ((cost / data.total_usd) * 100).toFixed(0);
                const color = MODEL_COLORS[model] || "var(--accent-blue)";
                return (
                  <div key={model} className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                    <span className="text-[11px] text-white/40">
                      {model.split("/").pop()} ({pct}%)
                    </span>
                  </div>
                );
              })}
            </div>
          </GlassCard>

          {/* Cost by agent */}
          <GlassCard hover={false}>
            <h3 className="text-base font-semibold text-white/80 mb-6">Cost by Agent</h3>
            <div className="space-y-4">
              {Object.entries(data.by_agent)
                .sort(([, a], [, b]) => b - a)
                .map(([agent, cost]) => {
                  const pct = (cost / maxAgentCost) * 100;
                  const color = AGENT_COLORS[agent] || "var(--accent-blue)";
                  return (
                    <div key={agent}>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-white/60 text-xs">{agent.replace(/_/g, " ")}</span>
                        <span className="text-white/70 font-semibold">${cost.toFixed(2)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${pct}%`, background: color }}
                        />
                      </div>
                    </div>
                  );
                })}
            </div>
          </GlassCard>
        </div>
      )}

      {/* Optimization tips */}
      <GlassCard hover={false}>
        <h3 className="text-base font-semibold text-white/80 mb-4">Optimization Insights</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="glass-subtle p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-teal)]" />
              <span className="text-xs font-semibold text-white/60">Prompt Caching</span>
            </div>
            <p className="text-xs text-white/40">
              System prompts are cached across agent calls. Saved{" "}
              <span className="text-[var(--accent-teal)] font-semibold">
                ${data.cache_savings.toFixed(2)}
              </span>{" "}
              this period.
            </p>
          </div>
          <div className="glass-subtle p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-blue)]" />
              <span className="text-xs font-semibold text-white/60">Batch API</span>
            </div>
            <p className="text-xs text-white/40">
              Triage and extraction use batch processing for 50% cost reduction on non-realtime tasks.
            </p>
          </div>
          <div className="glass-subtle p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-1.5 h-1.5 rounded-full bg-[var(--accent-amber)]" />
              <span className="text-xs font-semibold text-white/60">Model Routing</span>
            </div>
            <p className="text-xs text-white/40">
              Tasks are routed to the most cost-effective model. Gemini handles bulk triage, Claude handles deep analysis.
            </p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
