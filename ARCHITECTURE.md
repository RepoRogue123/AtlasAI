# Architecture & design decisions

This document explains how Atlas is built and, more importantly, *why*. File references are relative to `backend/`.

## 1. Guiding principles

1. **Do the work, don't describe it.** Every action hits a real system: a real browser, real HTTP, real PDFs. The
   sandbox apps are simple but enforce their own rules (validation, duplicate detection, auth, sessions), so the
   agent can fail in realistic ways.
2. **The runtime is the authority, not the model.** Risk classification, approvals, injection blocking, secret
   handling, retries and verification are deterministic code around the LLM. The model proposes; the runtime disposes.
3. **Done means verified.** The agent's own "I finished" is a claim. An independent component checks it.
4. **Generalise through observation, not special cases.** The kernel has no task- or app-specific branches. Moving
   to a new company means editing `environment.md` and the vault.
5. **Everything is an event.** One typed event stream drives the live UI, persistence, replay, evals and debugging.

## 2. Components

| Component | File | Responsibility |
|---|---|---|
| Kernel | `agent/kernel.py` | Plan → Act → Observe → Reflect loop, budgets, context building, finish/verify hand-off, report |
| Planner | `agent/planner.py` | Goal → understanding, high-level steps, **success criteria**, assumptions, ambiguities (structured JSON) |
| LLM adapter | `agent/llm.py` | Gemini function calling (`ANY` mode), JSON output, vision, backoff for 429/5xx, token + cost metering, model resolution |
| Tool registry | `tools/registry.py` | JSON-schema tools with static metadata (risk, idempotency, verifier-allowed); auto-adds a required `rationale` arg |
| Browser | `tools/browser.py`, `tools/snapshot.js` | Playwright session per run; DOM → compact text snapshot with numbered element refs; screenshots; document fetch |
| Policy | `agent/policy.py` | Runtime risk assessment (read / write / critical) and the autonomy-mode approval gate |
| Recovery | `agent/recovery.py` | Error → failure class → strategy / hint |
| Security | `agent/security.py`, `agent/vault.py` | Injection detection, taint tracking, secret substitution and scrubbing |
| Verifier | `agent/verifier.py` | Independent read-only agent producing a per-criterion verdict with evidence |
| Skills | `agent/skills.py` | Distil verified trajectories into reusable procedures; retrieve for similar goals |
| Memory | `agent/memory.py` | Working memory: facts with provenance (source, step, screenshot) |
| Events / store | `agent/events.py`, `agent/store.py` | Event bus with WebSocket fan-out; SQLite for runs, events, skills |
| Sandbox | `sandbox/` | Northwind Corp: mail, ERP, vendor portal, helpdesk; seed data; chaos middleware |
| Evals | `evals/` | Tasks + ground-truth checkers + runner with chaos and verifier-agreement metrics |

## 3. The loop

```
for step in 1..MAX_STEPS:
    reply   = LLM(system = persona + rules + environment card + live state, contents = compressed history)
    call    = first function call (exactly one action per turn)
    emit(action, rationale)
    loop-detection(call, page)                      -> runtime note + re-plan nudge
    risk    = policy.assess(call)                   -> inspects the real DOM element / form being submitted
    if taint(call): block                           -> injection guard
    if risk needs approval in this autonomy mode: await human (approve / edit / reject+reason)
    result  = execute with recovery                 -> auto-retry transient failures of idempotent tools
    scan result for injection, scrub secrets, emit observation
    if call == finish: verify -> (feedback once) -> report
```

**Why one action per turn?** After every action the agent sees the actual resulting state before deciding again.
That is slower than batching actions, but it makes behaviour observable, makes every decision explainable (each
call carries a rationale), and lets the policy gate inspect each action individually. For an AI *employee*, control
and auditability beat raw speed.

**Why `rationale` as a required argument instead of free text?** It is guaranteed to exist for every action and is
stored in the trace, which answers "why did the agent do that?" during review or debugging.

### Context management
- **System prompt rebuilt each turn**: rules, environment card, and a *state block* containing the plan with step
  statuses, the memory digest, flagged ambiguities, the skill hint, security notices and runtime notes (such as
  loop warnings).
- **History compression**: the last 3 tool results are kept verbatim; older observations are truncated. The memory
  digest preserves the important facts, so the model never needs an old page dump.
- **Observations are snapshots, not HTML**: `snapshot.js` walks the visible DOM and emits reading-order text with
  `[ref] role "label"` lines for interactive elements (labels resolved via `<label for>`, aria, placeholders).
  It is far smaller than raw HTML, robust to markup changes, and refs are re-assigned on every observation.
  Open modal dialogs are surfaced explicitly.
- Model content objects are replayed unchanged, which preserves Gemini thought signatures across turns.

## 4. Reliability: failure taxonomy

| Class | Typical cause | Strategy |
|---|---|---|
| `transient` | 5xx, timeouts, network | Idempotent tools: automatic retry with exponential backoff. Non-idempotent (submit): return to the model with "check whether it took effect before re-submitting" |
| `blocked_by_overlay` | modal / consent banner intercepts click | Attach a fresh observation; hint to dismiss the overlay |
| `element_not_found` | stale ref after page change | Attach a fresh observation with new refs |
| `validation` | rejected input (e.g. bad date format) | Hint to read the on-page error and fix the format |
| `auth` | session expired, redirected to login | Hint to sign in again with vault placeholders |
| `policy` / `rejected` | runtime block or operator rejection | Don't retry; choose another approach or ask |
| loop | same action on the same page ×3 | Runtime note forcing re-plan; recovery event |
| LLM | Gemini 429 / 5xx | Backoff honoring `retryDelay`; visible in the UI |

The ERP's duplicate detection plus the "check before re-submitting" hint makes retries of writes safe. That is
the same idempotency discipline a production worker needs.

**Chaos Mode** (`sandbox/chaos.py`) injects these failures for real: 503s before any work is done, 1.5–3.5 s
latency, blocking consent modals, and silent session expiry. Reliability is demonstrated rather than claimed, and
the eval runner compares clean and chaos runs.

### Grounding check (pre-commit verification)
`agent/grounding.py` indexes every amount, date and ID the agent has *observed* in pages, documents, API responses
and the user's request. Input values echoed back in snapshots and the runtime's own refusal messages are excluded,
so a value can't ground itself. Before a **critical** form submission, every such value in the form must be in the
index. The first violation bounces the submit back with a re-check hint. If the agent resubmits the same values,
the action is escalated to a human with a warning, regardless of autonomy mode. This came from a real failure in a
live run, where the model typed `7142.18` for an invoice whose total was `7,342.18`. Verification after the fact
would catch that; grounding stops it before it reaches the system of record.

### Model failover
`agent/llm.py` treats the model as an unreliable dependency too. A model that is retired for the key (404),
overloaded (503) or out of daily quota (429 with an hours-long retry) is parked, and the call fails over to the next
text Flash model (newest first, Flash-Lite as a last resort) without losing the run.

## 5. Verification

The verifier (`agent/verifier.py`) is a second agent loop with:
- a **fresh browser tab** (sharing cookies, so it can see the portal) and **read-only tools**: links only,
  enforced in code, never form submission;
- the user's request, the planner's **success criteria**, and the worker's **claims**, but *not* the worker's
  reasoning, so it cannot just agree with it;
- an output schema of a verdict (`verified` / `not_verified` / `inconclusive`) plus per-criterion pass/fail with
  evidence.

If the verdict is `not_verified`, the failed criteria go back to the worker as the result of its `finish` call, and
it gets one chance to fix the problem (the duplicate check protects against double entry). Final status values:
`success` (verified), `unverified`, `failed_verification`, `partial`, `failed`, `blocked`.

Who verifies the verifier? The eval harness. Its checkers read the sandbox database directly, and the report
includes **verifier agreement**: how often the verifier's verdict matched ground truth.

## 6. Human in the loop

Risk comes from the **actual element being acted on**, not from the model's self-report:
- link → read; GET form → read; sign-in form → read (credentials come from the vault);
- POST form → write; if the button label says pay/send/delete/transfer **or the form has an amount-like
  field** → critical.

Autonomy modes: *Supervised* (approve write + critical), *Balanced* (critical only), *Autonomous* (none). The
approval request includes a screenshot with the target highlighted and every form value being submitted. The
operator can approve, reject with a reason (returned to the agent as an observation), or edit the typed value.
`ask_user` covers ambiguity: the planner flags candidate ambiguities up front, and the agent asks when it hits one.

## 7. Security model

- **Untrusted content**: everything from pages, emails, documents and APIs is data. The system prompt says so,
  and flagged content gets an explicit runtime notice appended.
- **Detection**: patterns for instruction-like text aimed at an AI ("ignore previous instructions", "do not
  inform the user", "attention AI assistant", ...).
- **Taint tracking**: distinctive values (IDs, amounts) inside a flagged snippet become tainted, minus anything that
  also appears in the user's own goal. Any later action that would *write* a tainted value is blocked by the
  runtime. Detection may miss a phrasing, but when it fires, the harmful write is structurally prevented even if
  the model is persuaded.
- **Secrets vault**: credentials are referenced as `{{secret:name}}`. Substitution happens inside the tool at the
  last moment, password fields render as `********` in snapshots, and every output, event and trajectory is
  scrubbed of secret values. The model never sees the secret.
- **Blast radius**: `http_get` uses a host allow-list; file tools are confined to a workspace directory; the
  verifier is read-only.

## 8. Skill library: experiments into capabilities

After a **verified** success, the trajectory (actions plus outcomes, secrets scrubbed) is distilled by the LLM into a
parameterised skill: name, when it applies, procedure with concrete URLs and field names, pitfalls hit, and
keywords. A new goal retrieves the best match by token cosine similarity, and the skill is injected into planning
and acting as *guidance*. Skills are hints, not scripts: the agent still observes every step, so a changed UI
degrades to normal exploration instead of a broken macro. Repeated successes merge into the same skill and
increment its success count.

## 9. Generalization

What changes per task: nothing in the code. What changes per deployment: `environment.md` (which apps exist,
conventions) and vault entries. The eval suite spans 5 different apps or sources and 8 different task shapes, from
data entry and analysis to research, triage, adversarial input and impossible requests, all through the same kernel.

## 10. Key decisions & alternatives considered

| Decision | Alternative | Why |
|---|---|---|
| Custom ~440-line kernel | LangChain / LangGraph / browser-use | Full control of the loop, policy hooks and context; nothing hidden for the interview's "explain/debug/modify" |
| DOM snapshot with refs | Pure vision (screenshots + coordinates) | Cheaper, faster, exact text values; vision kept as a fallback tool (`look_at_screen`) |
| Simulated company apps | Real SaaS sandboxes | Deterministic, safe, resettable, no credentials. Still real HTTP and HTML with real validation, so execution is real |
| Gemini Flash | Larger model | Function calling plus thinking at low cost and latency; the model is configurable, with a separate model option for planning and verification |
| SQLite event store | Postgres / queue | Zero setup for reviewers. The event-sourced design maps directly onto a durable queue later |
| Runtime risk classification | Model self-declared risk | A model can be wrong or manipulated; the DOM can't lie about which form is being submitted |

## 11. Path to production

- Durable workflow engine (Temporal-style) over the existing event log; resumable runs.
- Per-run isolated browser containers or VMs; horizontal worker pool; queue-based scheduling.
- KMS-backed vault, OAuth connectors, per-tenant policy-as-code, signed audit trail.
- Embedding-based skill retrieval with versioning and canary evaluation of new skills.
- Continuous evaluation in CI (with chaos) as a release gate; per-task cost and success SLOs.
