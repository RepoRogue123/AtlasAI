import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CheckCircle2, FlaskConical, Loader2, Play, XCircle, Zap } from "lucide-react";
import { api, type EvalReport } from "../lib/api";
import { Empty, PageHeader, Panel, Stat } from "../components/ui";
import { fmtAgo, fmtCost, fmtDuration } from "../lib/format";

const tooltipStyle = { background: "#0e121c", border: "1px solid rgba(255,255,255,.08)", borderRadius: 10, fontSize: 12 };

export default function Evals() {
  const [reports, setReports] = useState<EvalReport[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [status, setStatus] = useState<Awaited<ReturnType<typeof api.evalStatus>>>({ running: false });
  const [chaos, setChaos] = useState(0);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    api.evals().then(setReports).catch(() => {});
    api.evalStatus().then(setStatus).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t); }, []);

  const report = reports.find((r) => r.id === selected) ?? reports[0];
  const start = () => { setErr(null); api.runEvals(chaos).then(load).catch((e) => setErr(String(e.message))); };

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <PageHeader title="Evaluations"
                  subtitle="Eight diverse tasks run through the same, unchanged agent kernel. Each is checked against ground truth read directly from the sandbox database, independent of both the agent and its verifier."
                  right={
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-2 rounded-xl border border-white/10 px-3 py-2 text-xs text-ink-300">
                        <Zap size={13} className={chaos ? "text-risk" : ""} /> Chaos
                        <select value={chaos} onChange={(e) => setChaos(+e.target.value)} className="bg-transparent font-mono text-ink-100 focus:outline-none">
                          {[0, 0.15, 0.3, 0.5].map((c) => <option key={c} value={c} className="bg-ink-900">{Math.round(c * 100)}%</option>)}
                        </select>
                      </label>
                      <button className="btn-primary" disabled={status.running} onClick={start}>
                        {status.running ? <><Loader2 size={14} className="animate-spin" /> {status.done}/{status.total} · {status.current}</> : <><Play size={14} /> Run suite</>}
                      </button>
                    </div>
                  } />
      {err && <div className="mb-4 rounded-xl border border-risk/30 bg-risk/10 px-4 py-2 text-sm text-risk">{err}</div>}
      {!report ? (
        <div className="panel"><Empty icon={<FlaskConical size={26} />} title="No eval reports yet">Run the suite here or via <code className="font-mono">python -m evals.runner --chaos 0.3</code>.</Empty></div>
      ) : (
        <div className="space-y-4">
          <div className="panel grid grid-cols-2 gap-6 p-5 md:grid-cols-6">
            <Stat label="Success rate" value={`${Math.round(report.success_rate * 100)}%`} tone={report.success_rate >= 0.75 ? "text-verified" : "text-signal"} />
            <Stat label="Passed" value={`${report.passed}/${report.total}`} />
            <Stat label="Verifier agreement" value={report.verifier_agreement == null ? "-" : `${Math.round(report.verifier_agreement * 100)}%`}
                  hint="How often the agent's own verifier agreed with ground truth" />
            <Stat label="Avg steps" value={report.avg_steps} />
            <Stat label="Chaos" value={`${Math.round(report.chaos * 100)}%`} tone={report.chaos ? "text-risk" : undefined} />
            <Stat label="Total cost" value={fmtCost(report.total_cost_usd)} />
          </div>

          <div className="grid gap-4 md:grid-cols-[1.3fr_1fr]">
            <Panel title="Steps per task (green = passed)">
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={report.tasks} margin={{ left: -20, right: 8, top: 8 }}>
                    <CartesianGrid stroke="rgba(255,255,255,.05)" vertical={false} />
                    <XAxis dataKey="id" tick={{ fill: "#6b7591", fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={56} />
                    <YAxis tick={{ fill: "#6b7591", fontSize: 11 }} allowDecimals={false} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,.03)" }} />
                    <Bar dataKey="steps" radius={[6, 6, 0, 0]}>
                      {report.tasks.map((t) => <Cell key={t.id} fill={t.passed ? "#3ddc97" : "#ff5d6c"} fillOpacity={0.85} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Report history" bodyClass="p-2 max-h-80 overflow-y-auto scroll-thin">
              {reports.map((r) => (
                <button key={r.id} onClick={() => setSelected(r.id)}
                        className={clsx("flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition",
                          r.id === report.id ? "bg-white/[0.06]" : "hover:bg-white/[0.03]")}>
                  <span className={clsx("font-display text-base font-semibold tabular-nums", r.success_rate >= 0.75 ? "text-verified" : "text-signal")}>
                    {Math.round(r.success_rate * 100)}%
                  </span>
                  <span className="flex-1 text-xs text-ink-300">{r.passed}/{r.total} tasks · {r.chaos ? <span className="text-risk">chaos {Math.round(r.chaos * 100)}%</span> : "clean"}</span>
                  <span className="text-[11px] text-ink-400">{fmtAgo(r.created_at)}</span>
                </button>
              ))}
            </Panel>
          </div>

          <Panel title={`Tasks · report ${report.id} · ${fmtDuration(report.duration_s)}`} bodyClass="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06] text-left font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-400">
                  <th className="px-4 py-2.5">Result</th><th className="px-4 py-2.5">Task</th><th className="px-4 py-2.5">Ground truth</th>
                  <th className="px-4 py-2.5">Verifier</th><th className="px-4 py-2.5 text-right">Steps</th><th className="px-4 py-2.5 text-right">Recov.</th>
                  <th className="px-4 py-2.5 text-right">Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {report.tasks.map((t) => (
                  <tr key={t.id}>
                    <td className="px-4 py-2.5">{t.passed ? <CheckCircle2 size={16} className="text-verified" /> : <XCircle size={16} className="text-risk" />}</td>
                    <td className="px-4 py-2.5">{t.run_id ? <Link to={`/runs/${t.run_id}`} className="hover:text-signal">{t.title}</Link> : t.title}
                      {!!t.injections_detected && <span className="chip ml-2 border-risk/30 text-risk">{t.injections_detected} injection</span>}</td>
                    <td className="max-w-xs px-4 py-2.5 text-xs text-ink-400">{t.detail}</td>
                    <td className="px-4 py-2.5 text-xs">{t.verifier ?? "-"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{t.steps ?? "-"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{t.recoveries ?? "-"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{t.cost_usd != null ? fmtCost(t.cost_usd) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      )}
    </div>
  );
}
