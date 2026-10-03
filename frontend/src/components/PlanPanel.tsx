import { motion } from "framer-motion";
import clsx from "clsx";
import { Check, Circle, Loader2, Minus, X } from "lucide-react";
import type { Plan, Verification } from "../lib/api";
import { Panel } from "./ui";

const ICON: Record<string, React.ReactNode> = {
  done: <Check size={12} className="text-verified" />,
  in_progress: <Loader2 size={12} className="animate-spin text-signal" />,
  failed: <X size={12} className="text-risk" />,
  skipped: <Minus size={12} className="text-ink-400" />,
};

export default function PlanPanel({ plan, verification }: { plan: Plan | null; verification?: Verification }) {
  return (
    <Panel className="flex-1" title="Plan" right={plan && plan.version > 0 && <span className="chip border-signal/30 text-signal">revised v{plan.version + 1}</span>}
           bodyClass="p-4 overflow-y-auto scroll-thin">
      {!plan ? (
        <div className="space-y-2">{[0, 1, 2, 3].map((i) => <div key={i} className="h-4 animate-pulse rounded bg-white/5" style={{ width: `${90 - i * 12}%` }} />)}</div>
      ) : (
        <>
          <p className="text-[13px] leading-relaxed text-ink-100">{plan.understanding}</p>
          <ol className="mt-4 space-y-1.5">
            {plan.steps.map((s, i) => (
              <motion.li key={`${plan.version}-${i}`} layout initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
                         transition={{ delay: i * 0.03 }}
                         className={clsx("flex items-start gap-2.5 text-[13px]", s.status === "done" ? "text-ink-400" : "text-ink-100")}>
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-white/10">
                  {ICON[s.status] ?? <Circle size={6} className="fill-ink-600 text-ink-600" />}
                </span>
                <span className={clsx(s.status === "done" && "line-through decoration-ink-600")}>{s.title}</span>
              </motion.li>
            ))}
          </ol>
          <div className="panel-title mt-5">Success criteria</div>
          <ul className="mt-2 space-y-1.5">
            {plan.success_criteria.map((c, i) => {
              const v = verification?.criteria?.[i];
              return (
                <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-ink-300">
                  <span className={clsx("mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                    v ? (v.passed ? "bg-verified" : "bg-risk") : "bg-ink-600")} />
                  {c}
                </li>
              );
            })}
          </ul>
          {plan.ambiguities.length > 0 && (
            <>
              <div className="panel-title mt-5">Flagged ambiguities</div>
              <ul className="mt-2 space-y-1 text-xs text-human">{plan.ambiguities.map((a, i) => <li key={i}>• {a}</li>)}</ul>
            </>
          )}
        </>
      )}
    </Panel>
  );
}
