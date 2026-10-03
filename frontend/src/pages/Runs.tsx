import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { History } from "lucide-react";
import { api, type RunRow } from "../lib/api";
import { Empty, PageHeader, StatusPill } from "../components/ui";
import { fmtAgo, fmtCost, fmtDuration } from "../lib/format";

export default function Runs() {
  const [runs, setRuns] = useState<RunRow[] | null>(null);
  const [showEvals, setShowEvals] = useState(false);
  useEffect(() => {
    const load = () => api.runs().then(setRuns).catch(() => setRuns([]));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  const rows = (runs ?? []).filter((r) => showEvals || r.source !== "eval");
  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <PageHeader title="Runs & Replay" subtitle="Every run is a persisted event trace. Open one to replay it step by step: thoughts, actions, screenshots, recoveries and the verifier's checks."
                  right={<label className="flex items-center gap-2 text-xs text-ink-300"><input type="checkbox" checked={showEvals} onChange={(e) => setShowEvals(e.target.checked)} className="accent-[#f5b544]" /> include eval runs</label>} />
      <div className="panel overflow-hidden">
        {rows.length === 0 ? <Empty icon={<History size={26} />} title="No runs yet">Launch a task from Mission Control.</Empty> : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-400">
                <th className="px-4 py-3">Status</th><th className="px-4 py-3">Task</th><th className="px-4 py-3">Mode</th>
                <th className="px-4 py-3 text-right">Steps</th><th className="px-4 py-3 text-right">Recov.</th>
                <th className="px-4 py-3 text-right">Cost</th><th className="px-4 py-3 text-right">Time</th><th className="px-4 py-3 text-right">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-white/[0.02]">
                  <td className="px-4 py-3"><StatusPill status={r.status} /></td>
                  <td className="max-w-md px-4 py-3"><Link to={`/runs/${r.id}`} className="line-clamp-1 text-ink-100 hover:text-signal">{r.goal}</Link></td>
                  <td className="px-4 py-3 text-xs text-ink-400">{r.source === "eval" ? "eval" : r.autonomy}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs">{r.report?.steps ?? "-"}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs">{r.report?.failures ?? "-"}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs">{r.report ? fmtCost(r.report.usage.cost_usd) : "-"}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs">{r.report ? fmtDuration(r.report.duration_s) : "-"}</td>
                  <td className="px-4 py-3 text-right text-xs text-ink-400">{fmtAgo(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
