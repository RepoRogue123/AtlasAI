import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import clsx from "clsx";
import { ArrowLeft, Pause, Play, Radio, Square, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { derive, useRunStream, type Shot } from "../lib/useRunStream";
import { fmtCost, fmtDuration, fmtTokens } from "../lib/format";
import ActivityFeed from "../components/ActivityFeed";
import LiveBrowser from "../components/LiveBrowser";
import PlanPanel from "../components/PlanPanel";
import MemoryPanel from "../components/MemoryPanel";
import ReportCard from "../components/ReportCard";
import { ApprovalDialog, QuestionDialog } from "../components/Dialogs";
import { Panel, Stat, StatusPill } from "../components/ui";

export default function RunView() {
  const { runId } = useParams();
  const { events, state: live } = useRunStream(runId);
  const [cursor, setCursor] = useState<number | null>(null);     // null = follow live
  const [playing, setPlaying] = useState(false);
  const [pinned, setPinned] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now() / 1000);

  const view = useMemo(() => (cursor === null ? live : derive(events.slice(0, cursor))), [cursor, events, live]);
  const shownEvents = cursor === null ? events : events.slice(0, cursor);
  const running = events.length > 0 && !live.report;
  const status = live.report ? live.report.status : live.pendingApproval || live.pendingQuestion ? "awaiting_human" : "running";

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, [running]);

  useEffect(() => {    // replay autoplay
    if (!playing) return;
    const t = setInterval(() => {
      setCursor((c) => {
        const next = (c ?? 0) + 1;
        if (next >= events.length) { setPlaying(false); return null; }
        return next;
      });
    }, 220);
    return () => clearInterval(t);
  }, [playing, events.length]);

  const shot: Shot | null = useMemo(() => {
    if (pinned) return view.shots.find((s) => s.url === pinned) ?? live.shots.find((s) => s.url === pinned) ?? null;
    return view.shots.at(-1) ?? null;
  }, [pinned, view.shots, live.shots]);

  const elapsed = live.startedAt ? (live.report ? live.report.duration_s : now - live.startedAt) : 0;
  const lastVerification = view.verifications.at(-1);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="border-b border-white/[0.06] bg-ink-950/60 px-6 py-4 backdrop-blur-xl">
        <div className="flex items-start gap-4">
          <Link to="/" className="mt-1 rounded-lg p-1 text-ink-400 hover:bg-white/5 hover:text-ink-100"><ArrowLeft size={18} /></Link>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={status} />
              {live.autonomy && <span className="chip border-white/10 text-ink-300">{live.autonomy}</span>}
              {live.model && <span className="chip border-white/10 text-ink-400">{live.model}</span>}
              {live.skillUsed && (
                <span className="chip border-signal/30 text-signal" title={live.skillUsed.summary}>
                  <Sparkles size={11} /> skill: {live.skillUsed.name}
                </span>
              )}
              {live.verifying && <span className="chip border-verified/30 text-verified animate-pulse">verifier checking…</span>}
            </div>
            <h1 className="mt-1.5 line-clamp-2 text-[15px] font-medium leading-snug text-ink-100">{live.goal || "Loading run…"}</h1>
          </div>
          <div className="hidden shrink-0 grid-cols-6 gap-6 lg:grid">
            <Stat label="Step" value={`${view.step}/${view.maxSteps}`} />
            <Stat label="Recoveries" value={view.recoveries} tone={view.recoveries ? "text-signal" : undefined} />
            <Stat label="LLM calls" value={view.usage.calls} />
            <Stat label="Tokens" value={fmtTokens(view.usage.input_tokens + view.usage.output_tokens + view.usage.thought_tokens)} />
            <Stat label="Cost" value={fmtCost(view.usage.cost_usd)} />
            <Stat label="Elapsed" value={fmtDuration(Math.max(0, elapsed))} />
          </div>
          {running && runId && (
            <button className="btn-danger shrink-0 px-3" onClick={() => api.cancel(runId)} title="Cancel run"><Square size={13} /> Stop</button>
          )}
        </div>
        {/* Replay scrubber */}
        {events.length > 1 && (
          <div className="mt-3 flex items-center gap-3">
            <button className="rounded-lg border border-white/10 p-1.5 text-ink-300 hover:text-ink-100"
                    onClick={() => { if (!playing && cursor === null) setCursor(1); setPlaying(!playing); setPinned(null); }}
                    title="Replay this run">
              {playing ? <Pause size={13} /> : <Play size={13} />}
            </button>
            <input type="range" min={1} max={events.length} value={cursor ?? events.length}
                   onChange={(e) => { setPlaying(false); setPinned(null); const v = +e.target.value; setCursor(v >= events.length ? null : v); }}
                   className="flex-1 accent-[#f5b544]" />
            <span className="w-28 text-right font-mono text-[11px] text-ink-400">
              {cursor === null ? "live" : `event ${cursor}/${events.length}`}
            </span>
            <button onClick={() => { setCursor(null); setPlaying(false); setPinned(null); }}
                    className={clsx("chip py-1", cursor === null ? "border-signal/40 text-signal" : "border-white/10 text-ink-400 hover:text-ink-100")}>
              <Radio size={11} /> {running ? "Live" : "End"}
            </button>
          </div>
        )}
      </header>

      {/* Body */}
      <div className="grid min-h-0 flex-1 grid-cols-[290px_minmax(0,1fr)_400px] gap-4 p-4">
        <div className="flex min-h-0 flex-col gap-4">
          <div className="flex min-h-0 flex-[1.3] flex-col"><PlanPanel plan={view.plan} verification={lastVerification} /></div>
          <div className="flex min-h-0 flex-1 flex-col">
            <MemoryPanel facts={view.facts} security={view.security} onShot={(u) => setPinned(u)} />
          </div>
        </div>
        <div className="flex min-h-0 flex-col gap-4 overflow-y-auto scroll-thin">
          {live.report && cursor === null && <div className="shrink-0"><ReportCard report={live.report} onShot={(u) => setPinned(u)} /></div>}
          {live.error && !live.report && <div className="rounded-xl border border-risk/30 bg-risk/10 px-4 py-2 text-sm text-risk">{live.error}</div>}
          <div className="flex min-h-[460px] flex-1 flex-col">
            <LiveBrowser shot={shot} shots={view.shots} onPick={(s) => setPinned(s.url)} live={running && cursor === null} />
          </div>
        </div>
        <Panel title="Agent activity" right={<span className="font-mono text-[10.5px] text-ink-400">{shownEvents.length} events</span>} bodyClass="p-0">
          <ActivityFeed events={shownEvents} follow={cursor === null} />
        </Panel>
      </div>

      <AnimatePresence>
        {cursor === null && runId && live.pendingApproval && <ApprovalDialog key={live.pendingApproval.seq} runId={runId} event={live.pendingApproval} />}
        {cursor === null && runId && live.pendingQuestion && <QuestionDialog key={live.pendingQuestion.seq} runId={runId} event={live.pendingQuestion} />}
      </AnimatePresence>
    </div>
  );
}
