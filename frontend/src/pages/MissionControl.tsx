import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import clsx from "clsx";
import {
  ArrowRight, CheckCheck, Eye, GraduationCap, ListTree, MousePointerClick, Rocket, Scale, ShieldCheck,
  Sparkles, Target, Wrench, Zap,
} from "lucide-react";
import { api, type Example, type RunRow } from "../lib/api";
import { StatusPill } from "../components/ui";
import { fmtAgo, fmtCost } from "../lib/format";

const AUTONOMY = [
  { id: "supervised", label: "Supervised", icon: ShieldCheck, desc: "Approve every state-changing action." },
  { id: "balanced", label: "Balanced", icon: Scale, desc: "Approve only irreversible / financial actions." },
  { id: "autonomous", label: "Autonomous", icon: Rocket, desc: "No approvals. Injection guard still enforced." },
];

const PIPELINE = [
  { icon: Target, label: "Understand", note: "goal + success criteria" },
  { icon: ListTree, label: "Plan", note: "re-plans on surprises" },
  { icon: MousePointerClick, label: "Act", note: "real browser, files, APIs" },
  { icon: Eye, label: "Observe", note: "fresh state every step" },
  { icon: Wrench, label: "Recover", note: "classified failures" },
  { icon: CheckCheck, label: "Verify", note: "independent auditor" },
  { icon: GraduationCap, label: "Learn", note: "distils reusable skills" },
];

export default function MissionControl() {
  const nav = useNavigate();
  const [goal, setGoal] = useState("");
  const [autonomy, setAutonomy] = useState("balanced");
  const [useSkills, setUseSkills] = useState(true);
  const [chaos, setChaos] = useState(0);
  const [examples, setExamples] = useState<Example[]>([]);
  const [recent, setRecent] = useState<RunRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.examples().then(setExamples).catch(() => {});
    api.runs().then((r) => setRecent(r.filter((x) => x.source !== "eval").slice(0, 6))).catch(() => {});
    api.chaos().then((c) => setChaos(c.level)).catch(() => {});
  }, []);

  const launch = async () => {
    if (!goal.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      await api.setChaos(chaos);
      const { run_id } = await api.startRun(goal, autonomy, useSkills);
      nav(`/runs/${run_id}`);
    } catch (e) {
      setErr(String((e as Error).message));
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.22em] text-signal">
          <Sparkles size={13} /> Autonomous AI task worker
        </div>
        <h1 className="font-display text-4xl font-semibold tracking-tight">
          Tell Atlas the outcome. <span className="text-ink-400">It works out the steps.</span>
        </h1>
        <p className="mt-3 max-w-2xl text-ink-300">
          Atlas operates real software (browser, documents, APIs) to complete business tasks, recovers from failures,
          asks when it should, and proves the result with an independent verifier.
        </p>
      </motion.div>

      {/* Composer */}
      <motion.div
        initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.4 }}
        className="panel mt-8 p-1.5"
        style={{ boxShadow: "0 0 0 1px rgba(245,181,68,.12), 0 30px 80px -40px rgba(245,181,68,.35)" }}
      >
        <textarea
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) launch(); }}
          placeholder="e.g. Find the latest invoice from Acme Supplies, extract the amount and due date, enter it into our internal system, and tell me once it is done."
          className="h-32 w-full resize-none rounded-xl bg-transparent px-4 py-3 text-[15px] leading-relaxed text-ink-100 placeholder:text-ink-600 focus:outline-none"
        />
        <div className="flex flex-wrap items-center gap-3 border-t border-white/[0.05] px-3 py-3">
          <div className="flex rounded-xl border border-white/[0.07] bg-ink-950/60 p-1">
            {AUTONOMY.map((a) => (
              <button
                key={a.id}
                onClick={() => setAutonomy(a.id)}
                title={a.desc}
                className={clsx(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition",
                  autonomy === a.id ? "bg-white/[0.08] text-ink-100" : "text-ink-400 hover:text-ink-100",
                )}
              >
                <a.icon size={13} /> {a.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 rounded-xl border border-white/[0.07] bg-ink-950/60 px-3 py-1.5 text-xs text-ink-300"
                 title="Inject random 503s, latency, blocking modals and session expiry into the sandbox apps">
            <Zap size={13} className={chaos > 0 ? "text-risk" : ""} /> Chaos
            <input type="range" min={0} max={0.6} step={0.05} value={chaos}
                   onChange={(e) => setChaos(parseFloat(e.target.value))} className="w-24 accent-[#ff5d6c]" />
            <span className="w-8 font-mono tabular-nums">{Math.round(chaos * 100)}%</span>
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-300">
            <input type="checkbox" checked={useSkills} onChange={(e) => setUseSkills(e.target.checked)} className="accent-[#f5b544]" />
            Use learned skills
          </label>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden font-mono text-[10.5px] text-ink-400 md:inline">Ctrl + Enter</span>
            <button className="btn-primary" disabled={busy || !goal.trim()} onClick={launch}>
              {busy ? "Launching..." : "Launch Atlas"} <ArrowRight size={15} />
            </button>
          </div>
        </div>
        <div className="px-4 pb-2 text-[11.5px] text-ink-400">{AUTONOMY.find((a) => a.id === autonomy)?.desc}</div>
      </motion.div>
      {err && <div className="mt-3 rounded-xl border border-risk/30 bg-risk/10 px-4 py-2 text-sm text-risk">{err}</div>}

      {/* Pipeline */}
      <div className="mt-8 grid grid-cols-7 gap-2">
        {PIPELINE.map((p, i) => (
          <motion.div key={p.label} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.15 + i * 0.05 }}
                      className="relative rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-3">
            <p.icon size={16} className="text-signal" />
            <div className="mt-2 text-sm font-semibold">{p.label}</div>
            <div className="text-[11px] leading-snug text-ink-400">{p.note}</div>
          </motion.div>
        ))}
      </div>

      {/* Examples */}
      <div className="mt-10 flex items-end justify-between">
        <h2 className="panel-title">Try a task from the evaluation suite</h2>
        <span className="text-xs text-ink-400">Same agent kernel for every task</span>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {examples.map((ex) => (
          <button key={ex.id} onClick={() => setGoal(ex.goal)}
                  className="group rounded-2xl border border-white/[0.06] bg-ink-900/60 p-4 text-left transition hover:border-signal/30 hover:bg-ink-850">
            <div className="text-sm font-semibold group-hover:text-signal">{ex.title}</div>
            <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-ink-400">{ex.goal}</p>
            <div className="mt-3 flex flex-wrap gap-1">
              {ex.tags.map((t) => <span key={t} className="chip border-white/10 text-ink-300">{t}</span>)}
            </div>
          </button>
        ))}
      </div>

      {/* Recent */}
      {recent.length > 0 && (
        <>
          <h2 className="panel-title mt-10">Recent runs</h2>
          <div className="mt-3 divide-y divide-white/[0.05] overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-900/60">
            {recent.map((r) => (
              <Link key={r.id} to={`/runs/${r.id}`} className="flex items-center gap-4 px-4 py-3 text-sm hover:bg-white/[0.02]">
                <StatusPill status={r.status} />
                <span className="min-w-0 flex-1 truncate text-ink-300">{r.goal}</span>
                {r.report && <span className="font-mono text-xs text-ink-400">{r.report.steps} steps · {fmtCost(r.report.usage.cost_usd)}</span>}
                <span className="w-20 text-right text-xs text-ink-400">{fmtAgo(r.created_at)}</span>
              </Link>
            ))}
          </div>
        </>
      )}
      <div className="h-6" />
    </div>
  );
}
