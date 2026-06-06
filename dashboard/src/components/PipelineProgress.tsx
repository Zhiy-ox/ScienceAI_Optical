"use client";

/** Animated node-by-node progress rail driven by SSE events. */

export interface PipelineStage {
  key: string;
  label: string;
}

// The 13-stage pipeline rail (matches graph node `stage` names).
export const PIPELINE_STAGES: PipelineStage[] = [
  { key: "plan", label: "Plan" },
  { key: "search", label: "Search" },
  { key: "triage", label: "Triage" },
  { key: "select", label: "Select" },
  { key: "deep_read", label: "Deep Read" },
  { key: "index", label: "Index" },
  { key: "critique", label: "Critique" },
  { key: "gap_detect", label: "Gap Detect" },
  { key: "verify", label: "Verify" },
  { key: "idea", label: "Ideate" },
  { key: "experiment", label: "Experiment" },
  { key: "report", label: "Report" },
];

interface Props {
  activeStage: string | null;
  completedStages: Set<string>;
  message?: string | null;
}

export default function PipelineProgress({
  activeStage,
  completedStages,
  message,
}: Props) {
  return (
    <div className="glass p-6" style={{ borderRadius: "20px" }}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white/70">Pipeline Progress</h3>
        {message && (
          <span className="text-xs text-[var(--accent-blue)] font-mono animate-pulse">
            {message}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {PIPELINE_STAGES.map((stage, i) => {
          const isActive = activeStage === stage.key;
          const isDone = completedStages.has(stage.key);
          return (
            <div key={stage.key} className="flex items-center gap-2">
              <div
                className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs transition-all duration-500 ${
                  isActive
                    ? "bg-[var(--accent-blue)]/20 border-[var(--accent-blue)]/50 text-white shadow-lg"
                    : isDone
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300/90"
                    : "bg-white/5 border-white/10 text-white/30"
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full transition-all ${
                    isActive
                      ? "bg-[var(--accent-blue)] animate-pulse"
                      : isDone
                      ? "bg-emerald-400"
                      : "bg-white/20"
                  }`}
                />
                {stage.label}
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <span className="text-white/15 text-xs">→</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
