import clsx from "clsx";
import type { ReactNode } from "react";
import { STATUS_META, TONE } from "../lib/format";

export function StatusPill({ status, className }: { status: string; className?: string }) {
  const meta = STATUS_META[status] ?? { label: status, tone: "muted" };
  return (
    <span className={clsx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", TONE[meta.tone], className)}>
      {(status === "running" || status === "awaiting_human") && (
        <span className={clsx("h-1.5 w-1.5 rounded-full pulse-dot", status === "running" ? "bg-signal" : "bg-human")} />
      )}
      {meta.label}
    </span>
  );
}

export function Panel({ title, right, children, className, bodyClass }: {
  title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <section className={clsx("panel flex min-h-0 flex-col", className)}>
      {title && (
        <header className="flex items-center justify-between border-b border-white/[0.05] px-4 py-2.5">
          <h3 className="panel-title">{title}</h3>
          {right}
        </header>
      )}
      <div className={clsx("min-h-0 flex-1", bodyClass ?? "p-4")}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: string; hint?: string }) {
  return (
    <div className="min-w-0" title={hint}>
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-400">{label}</div>
      <div className={clsx("mt-0.5 truncate font-display text-lg font-semibold tabular-nums", tone)}>{value}</div>
    </div>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-ink-400">
      <div className="text-ink-600">{icon}</div>
      <div className="text-sm font-medium text-ink-300">{title}</div>
      {children && <div className="max-w-sm text-xs">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-ink-300">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
