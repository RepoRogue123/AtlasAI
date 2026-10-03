import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import { Boxes, FlaskConical, History, LayoutDashboard, Sparkles, Zap } from "lucide-react";
import { api } from "../lib/api";

const NAV = [
  { to: "/", label: "Mission Control", icon: LayoutDashboard },
  { to: "/runs", label: "Runs & Replay", icon: History },
  { to: "/skills", label: "Skill Library", icon: Sparkles },
  { to: "/evals", label: "Evaluations", icon: FlaskConical },
  { to: "/sandbox", label: "Sandbox", icon: Boxes },
];

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="#0e121c" stroke="rgba(255,255,255,.08)" />
      <path d="M16 6 26.5 25.5h-21Z" fill="none" stroke="#f5b544" strokeWidth="2.6" strokeLinejoin="round" />
      <circle cx="16" cy="19" r="2.6" fill="#3ddc97" />
    </svg>
  );
}

function HealthBadge() {
  const [h, setH] = useState<Awaited<ReturnType<typeof api.health>> | null>(null);
  const [chaos, setChaos] = useState(0);
  useEffect(() => {
    const load = () => {
      api.health().then(setH).catch(() => setH(null));
      api.chaos().then((c) => setChaos(c.level)).catch(() => {});
    };
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);
  const dot = (ok: boolean) => <span className={clsx("h-1.5 w-1.5 rounded-full", ok ? "bg-verified" : "bg-risk")} />;
  return (
    <div className="space-y-2 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 font-mono text-[10.5px] text-ink-300">
      <div className="flex items-center gap-2">{dot(!!h?.ok)} API</div>
      <div className="flex items-center gap-2">{dot(!!h?.sandbox)} Sandbox suite</div>
      <div className="flex items-center gap-2">{dot(!!h?.llm_ready)}
        <span className="truncate" title={h?.model ?? ""}>{h?.llm_ready ? h.model ?? "Gemini" : "No LLM key in .env"}</span>
      </div>
      {!!h?.fallbacks?.length && (
        <div className="flex items-center gap-2 text-ink-400">{dot(true)} fallback: {h.fallbacks.join(", ")}</div>
      )}
      {chaos > 0 && (
        <div className="flex items-center gap-2 text-risk"><Zap size={11} /> Chaos {Math.round(chaos * 100)}%</div>
      )}
    </div>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-white/[0.06] bg-ink-950/70 px-4 py-5 backdrop-blur-xl">
        <div className="mb-8 flex items-center gap-3 px-1">
          <Logo />
          <div>
            <div className="font-display text-lg font-semibold leading-none tracking-tight">Atlas</div>
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-ink-400">AI task worker</div>
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition",
                  isActive ? "bg-white/[0.06] text-ink-100" : "text-ink-300 hover:bg-white/[0.03] hover:text-ink-100",
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto"><HealthBadge /></div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto scroll-thin">{children}</main>
    </div>
  );
}
