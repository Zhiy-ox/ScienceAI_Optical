"use client";

import { useState } from "react";
import GlassCard, { StatCard } from "@/components/GlassCard";

/** Demo cost data for offline mode. */
const DEMO_COST_DATA = {
  total_usd: 7.80,
  by_model: {
    "claude-opus-4-6": 3.85,
    "gpt-5.4": 2.45,
    "claude-sonnet-4-6": 0.95,
    "gemini/gemini-3.1-pro": 0.55,
  },
  by_agent: {
    deep_reader: 2.90,
    report_writer: 1.65,
    gap_detector: 1.20,
    critique: 0.80,
    query_planner: 0.45,
    paper_triage: 0.40,
    verification: 0.25,
    idea_generator: 0.15,
  },
  call_count: 42,
  cache_savings: 1.23,
  sessions: 5,
};

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

export default function CostsPage() {
  const [data] = useState(DEMO_COST_DATA);

  const maxModelCost = Math.max(...Object.values(data.by_model));
  const maxAgentCost = Math.max(...Object.values(data.by_agent));

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
          value={`$${(data.total_usd / data.sessions).toFixed(2)}`}
          variant="amber"
        />
      </div>

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

          {/* Pie-chart-like breakdown */}
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
