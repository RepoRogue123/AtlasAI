import { motion } from "framer-motion";
import clsx from "clsx";
import { AlertOctagon, BadgeCheck, CheckCircle2, CircleSlash, ShieldAlert, Sparkles, XCircle } from "lucide-react";
import type { Report } from "../lib/api";
import { fmtCost, fmtDuration, fmtTokens, STATUS_META } from "../lib/format";
import { Stat } from "./ui";

const HERO: Record<string, { icon: React.ReactNode; ring: string; text: string }> = {
  success: { icon: <BadgeCheck size={26} />, ring: "border-verified/40 bg-verified/10 text-verified", text: "text-verified" },
  failed_verification: { icon: <XCircle size={26} />, ring: "border-risk/40 bg-risk/10 text-risk", text: "text-risk" },
  failed: { icon: <XCircle size={26} />, ring: "border-risk/40 bg-risk/10 text-risk", text: "text-risk" },
  error: { icon: <AlertOctagon size={26} />, ring: "border-risk/40 bg-risk/10 text-risk", text: "text-risk" },
  blocked: { icon: <CircleSlash size={26} />, ring: "border-human/40 bg-human/10 text-human", text: "text-human" },
};
const DEFAULT_HERO = { icon: <CheckCircle2 size={26} />, ring: "border-signal/40 bg-signal/10 text-signal", text: "text-signal" };

export default function ReportCard({ report, onShot }: { report: Report; onShot: (url: string) => void }) {
  const hero = HERO[report.status] ?? DEFAULT_HERO;
  const v = report.verification;
  return (
    <motion.section initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="panel overflow-hidden">
      <div className="flex items-start gap-4 p-5">
        <div className={clsx("flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border", hero.ring)}>{hero.icon}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <div className={clsx("font-display text-xl font-semibold", hero.text)}>{STATUS_META[report.status]?.label ?? report.status}</div>
            {report.skill_learned && (
              <span className="chip border-signal/30 bg-signal/10 py-1 text-signal">
                <Sparkles size={11} /> {report.skill_learned.merged ? "skill refined" : "skill learned"}: {report.skill_learned.name}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-ink-100">{report.summary}</p>
        </div>
      </div>

      <div className="grid gap-px border-t border-white/[0.05] bg-white/[0.04] md:grid-cols-2">
        <div className="bg-ink-900 p-5">
          <div className="panel-title mb-3">Results</div>
          {report.results.length === 0 ? <div className="text-xs text-ink-400">No structured results reported.</div> : (
            <dl className="space-y-2">
              {report.results.map((r, i) => (
                <div key={i} className="flex justify-between gap-4 text-sm">
                  <dt className="text-ink-400">{r.label}</dt>
                  <dd className="text-right font-mono text-[12.5px] font-medium text-ink-100">{r.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {report.evidence.length > 0 && (
            <>
              <div className="panel-title mb-2 mt-5">Evidence</div>
              <ul className="space-y-1">{report.evidence.map((e, i) => <li key={i} className="truncate font-mono text-[11.5px] text-info" title={e}>{e}</li>)}</ul>
            </>
          )}
          {report.facts.length > 0 && (
            <>
              <div className="panel-title mb-2 mt-5">Provenance</div>
              <div className="flex flex-wrap gap-1.5">
                {report.facts.map((f) => (
                  <button key={f.key} onClick={() => f.screenshot && onShot(f.screenshot)}
                          className="chip border-white/10 py-1 text-ink-300 hover:border-verified/40" title={`from ${f.source}`}>
                    {f.key}: <b className="text-ink-100">{f.value}</b>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="bg-ink-900 p-5">
          <div className="mb-3 flex items-center justify-between">
            <div className="panel-title">Independent verification</div>
            {v && <span className={clsx("chip", v.verdict === "verified" ? "border-verified/40 text-verified" : "border-risk/40 text-risk")}>{v.verdict}</span>}
          </div>
          {!v ? <div className="text-xs text-ink-400">Not verified (the agent did not claim success).</div> : (
            <ul className="space-y-2.5">
              {v.criteria.map((c, i) => (
                <li key={i} className="flex gap-2.5">
                  {c.passed ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-verified" /> : <XCircle size={15} className="mt-0.5 shrink-0 text-risk" />}
                  <div className="min-w-0">
                    <div className="text-[13px] text-ink-100">{c.criterion}</div>
                    <div className="text-[11.5px] leading-relaxed text-ink-400">{c.evidence}</div>
                  </div>
                </li>
              ))}
              {v.notes && <li className="text-[11.5px] italic text-ink-400">{v.notes}</li>}
            </ul>
          )}
          {report.security.length > 0 && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-risk/30 bg-risk/[0.07] p-3 text-xs text-ink-300">
              <ShieldAlert size={14} className="mt-0.5 shrink-0 text-risk" />
              <span>{report.security.length} prompt-injection attempt(s) detected in {report.security.map((s) => s.source).join(", ")}. Not acted upon.</span>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4 border-t border-white/[0.05] px-5 py-3 md:grid-cols-6">
        <Stat label="Steps" value={report.steps} />
        <Stat label="Recoveries" value={report.failures} tone={report.failures ? "text-signal" : undefined} />
        <Stat label="Retries" value={report.retries} />
        <Stat label="Tokens" value={fmtTokens(report.usage.input_tokens + report.usage.output_tokens)} />
        <Stat label="Cost" value={fmtCost(report.usage.cost_usd)} />
        <Stat label="Duration" value={fmtDuration(report.duration_s)} />
      </div>
    </motion.section>
  );
}
