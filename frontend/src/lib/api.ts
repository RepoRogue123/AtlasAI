export type AtlasEvent = { run_id: string; seq: number; ts: number; type: string; data: any };

export type PlanStep = { title: string; status: string };
export type Plan = {
  understanding: string;
  steps: PlanStep[];
  success_criteria: string[];
  assumptions: string[];
  ambiguities: string[];
  version: number;
};

export type Criterion = { criterion: string; passed: boolean; evidence: string };
export type Verification = { verdict: string; criteria: Criterion[]; notes: string; steps?: number; attempt?: number };

export type Report = {
  status: string;
  outcome: string;
  summary: string;
  results: { label: string; value: string }[];
  evidence: string[];
  verification: Verification | null;
  facts: { key: string; value: string; source: string; step: number; screenshot?: string }[];
  security: { source: string; snippet: string; tainted: string[] }[];
  steps: number;
  retries: number;
  failures: number;
  usage: { calls: number; input_tokens: number; output_tokens: number; thought_tokens: number; cost_usd: number };
  duration_s: number;
  skill_used: { id: number; name: string } | null;
  skill_learned: { id: number; name: string; merged: boolean } | null;
  final_screenshot?: string | null;
};

export type RunRow = {
  id: string;
  goal: string;
  autonomy: string;
  status: string;
  created_at: number;
  finished_at: number | null;
  report: Report | null;
  source: string;
};

export type Skill = {
  id: number;
  name: string;
  summary: string;
  applies_when: string;
  procedure: string[];
  pitfalls: string[];
  keywords: string[];
  uses: number;
  successes: number;
  source_run: string;
  updated_at: number;
};

export type Example = { id: string; title: string; goal: string; tags: string[] };

export type EvalTask = {
  id: string; title: string; run_id?: string; passed: boolean; detail: string; agent_status?: string;
  verifier?: string; steps?: number; retries?: number; cost_usd?: number; duration_s?: number;
  injections_detected?: number; recoveries?: number;
};
export type EvalReport = {
  id: string; created_at: number; chaos: number; model: string; tasks: EvalTask[]; passed: number; total: number;
  success_rate: number; verifier_agreement: number | null; avg_steps: number; total_cost_usd: number; duration_s: number;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean; gemini_key: boolean; llm_ready: boolean; model: string | null; fallbacks: string[]; sandbox: boolean; sandbox_url: string }>("/api/health"),
  examples: () => req<Example[]>("/api/examples"),
  startRun: (goal: string, autonomy: string, use_skills = true) =>
    req<{ run_id: string }>("/api/runs", { method: "POST", body: JSON.stringify({ goal, autonomy, use_skills }) }),
  runs: () => req<RunRow[]>("/api/runs"),
  run: (id: string) => req<RunRow & { events: AtlasEvent[] }>(`/api/runs/${id}`),
  respond: (id: string, body: Record<string, unknown>) =>
    req(`/api/runs/${id}/respond`, { method: "POST", body: JSON.stringify(body) }),
  cancel: (id: string) => req(`/api/runs/${id}/cancel`, { method: "POST" }),
  skills: () => req<Skill[]>("/api/skills"),
  deleteSkill: (id: number) => req(`/api/skills/${id}`, { method: "DELETE" }),
  chaos: () => req<{ level: number; log: { ts: number; fault: string; method: string; path: string }[] }>("/api/sandbox/chaos"),
  setChaos: (level: number) => req("/api/sandbox/chaos", { method: "POST", body: JSON.stringify({ level }) }),
  resetSandbox: () => req("/api/sandbox/reset", { method: "POST" }),
  sandboxState: () => req<any>("/api/sandbox/state"),
  evals: () => req<EvalReport[]>("/api/evals"),
  evalStatus: () => req<{ running: boolean; total?: number; done?: number; current?: string | null; chaos?: number }>("/api/evals/status"),
  runEvals: (chaos: number, tasks?: string[]) =>
    req("/api/evals/run", { method: "POST", body: JSON.stringify({ chaos, tasks }) }),
};

export function wsUrl(path: string) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}`;
}
