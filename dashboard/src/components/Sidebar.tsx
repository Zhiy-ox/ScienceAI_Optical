"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Dashboard", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4" },
  { href: "/new", label: "New Research", icon: "M12 4v16m8-8H4" },
  { href: "/costs", label: "Cost Analytics", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="glass fixed left-4 top-4 bottom-4 w-64 p-6 flex flex-col z-10"
      style={{ borderRadius: "24px" }}>
      {/* Logo */}
      <div className="mb-10">
        <h1 className="text-xl font-bold tracking-tight">
          <span className="stat-value">Science</span>
          <span className="text-white/60"> AI</span>
        </h1>
        <p className="text-xs text-white/30 mt-1 font-mono">Optical Research Assistant</p>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-2 flex-1">
        {navItems.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-300 group ${
                active
                  ? "bg-white/10 border border-white/15 shadow-lg shadow-black/10"
                  : "hover:bg-white/5 border border-transparent"
              }`}
            >
              <svg
                className={`w-5 h-5 transition-colors ${
                  active ? "text-[var(--accent-blue)]" : "text-white/40 group-hover:text-white/60"
                }`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
              </svg>
              <span
                className={`text-sm font-medium ${
                  active ? "text-white" : "text-white/50 group-hover:text-white/70"
                }`}
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Version badge */}
      <div className="glass-subtle px-4 py-3 text-center">
        <span className="text-xs text-white/30 font-mono">v0.4.0</span>
      </div>
    </aside>
  );
}
