import { useEffect, useState } from "react";
import { ExternalLink, Mail, Receipt, RotateCcw, Store, Ticket, Zap } from "lucide-react";
import { api } from "../lib/api";
import { PageHeader, Panel } from "../components/ui";

const APPS = [
  { path: "/mail", name: "Mail", icon: Mail, desc: "Shared AP + support inbox with PDF invoices (and one malicious email)." },
  { path: "/erp/bills", name: "Ledger ERP", icon: Receipt, desc: "Accounts payable. Validation, duplicate detection, payments." },
  { path: "/helpdesk", name: "Helpdesk", icon: Ticket, desc: "Internal tickets with notes and close/reopen." },
  { path: "/portal", name: "Globex portal", icon: Store, desc: "External vendor portal behind a login (vault credentials)." },
];

export default function Sandbox() {
  const [url, setUrl] = useState("");
  const [chaos, setChaos] = useState<{ level: number; log: { ts: number; fault: string; method: string; path: string }[] }>({ level: 0, log: [] });
  const [state, setState] = useState<any>(null);
  const [msg, setMsg] = useState("");

  const load = () => {
    api.chaos().then(setChaos).catch(() => {});
    api.sandboxState().then(setState).catch(() => {});
  };
  useEffect(() => {
    api.health().then((h) => setUrl(h.sandbox_url)).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const reset = async () => { await api.resetSandbox(); setMsg("Sandbox data reset to seed state."); load(); setTimeout(() => setMsg(""), 3000); };

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <PageHeader title="Sandbox: Northwind Corp"
                  subtitle="A small but real company environment: four server-rendered web apps with their own rules and validation, which Atlas operates through a real Chromium browser. Nothing here is mocked at the agent level."
                  right={<button className="btn-ghost" onClick={reset}><RotateCcw size={14} /> Reset data</button>} />
      {msg && <div className="mb-4 rounded-xl border border-verified/30 bg-verified/10 px-4 py-2 text-sm text-verified">{msg}</div>}
      <div className="grid gap-3 md:grid-cols-4">
        {APPS.map((a) => (
          <a key={a.path} href={`${url}${a.path}`} target="_blank" rel="noreferrer"
             className="group panel p-4 transition hover:border-signal/30">
            <div className="flex items-center justify-between"><a.icon size={18} className="text-signal" /><ExternalLink size={13} className="text-ink-600 group-hover:text-ink-300" /></div>
            <div className="mt-3 font-semibold">{a.name}</div>
            <div className="mt-1 text-xs leading-relaxed text-ink-400">{a.desc}</div>
          </a>
        ))}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-[1fr_1.2fr]">
        <Panel title="Chaos mode" right={<span className="font-mono text-xs text-risk">{Math.round(chaos.level * 100)}%</span>}>
          <p className="text-xs leading-relaxed text-ink-400">Each request has this probability of a fault: a 503 before any work is done, 1.5-3.5s latency, a blocking cookie-consent modal, or vendor-portal session expiry.</p>
          <input type="range" min={0} max={0.6} step={0.05} value={chaos.level} className="mt-4 w-full accent-[#ff5d6c]"
                 onChange={(e) => api.setChaos(+e.target.value).then(load)} />
          <div className="panel-title mb-2 mt-5">Injected faults (latest first)</div>
          <div className="max-h-56 space-y-1 overflow-y-auto font-mono text-[11px] scroll-thin">
            {chaos.log.length === 0 ? <div className="text-ink-400">No faults injected yet.</div> :
              [...chaos.log].reverse().map((l, i) => (
                <div key={i} className="flex gap-2 text-ink-300">
                  <Zap size={11} className="mt-0.5 shrink-0 text-risk" />
                  <span className="w-20 text-risk">{l.fault}</span><span className="text-ink-400">{l.method}</span><span className="truncate">{l.path}</span>
                </div>
              ))}
          </div>
        </Panel>
        <Panel title="Ground truth · ERP bills" bodyClass="p-0 max-h-96 overflow-y-auto scroll-thin">
          <table className="w-full text-xs">
            <thead><tr className="border-b border-white/[0.06] text-left text-ink-400"><th className="px-3 py-2">Vendor</th><th className="px-3 py-2">Invoice</th><th className="px-3 py-2 text-right">Amount</th><th className="px-3 py-2">Due</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">By</th></tr></thead>
            <tbody className="divide-y divide-white/[0.04]">
              {state?.bills?.map((b: any) => (
                <tr key={b.id} className={b.created_by !== "seed" ? "bg-verified/[0.06]" : ""}>
                  <td className="px-3 py-1.5">{b.vendor}</td><td className="px-3 py-1.5 font-mono">{b.invoice_number}</td>
                  <td className="px-3 py-1.5 text-right font-mono">{b.amount.toFixed(2)}</td><td className="px-3 py-1.5 font-mono">{b.due_date}</td>
                  <td className="px-3 py-1.5">{b.status}</td><td className="px-3 py-1.5 text-ink-400">{b.created_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
