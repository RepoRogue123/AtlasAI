import { useEffect, useMemo, useRef, useState } from "react";
import { wsUrl, type AtlasEvent, type Plan, type Report, type Verification } from "./api";

export type Shot = { seq: number; url: string; page_url: string; tag: string; step: number; actor: string; target?: string };
export type Fact = { key: string; value: string; source: string; step: number; screenshot?: string };

export type RunState = {
  goal: string;
  autonomy: string;
  model: string;
  plan: Plan | null;
  planVersions: number;
  facts: Fact[];
  shots: Shot[];
  usage: { calls: number; input_tokens: number; output_tokens: number; thought_tokens: number; cost_usd: number };
  step: number;
  maxSteps: number;
  retries: number;
  recoveries: number;
  security: AtlasEvent[];
  pendingApproval: AtlasEvent | null;
  pendingQuestion: AtlasEvent | null;
  verifying: boolean;
  verifications: Verification[];
  skillUsed: { id: number; name: string; score: number; summary: string } | null;
  skillLearned: { id: number; name: string; merged: boolean; summary: string } | null;
  report: Report | null;
  error: string | null;
  startedAt: number | null;
  lastTs: number | null;
};

const EMPTY_USAGE = { calls: 0, input_tokens: 0, output_tokens: 0, thought_tokens: 0, cost_usd: 0 };

/** Fold the event log into a view model. Pure, so replay = derive(events.slice(0, n)). */
export function derive(events: AtlasEvent[]): RunState {
  const s: RunState = {
    goal: "", autonomy: "", model: "", plan: null, planVersions: 0, facts: [], shots: [], usage: EMPTY_USAGE,
    step: 0, maxSteps: 40, retries: 0, recoveries: 0, security: [], pendingApproval: null, pendingQuestion: null,
    verifying: false, verifications: [], skillUsed: null, skillLearned: null, report: null, error: null,
    startedAt: null, lastTs: null,
  };
  const facts = new Map<string, Fact>();
  for (const e of events) {
    const d = e.data;
    s.lastTs = e.ts;
    switch (e.type) {
      case "run_started": s.goal = d.goal; s.autonomy = d.autonomy; s.maxSteps = d.max_steps; s.startedAt = e.ts; break;
      case "model": s.model = d.model; break;
      case "plan": s.plan = d; s.planVersions += 1; break;
      case "usage": s.usage = d; break;
      case "action": s.step = Math.max(s.step, d.step ?? 0); break;
      case "screenshot": s.shots.push({ seq: e.seq, ...d }); break;
      case "memory": facts.set(d.key, d); break;
      case "recovery": s.recoveries += 1; if (d.kind === "transient" || d.kind === "llm_backoff") s.retries += 1; break;
      case "security": s.security.push(e); break;
      case "approval_requested": s.pendingApproval = e; break;
      case "approval_resolved": if (s.pendingApproval?.data.request_id === d.request_id) s.pendingApproval = null; break;
      case "question_requested": s.pendingQuestion = e; break;
      case "question_resolved": if (s.pendingQuestion?.data.request_id === d.request_id) s.pendingQuestion = null; break;
      case "verification_started": s.verifying = true; break;
      case "verification": s.verifying = false; s.verifications.push(d); break;
      case "skill_used": s.skillUsed = d; break;
      case "skill_learned": s.skillLearned = d; break;
      case "error": s.error = d.message; break;
      case "run_finished": s.report = d; s.verifying = false; s.pendingApproval = null; s.pendingQuestion = null; break;
    }
  }
  s.facts = [...facts.values()];
  return s;
}

export function useRunStream(runId: string | undefined) {
  const [events, setEvents] = useState<AtlasEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const seen = useRef(new Set<number>());

  useEffect(() => {
    if (!runId) return;
    setEvents([]);
    seen.current = new Set();
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;
    const connect = () => {
      ws = new WebSocket(wsUrl(`/ws/runs/${runId}`));
      ws.onopen = () => setConnected(true);
      ws.onmessage = (m) => {
        const ev = JSON.parse(m.data) as AtlasEvent;
        if (seen.current.has(ev.seq)) return;
        seen.current.add(ev.seq);
        setEvents((prev) => [...prev, ev]);
      };
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); ws?.close(); };
  }, [runId]);

  const state = useMemo(() => derive(events), [events]);
  return { events, state, connected };
}
