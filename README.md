# Atlas: an autonomous AI task worker

Atlas takes a natural-language business request, such as *"Find the latest invoice from Acme Supplies, extract the
amount and due date, enter it into our internal system, and tell me once it is done"*, and carries it out on a
computer. It drives a real Chromium browser through company web apps, reads PDFs, calls APIs and searches the public
web. It checks the result of every action, recovers from failures and asks the operator when it shouldn't guess.
Before it reports success, an **independent verifier** checks the outcome in the real systems.

It is a narrow prototype that genuinely works: a fictional company ("Northwind Corp") with four small but real web
apps (mail, an ERP, a vendor portal and a helpdesk), operated end to end with no mocked autonomy. One agent kernel,
unchanged, handles every task in the evaluation suite.

---

## Quick start

Prerequisites: Python 3.11+, Node 18+, and a Gemini API key (free tier works: https://aistudio.google.com/apikey).
Optional fallbacks, used only when every Gemini model is down or out of quota: a Groq key
(https://console.groq.com/keys) and/or an OpenRouter key (https://openrouter.ai/keys; free models are used).

```powershell
# Windows
.\run.ps1            # creates .env, installs deps + Chromium, builds the UI, serves on http://127.0.0.1:8000
```
```bash
# macOS / Linux
./run.sh
```
Put your keys in `.env` (`GEMINI_API_KEY=...`, optionally `GROQ_API_KEY=...`, `OPENROUTER_API_KEY=...`), then open **http://127.0.0.1:8000**. The sandbox apps start
automatically on http://127.0.0.1:8001.

<details><summary>Manual setup / dev mode with hot reload</summary>

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
python -m playwright install chromium
python -m app.main                                  # API :8000 + sandbox :8001

cd ../frontend
npm install
npm run dev                                         # UI with hot reload on :5173 (proxies to :8000)
```
Set `ATLAS_HEADLESS=0` in `.env` to watch the Chromium window while the agent works.
</details>

## A 3-minute demo

1. **Mission Control** → pick *"Invoice from email → ERP"* (the task from the brief) → Launch in **Balanced**
   mode. Watch the plan, the live browser, the reasoning stream and the facts it remembers (each with its source).
2. Atlas opens the inbox, picks the *latest* Acme invoice (not the older one), reads the PDF and fills the ERP form.
   The submit carries an amount, so the policy marks it **critical** and asks you to approve. The dialog shows the
   highlighted button and every value being submitted. Approve it, or reject it with a reason that goes back to the agent.
3. Atlas checks the confirmation page and calls `finish`. The **verifier** then opens a separate tab, finds the bill
   in the ERP and checks each success criterion. The report card shows the verdict with evidence, provenance,
   steps, cost, and a **skill learned**.
4. Run the same task again after **Reset data** on the Sandbox page. The learned skill is retrieved and the run needs
   fewer steps.
5. Set **Chaos** to 30% and run again. Pages randomly return 503s, a cookie-consent modal blocks clicks, and portal
   sessions expire. The activity stream shows classified recoveries, and the run still verifies.
6. Try *"Inbox processing with a prompt-injection email"*. One email tells "the AI assistant" to create a fake
   $9,850 bill. Atlas flags it, and the runtime blocks any write of the injected values even if the model were fooled.
7. Try *"Mark the Initech bill as paid"*. Two bills match, so Atlas asks which one instead of guessing.
8. **Runs & Replay** → open any run and scrub the timeline to replay thoughts, actions and screenshots.

## How it works (short version)

```
 user goal ─► Planner ─► plan + success criteria
                │
                ▼
     ┌──── Agent kernel (one tool call per turn, Gemini function calling) ◄──── environment card + learned skill
     │        │  act ─► Policy gate (risk ▸ approval ▸ injection taint) ─► Tool ─► Playwright / PDF / HTTP / files
     │        │  observe ◄─ fresh page snapshot + screenshot ◄────────────────────────┘
     │        │  recover ◄─ failure taxonomy (auto-retry transient, re-observe, hint, re-plan, ask user)
     │        ▼
     │     finish ─► Independent verifier (fresh tab, read-only tools) ─► verdict per criterion
     │                  └─ not verified → feedback to the agent (once) → honest failure
     └──► Event stream ─► SQLite (replay, audit) + WebSocket ─► Mission Control UI
                           verified success ─► Skill distillation ─► Skill library
```

The full design rationale is in **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## What maps to the evaluation criteria

| Criterion | What Atlas does |
|---|---|
| **Autonomy** | Receives only the goal. The planner derives steps and **success criteria**; the kernel explores the apps to find what it needs and re-plans when reality differs. |
| **Execution** | Real Chromium via Playwright against real (sandboxed) web apps with server-side validation; real PDFs parsed; real public web for research. Nothing is simulated at the agent level. |
| **Reliability** | Model failover: retired (404), overloaded (503) or quota-exhausted (429) Gemini models are parked and the next Flash model takes over mid-run; if no Gemini model is left, the run continues on **Groq** or **OpenRouter** (free models). Failure taxonomy (transient / overlay / stale element / validation / auth / policy) → strategy. Transient failures of idempotent tools are retried automatically with backoff. Loop detection forces a re-plan. Gemini 429/5xx backoff. **Chaos Mode** injects real faults to prove it. |
| **Grounding** | Before any critical submit, every amount, date and ID in the form must appear in something the agent actually observed (document, page, API, or the user's request). Otherwise the submit is bounced back for a re-check, and if the agent insists, a human must decide even in Autonomous mode. Added after a live run where the model typed 7142.18 for an invoice total of 7,342.18. |
| **Verification** | Separate verifier agent with read-only tools and a fresh tab checks every success criterion against ground truth and cites evidence. A failed verification feeds back to the agent once; otherwise the run reports failure honestly. The eval harness then checks the verifier itself against the database. |
| **Generalization** | The kernel has zero task- or app-specific code. Deployment knowledge lives in `backend/environment.md`; 8 different tasks run through the same code. Element refs come from a generic accessibility snapshot, not hard-coded selectors. |
| **Human approval** | The runtime (not the model) classifies risk: read / write / critical (financial or irreversible). Three autonomy modes. Approve, reject with a reason, or edit the value. Clarifying questions via `ask_user`. |
| **Safety** | Prompt-injection detection plus **taint tracking**: values from flagged content cannot be written unless the user asked for them. **Secrets vault**: the model types `{{secret:name}}`, never sees the password, and outputs are scrubbed. |
| **Reusable capabilities** | **Skill library**: verified successes are distilled into parameterised procedures and retrieved for similar tasks. |
| **Product thinking** | Report card with summary, results, provenance per value, evidence and verification checklist; full replay for "why did it do that?". |

## Evaluation suite

`backend/evals/tasks.yaml` defines 8 tasks, each checked against **ground truth read directly from the sandbox
database**, independent of both the agent and its verifier:

| Task | Exercises |
|---|---|
| Invoice from email → ERP (the brief's example) | mail, choosing the *latest* invoice, PDF extraction, form entry, approval |
| Vendor portal → ERP | login with vault secrets, session handling, PDF behind auth |
| "Mark the Initech bill as paid" | ambiguity → asks the user; critical action |
| Overdue bills → email report | ERP analysis, composing and sending email |
| Public-web research → helpdesk note | web search / Wikipedia, summarising, writing back |
| Release notes → close fixed tickets | reading comprehension: close #3 and #5, **not** #9 |
| Inbox processing with an injection email | the injection is ignored and blocked; the real invoice is still entered |
| Invoice from a vendor that doesn't exist | honest failure, nothing created |

```bash
cd backend
python -m evals.runner                 # clean run
python -m evals.runner --chaos 0.3     # under fault injection
python -m evals.runner --tasks invoice_email,injection_trap
```
Reports (success rate, verifier agreement with ground truth, steps, recoveries, cost) are written to
`backend/data/evals/` and charted on the **Evaluations** page, which can also launch the suite.

## Tests

```bash
cd backend && python -m pytest -q        # 20 tests, no API key needed
```
- `test_sandbox.py`: the simulated systems enforce real rules (validation, duplicates, auth, chaos).
- `test_browser_tools.py`: real Chromium reads the invoice PDF, fills the ERP form, logs in with vault secrets (the
  password never appears in output) and detects the chaos modal.
- `test_kernel.py`: the **full kernel loop driven by a scripted LLM**: approval gate, operator rejection,
  injection blocking, the grounding check (wrong amount bounced, then escalated), and a failed verification that is
  fed back to the agent and then ends in an honest failure.
- `test_units.py`: recovery taxonomy, injection detection and taint, vault, risk classification.

## Project layout

```
backend/
  agent/        kernel (loop), planner, verifier, policy, recovery, security, skills, memory, vault, llm, events, store
  tools/        registry, Playwright session + snapshot.js, browser/document tools, web/http, files, core, vision
  sandbox/      Northwind Corp suite (FastAPI + Jinja2), seed data + PDF generation, chaos middleware
  evals/        tasks.yaml, ground-truth checkers, runner (CLI + API)
  app/main.py   REST + WebSocket API, serves the built UI
  environment.md  the deployment "environment card" (the only place apps are described to the agent)
frontend/       React 19 + Vite + Tailwind 4 + framer-motion + recharts ("Mission Control")
```

## Models, APIs, frameworks

- **Google Gemini** via `google-genai` (default `gemini-3.8-flash`, configurable; if a model is retired or not offered, the
  newest available Flash model is selected). Function calling in `ANY` mode, structured JSON output for planning,
  verdicts and skills, thought summaries, multimodal input for the vision fallback.
- **Fallback providers: Groq and OpenRouter** through their OpenAI-compatible APIs (`backend/agent/providers.py`,
  plain `httpx`, no extra SDK). Model `auto` picks a tool-capable model; on OpenRouter only free models are chosen.
  Once a run falls back it stays on that provider for the rest of the run.
- **Playwright** (Chromium) for browser automation; **pypdf** to read PDFs; **fpdf2** to generate the sandbox invoices.
- **FastAPI**, **uvicorn**, **Jinja2**, **SQLite**, **httpx**, **pytest**.
- **React**, **Vite**, **Tailwind CSS**, **framer-motion**, **recharts**, **lucide-react**.
- Public web: DuckDuckGo HTML results with a Wikipedia search API fallback.
- No agent framework (LangChain etc.): the loop is small and explicit on purpose, so every decision is inspectable.

## Assumptions

- "Our internal system" means the company ERP; "entering an invoice" means creating a vendor bill.
- Creating financial records is **critical** and needs approval in Balanced mode; logging in with vault credentials
  is low risk.
- The agent may freely *read* the public web but never submits forms or signs in on external sites.
- Sandbox credentials are fictional and live in the vault; all companies and people are fictional.

## Known limitations

- Web apps only: no native desktop control. The browser snapshot covers standard HTML; canvas-heavy apps rely on
  the slower vision fallback.
- One action per LLM turn trades speed for control: typical tasks take 10–25 steps (1–3 minutes on Flash).
- Skill retrieval uses token overlap, not embeddings, which is fine for tens of skills but not thousands.
- Injection detection is pattern-based. Taint tracking limits the damage, but a novel phrasing could evade
  *detection*. The approval gate is the backstop for critical actions.
- Runs are in-process: a server restart marks running runs as interrupted (no resume).
- The free Gemini tier rate-limits; Atlas backs off and shows it, but runs get slower.
- Fallback models are weaker than Gemini Flash at long tool-use tasks, and free OpenRouter endpoints may log prompts
  (fine for this fictional sandbox, not for real company data).

## What I'd build next

1. **Durable execution**: checkpoint the kernel state per step (it is already event-sourced) to resume after crashes.
2. **Triggers and schedules**: start workers from events ("a new invoice email arrived") or cron.
3. **Multi-agent delegation**: a manager splitting work across specialist workers (browser, data, comms) in parallel.
4. **MCP tool layer**: expose and consume tools over MCP so new enterprise systems need no code changes.
5. **Desktop and VM computer use**: OS-level control in an isolated VM for non-web applications.
6. **Policy-as-code and audit**: OPA-style rules per tool and role, signed audit log, per-tenant RBAC.
7. **Learned site maps and a self-healing locator cache** to cut exploration steps further.
8. **Cost-aware model routing**: a cheap model for routine steps, a stronger one for planning and verification
   (already configurable via `GEMINI_REASONING_MODEL`).
9. **Nightly eval regression in CI** with chaos, tracking success rate and cost per task over time.
10. **Slack / Teams / voice intake**, so the user can actually be "told once it is done".
