import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { AlertTriangle, Sparkles, Trash2 } from "lucide-react";
import { api, type Skill } from "../lib/api";
import { Empty, PageHeader } from "../components/ui";
import { fmtAgo } from "../lib/format";

export default function Skills() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const load = () => api.skills().then(setSkills).catch(() => {});
  useEffect(() => { load(); }, []);
  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <PageHeader title="Skill Library"
                  subtitle="After a verified success, Atlas distils the trajectory into a reusable, parameterised procedure. Similar future tasks retrieve it as guidance, so they need fewer exploration steps. Skills are hints, not scripts: the agent still observes and adapts." />
      {skills.length === 0 ? (
        <div className="panel"><Empty icon={<Sparkles size={26} />} title="No skills learned yet">Complete a task successfully (verified) and its skill will appear here. Run the same kind of task again to see it reused.</Empty></div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {skills.map((s, i) => (
            <motion.div key={s.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="panel p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-mono text-sm font-semibold text-signal">{s.name}</div>
                  <p className="mt-1 text-sm text-ink-300">{s.summary}</p>
                </div>
                <button onClick={() => api.deleteSkill(s.id).then(load)} className="rounded-lg p-1.5 text-ink-400 hover:bg-risk/10 hover:text-risk" title="Forget skill"><Trash2 size={14} /></button>
              </div>
              <div className="mt-2 text-xs text-ink-400"><b className="text-ink-300">Applies when:</b> {s.applies_when}</div>
              <ol className="mt-4 space-y-1.5">
                {s.procedure.map((p, j) => (
                  <li key={j} className="flex gap-2.5 text-[13px] text-ink-100">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-white/5 font-mono text-[10px] text-ink-400">{j + 1}</span>{p}
                  </li>
                ))}
              </ol>
              {s.pitfalls.length > 0 && (
                <div className="mt-4 space-y-1 rounded-xl border border-signal/20 bg-signal/[0.05] p-3">
                  {s.pitfalls.map((p, j) => <div key={j} className="flex gap-2 text-xs text-ink-300"><AlertTriangle size={12} className="mt-0.5 shrink-0 text-signal" />{p}</div>)}
                </div>
              )}
              <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
                <span className="chip border-verified/30 text-verified">{s.successes} verified success{s.successes === 1 ? "" : "es"}</span>
                <span className="chip border-white/10">used {s.uses}x</span>
                {s.keywords.slice(0, 6).map((k) => <span key={k} className="chip border-white/10">{k}</span>)}
                <span className="ml-auto">updated {fmtAgo(s.updated_at)}{s.source_run && <> · <Link className="text-info hover:underline" to={`/runs/${s.source_run}`}>origin run</Link></>}</span>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
