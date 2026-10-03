import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import {
  AlertTriangle, Brain, CheckCircle2, ChevronDown, CircleHelp, FileText, Flag, Globe, Hand, ListChecks, Lock,
  Search, ShieldAlert, ShieldCheck, Sparkles, Wrench, XCircle, Zap,
} from "lucide-react";
import type { AtlasEvent } from "../lib/api";

const HIDDEN = new Set(["usage", "screenshot", "model", "run_started", "http", "verification_started"]);

function argSummary(tool: string, args: Record<string, any>) {
  if (!args) return "";
  if (tool === "browser_goto" || tool === "read_document" || tool === "http_get") return args.url;
  if (tool === "browser_click") return `[${args.ref}]`;
  if (tool === "browser_type") return `[${args.ref}] ← "${args.text}"${args.submit ? " ⏎" : ""}`;
  if (tool === "browser_select") return `[${args.ref}] ← ${args.option}`;
  if (tool === "remember") return `${args.key} = ${args.value}`;
  if (tool === "web_search") return `"${args.query}"`;
  if (tool === "ask_user") return args.question;
  if (tool === "finish") return args.outcome;
  if (tool === "update_plan") return `${args.steps?.length ?? 0} steps`;
  return Object.keys(args).length ? JSON.stringify(args).slice(0, 120) : "";
}

function Row({ icon, tone, title, children, actor }: {
  icon: React.ReactNode; tone: string; title: React.ReactNode; children?: React.ReactNode; actor?: string;
}) {
  return (
    <div className="group relative flex gap-3 py-1.5">
      <div className={clsx("mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border", tone)}>{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-[13px] leading-6">
          {title}
          {actor === "verifier" && <span className="chip border-verified/30 text-verified">verifier</span>}
        </div>
        {children && <div className="text-xs leading-relaxed text-ink-300">{children}</div>}
      </div>
    </div>
  );
}

function Expandable({ text, lines = 3 }: { text: string; lines?: number }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 220;
  return (
    <div>
      <pre className={clsx("whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-ink-400",
                           !open && long && (lines === 2 ? "line-clamp-2" : "line-clamp-3"))}>{text}</pre>
      {long && (
        <button onClick={() => setOpen(!open)} className="mt-0.5 flex items-center gap-1 text-[11px] text-ink-400 hover:text-ink-100">
          <ChevronDown size={12} className={clsx("transition", open && "rotate-180")} /> {open ? "less" : "more"}
        </button>
      )}
    </div>
  );
}

const T = {
  signal: "border-signal/30 bg-signal/10 text-signal",
  info: "border-info/30 bg-info/10 text-info",
  ok: "border-verified/30 bg-verified/10 text-verified",
  risk: "border-risk/30 bg-risk/10 text-risk",
  human: "border-human/30 bg-human/10 text-human",
  muted: "border-white/10 bg-white/5 text-ink-300",
};

export function EventRow({ e }: { e: AtlasEvent }) {
  const d = e.data;
  switch (e.type) {
    case "thought":
      return <Row icon={<Brain size={13} />} tone={T.muted} title={<span className="text-ink-400">Thinking</span>}>
        <Expandable text={d.text} lines={2} />
      </Row>;
    case "action":
    case "verifier_action":
      return <Row actor={e.type === "verifier_action" ? "verifier" : undefined} icon={<Zap size={13} />}
                  tone={e.type === "verifier_action" ? T.ok : T.signal}
                  title={<><span className="font-mono text-[12px] font-semibold text-signal">{d.tool}</span>
                    <span className="truncate font-mono text-[11.5px] text-ink-300">{argSummary(d.tool, d.args)}</span></>}>
        {d.rationale && <span className="italic text-ink-400">“{d.rationale}”</span>}
      </Row>;
    case "risk":
      return <Row icon={<AlertTriangle size={13} />} tone={d.risk === "critical" ? T.risk : T.signal}
                  title={<span>Risk: <b className="uppercase">{d.risk}</b></span>}>{d.reason}</Row>;
    case "observation":
      return d.ok
        ? <Row icon={<CheckCircle2 size={13} />} tone={T.info} title={<span className="text-ink-300">{d.data?.title || "Observed"}</span>}>
            <Expandable text={d.text} />
          </Row>
        : <Row icon={<XCircle size={13} />} tone={T.risk}
               title={<span className="text-risk">Failed <span className="chip ml-1 border-risk/30">{d.error_kind}</span></span>}>
            <Expandable text={d.text} />
          </Row>;
    case "recovery":
      return <Row icon={<Wrench size={13} />} tone={T.signal}
                  title={<span>Recovery · <span className="font-mono text-[12px] text-signal">{d.kind}</span>{d.attempt ? ` #${d.attempt}` : ""}</span>}>
        {d.strategy}
      </Row>;
    case "security":
      return <Row icon={d.kind === "blocked" ? <Lock size={13} /> : <ShieldAlert size={13} />} tone={T.risk}
                  title={<span className="font-semibold text-risk">{d.kind === "blocked" ? "Action blocked by injection guard" : "Prompt injection detected"}</span>}>
        {d.message ?? <Expandable text={d.snippet ?? ""} lines={2} />}
        {d.tainted?.length > 0 && <div className="mt-1 flex flex-wrap gap-1">{d.tainted.map((t: string) =>
          <span key={t} className="chip border-risk/30 text-risk">tainted {t}</span>)}</div>}
      </Row>;
    case "approval_requested":
      return <Row icon={<Hand size={13} />} tone={T.human} title={<span className="text-human">Approval requested</span>}>
        {d.reason}{d.target && <> · “{d.target}”</>}
      </Row>;
    case "approval_resolved":
      return <Row icon={<Hand size={13} />} tone={d.decision === "reject" ? T.risk : T.ok}
                  title={<span>Operator {d.decision === "reject" ? "rejected" : d.decision === "edit" ? "edited & approved" : "approved"}</span>}>
        {d.reason}
      </Row>;
    case "question_requested":
      return <Row icon={<CircleHelp size={13} />} tone={T.human} title={<span className="text-human">Atlas asks</span>}>{d.question}</Row>;
    case "question_resolved":
      return <Row icon={<CircleHelp size={13} />} tone={T.ok} title="You answered">{d.answer ?? d.reason}</Row>;
    case "memory":
      return <Row icon={<ListChecks size={13} />} tone={T.ok}
                  title={<span>Remembered <span className="font-mono text-[12px]">{d.key}</span></span>}>
        <span className="font-semibold text-ink-100">{d.value}</span> <span className="text-ink-400">· {d.source}</span>
      </Row>;
    case "document":
      return <Row icon={<FileText size={13} />} tone={T.info} title="Read document">
        <span className="font-mono text-[11px]">{d.url}</span> · {d.content_type} · {d.chars} chars
      </Row>;
    case "search":
      return <Row icon={<Search size={13} />} tone={T.info} title={<>Web search <span className="font-mono text-[12px]">“{d.query}”</span></>}>
        {d.results?.length ?? 0} results
      </Row>;
    case "file":
      return <Row icon={<FileText size={13} />} tone={T.info} title="Wrote file">{d.path}</Row>;
    case "plan":
      return d.replanned
        ? <Row icon={<ListChecks size={13} />} tone={T.signal} title={<span>Re-planned <span className="chip ml-1 border-signal/30 text-signal">v{d.version + 1}</span></span>} />
        : d.version === 0 && !d.replanned && e.seq < 8
          ? <Row icon={<ListChecks size={13} />} tone={T.signal} title="Plan created">{d.steps?.length} steps · {d.success_criteria?.length} success criteria</Row>
          : null;
    case "verification":
      return <Row icon={<ShieldCheck size={13} />} tone={d.verdict === "verified" ? T.ok : T.risk}
                  title={<span className={d.verdict === "verified" ? "text-verified" : "text-risk"}>Verifier verdict: {d.verdict}</span>}>
        {d.notes}
      </Row>;
    case "skill_used":
      return <Row icon={<Sparkles size={13} />} tone={T.signal} title={<>Using skill <span className="font-mono text-[12px]">{d.name}</span></>}>{d.summary}</Row>;
    case "skill_learned":
      return <Row icon={<Sparkles size={13} />} tone={T.ok} title={<>{d.merged ? "Refined" : "Learned"} skill <span className="font-mono text-[12px]">{d.name}</span></>}>{d.summary}</Row>;
    case "error":
      return <Row icon={<XCircle size={13} />} tone={T.risk} title={<span className="text-risk">Error</span>}>{d.message}</Row>;
    case "run_finished":
      return <Row icon={<Flag size={13} />} tone={d.status === "success" ? T.ok : T.muted} title={<b>Run finished · {d.status}</b>} />;
    default:
      return <Row icon={<Globe size={13} />} tone={T.muted} title={e.type} />;
  }
}

export default function ActivityFeed({ events, follow }: { events: AtlasEvent[]; follow: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const visible = events.filter((e) => !HIDDEN.has(e.type));
  useEffect(() => {
    const el = ref.current;
    if (!el || !follow) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 240) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [visible.length, follow]);

  let lastStep = -1;
  return (
    <div ref={ref} className="h-full overflow-y-auto px-4 py-2 scroll-thin">
      {visible.map((e) => {
        const step = e.data?.step;
        const header = typeof step === "number" && step > 0 && step !== lastStep && e.type === "action";
        if (header) lastStep = step;
        return (
          <div key={e.seq}>
            {header && (
              <div className="sticky top-0 z-10 -mx-4 mb-1 mt-2 bg-ink-900/95 px-4 py-1 font-mono text-[10px] uppercase tracking-[0.2em] text-ink-400 backdrop-blur">
                Step {step}
              </div>
            )}
            <EventRow e={e} />
          </div>
        );
      })}
    </div>
  );
}
