import { useState } from "react";
import { motion } from "framer-motion";
import { CircleHelp, Hand, Send } from "lucide-react";
import clsx from "clsx";
import { api, type AtlasEvent } from "../lib/api";

function Overlay({ children }: { children: React.ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/70 p-6 backdrop-blur-sm">
      <motion.div initial={{ y: 16, scale: 0.98 }} animate={{ y: 0, scale: 1 }} transition={{ type: "spring", damping: 24, stiffness: 300 }}
                  className="panel max-h-[90vh] w-full max-w-3xl overflow-y-auto scroll-thin"
                  style={{ boxShadow: "0 0 0 1px rgba(139,124,255,.25), 0 40px 120px -30px rgba(139,124,255,.35)" }}>
        {children}
      </motion.div>
    </motion.div>
  );
}

export function ApprovalDialog({ runId, event }: { runId: string; event: AtlasEvent }) {
  const d = event.data;
  const [mode, setMode] = useState<"idle" | "reject">("idle");
  const [reason, setReason] = useState("");
  const [text, setText] = useState<string>(d.args?.text ?? "");
  const [busy, setBusy] = useState(false);
  const edited = d.editable && text !== (d.args?.text ?? "");

  const send = async (decision: string) => {
    setBusy(true);
    const body: Record<string, unknown> = { request_id: d.request_id, decision, reason: reason || undefined };
    if (decision === "edit") body.args = { text };
    await api.respond(runId, body).catch(() => setBusy(false));
  };

  return (
    <Overlay>
      <div className="flex items-start gap-4 border-b border-white/[0.06] p-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-human/30 bg-human/10 text-human"><Hand size={18} /></div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="font-display text-lg font-semibold">Approval required</h2>
            <span className={clsx("chip uppercase", d.risk === "critical" ? "border-risk/40 bg-risk/10 text-risk" : "border-signal/40 bg-signal/10 text-signal")}>
              {d.risk}
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-300">
            Atlas wants to run <span className="font-mono text-signal">{d.tool}</span>
            {d.target && <> on <b className="text-ink-100">“{d.target}”</b></>} · {d.reason}
          </p>
          {d.rationale && <p className="mt-2 text-sm italic text-ink-400">“{d.rationale}”</p>}
        </div>
      </div>
      {d.ungrounded?.length > 0 && (
        <div className="mx-5 mt-5 rounded-xl border border-risk/40 bg-risk/10 px-4 py-3 text-sm text-risk">
          <b>Grounding warning:</b> {d.ungrounded.join(", ")} does not appear in any document or page Atlas observed.
          It was asked to re-check once and submitted the same values again. Compare with the source before approving.
        </div>
      )}
      <div className="grid gap-5 p-5 md:grid-cols-[1.4fr_1fr]">
        {d.screenshot ? (
          <img src={d.screenshot} alt="target" className="w-full rounded-xl border border-white/10" />
        ) : <div className="rounded-xl border border-white/10 bg-ink-950 p-6 text-sm text-ink-400">No screenshot</div>}
        <div className="space-y-4">
          {d.form_fields?.length > 0 && (
            <div>
              <div className="panel-title mb-2">Values being submitted</div>
              <table className="w-full text-sm">
                <tbody>
                  {d.form_fields.map((f: { label: string; value: string }, i: number) => (
                    <tr key={i} className="border-b border-white/[0.05]">
                      <td className="py-1.5 pr-3 text-ink-400">{f.label}</td>
                      <td className="py-1.5 font-mono text-[12.5px] text-ink-100">{f.value || <span className="text-ink-600">empty</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {d.editable && (
            <div>
              <div className="panel-title mb-2">Value (editable)</div>
              <input value={text} onChange={(e) => setText(e.target.value)}
                     className="w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 font-mono text-sm focus:border-human/50 focus:outline-none" />
            </div>
          )}
          {mode === "reject" && (
            <div>
              <div className="panel-title mb-2">Why? (sent back to the agent)</div>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} autoFocus
                        className="h-20 w-full resize-none rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm focus:border-risk/50 focus:outline-none"
                        placeholder="e.g. Wrong vendor - this belongs to Globex" />
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center justify-end gap-2 border-t border-white/[0.06] p-4">
        {mode === "reject" ? (
          <>
            <button className="btn-ghost" onClick={() => setMode("idle")}>Back</button>
            <button className="btn-danger" disabled={busy} onClick={() => send("reject")}>Reject action</button>
          </>
        ) : (
          <>
            <button className="btn-danger" onClick={() => setMode("reject")}>Reject…</button>
            <button className="btn-ok" disabled={busy} onClick={() => send(edited ? "edit" : "approve")}>
              {edited ? "Approve with edit" : "Approve"}
            </button>
          </>
        )}
      </div>
    </Overlay>
  );
}

export function QuestionDialog({ runId, event }: { runId: string; event: AtlasEvent }) {
  const d = event.data;
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const send = async (a: string) => {
    if (!a.trim()) return;
    setBusy(true);
    await api.respond(runId, { request_id: d.request_id, decision: "answer", answer: a }).catch(() => setBusy(false));
  };
  return (
    <Overlay>
      <div className="p-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-human/30 bg-human/10 text-human"><CircleHelp size={18} /></div>
          <div>
            <div className="panel-title">Atlas needs your input</div>
            <h2 className="mt-0.5 font-display text-lg font-semibold leading-snug">{d.question}</h2>
          </div>
        </div>
        {d.options?.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2">
            {d.options.map((o: string) => (
              <button key={o} disabled={busy} onClick={() => send(o)}
                      className="rounded-xl border border-human/30 bg-human/10 px-3 py-2 text-left text-sm text-ink-100 transition hover:bg-human/20">
                {o}
              </button>
            ))}
          </div>
        )}
        <div className="mt-5 flex gap-2">
          <input value={answer} onChange={(e) => setAnswer(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(answer)}
                 placeholder="Type an answer..." autoFocus
                 className="flex-1 rounded-xl border border-white/10 bg-ink-950 px-3 py-2 text-sm focus:border-human/50 focus:outline-none" />
          <button className="btn-primary" disabled={busy || !answer.trim()} onClick={() => send(answer)}><Send size={14} /> Send</button>
        </div>
      </div>
    </Overlay>
  );
}
