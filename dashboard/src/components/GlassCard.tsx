"use client";

import { ReactNode } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export default function GlassCard({ children, className = "", hover = true }: GlassCardProps) {
  return (
    <div className={`${hover ? "glass-card" : "glass-subtle"} p-6 ${className}`}>
      {children}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: string | number;
  variant?: "blue" | "purple" | "amber";
  subtitle?: string;
}

export function StatCard({ label, value, variant = "blue", subtitle }: StatCardProps) {
  const cls =
    variant === "purple"
      ? "stat-value-purple"
      : variant === "amber"
        ? "stat-value-amber"
        : "stat-value";

  return (
    <div className="glass-card p-5">
      <p className="text-xs text-white/40 uppercase tracking-wider mb-2">{label}</p>
      <p className={`text-3xl font-bold ${cls}`}>{value}</p>
      {subtitle && <p className="text-xs text-white/30 mt-1">{subtitle}</p>}
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "running"
      ? "badge-running"
      : status === "completed"
        ? "badge-completed"
        : status === "failed"
          ? "badge-failed"
          : "badge-started";

  return <span className={`glass-badge ${cls}`}>{status}</span>;
}
