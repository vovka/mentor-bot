# Mentor assistant bot — architecture

Status 2026-10-02: built, 143 tests, live-tested, running as a systemd user service.
Published page with the same diagrams: https://claude.ai/artifact/Kz2GVi8aQ5SpxxtQVg1HFD

## 1. What it is

```mermaid
flowchart LR
  You((you)) <-- Telegram chat --> BOT[mentor bot]
  BOT -- 08:00 brief --> You
  BOT -- pinned plan --> You
  BOT -- reports · files · approvals --> You
  BOT --> P1[(project-one/)]
  BOT --> P2[(project-two/)]
  BOT --> P3[(project-three/)]
  BOT -. subscriptions, no API keys .-> CX[codex exec]
  BOT -. secondary and coder .-> CL[claude -p]
```

## 2. How subscriptions reach the bot

```mermaid
flowchart LR
  subgraph ChatGPT["ChatGPT subscription (default)"]
    LOGIN["codex login"] --> AUTH["~/.codex/auth.json"] --> CX["codex exec"]
  end
  subgraph Claude["Claude subscription (secondary)"]
    ST["claude setup-token"] --> TOK["CLAUDE_CODE_OAUTH_TOKEN"]
    TOK --> CLI["claude -p"]
    TOK --> SDK["Claude Agent SDK"]
    TOK -. rejected .-> HTTP["anthropic HTTP SDK = API key only"]
  end
  CX & CLI & SDK --> BRAIN((Brain port))
```

Never `claude --bare` (ignores OAuth). No SDK for ChatGPT subscription: subprocess only.

## 3. Layers

```mermaid
flowchart TB
  subgraph app["app/ — wiring"]
    CFG[config.py env] --> CT[container.py] --> CLIa["cli.py: serve · job · doctor"]
    CT --> KK[kick.py]
  end
  subgraph adapters["adapters/ — all I/O"]
    TG[telegram/ api · markdown · fake]
    BR[brain/ router · codex_cli · claude_cli · fake]
    MAIL[mail/ imap]
    STO[store/ files · lock]
    SCH[scheduler/ inprocess]
    RND[render/ kroki · fake]
  end
  subgraph ports["ports/ — Protocols"]
    PC[Chat] --- PB[Brain] --- PS[Store] --- PK[Clock] --- PR[Renderer] --- PM[Mail]
  end
  subgraph usecases["usecases/ — one file per verb"]
    U1[handle_update] --> U2[handle_message]
    U2 --> U4[replan · scout · change_settings · add_project]
    U3[morning_checkin · reconcile · checkin · morning_brief · compact]
    U5[work · work_brain · work_result · task_buttons · task_update · apply_plan]
    U2 --> U5
  end
  subgraph domain["domain/ — no I/O"]
    D[Project · Task · Action · BrainTask · BrainResult · BrainSettings · Update]
  end
  app --> adapters
  adapters -- implement --> ports
  usecases -- use --> ports
  usecases & ports --> domain
```

Arrows point inward only. Telegram → Slack, files → S3, CLI → SDK = new adapter folder + one line in `container.py`.

## 4. A chat message

```mermaid
sequenceDiagram
  actor You
  participant TG as Telegram
  participant AD as telegram/api.py
  participant HU as handle_update
  participant HM as handle_message
  participant ST as store (data/)
  participant BR as brain (read-only)
  You->>TG: "move the demo to Friday"
  TG->>AD: getUpdates
  AD->>HU: update
  HU->>ST: lock · dedup update_id · append history/today.md
  HU->>HM: text, message_id
  HM->>TG: 👀 reaction · "typing…" every 4 s until reply
  HM->>ST: settings · summary.md · last 2 days · projects
  HM->>BR: prompt (gpt-5.5 low)
  BR-->>HM: {reply, document, actions:[replan]}
  HM->>TG: 🤔 reaction (heavy action started)
  HM->>BR: replan prompt (gpt-6-astra high)
  BR-->>HM: {document: new plan.md}
  HM->>ST: write plan.md · append reply
  HM->>AD: send(reply) · edit(pinned)
  AD->>TG: sendMessage · editMessageText · reaction cleared
  TG->>You: reply + updated pin
```

## 5. Brain: cheap chat, heavy planners, a write-enabled worker

```mermaid
flowchart TB
  U[chat message] --> C["chat brain · gpt-5.5 low · read-only"]
  C --> OUT["{reply, document, actions:[{kind,args}]}"]
  OUT -- replan --> P["replan.run · heavy settings<br/>document → plan.md → pin"]
  OUT -- scout --> S["scout.run · read-only over project repo_path"]
  OUT -- set_settings --> V{"change_settings.run<br/>valid vs ALLOWED?"}
  OUT -- add_project --> A{"add_project.run<br/>slug ok · repo_path exists?"}
  OUT -- send_image --> I["send_image.run<br/>Mermaid → Kroki PNG → sendPhoto"]
  OUT -- work --> WK["kick the worker<br/>reply: Working on the next task."]
  OUT -- task_update --> TU["task_update.run<br/>todo · done · dropped → refresh plan → kick"]
  V -- yes --> W1[settings.json]
  V -- no --> R1[reply: allowed list]
  A -- yes --> W2["data/projects/&lt;name&gt;/ from _template"]
  A -- no --> R2[reply: rejected]
  P & S & W1 & W2 & I & WK & TU --> RES[folded into reply]
```

Images: the brain never renders. It emits `send_image{diagram, caption}`; the use case posts the
PNG from Kroki (`KROKI_URL`, default kroki.io, self-hostable) and a failure lands in the reply text.

`task_result` is a worker-only kind. The chat prompt forbids it and `output_schema.json` lists all
eight kinds: replan, scout, set_settings, add_project, send_image, work, task_update, task_result.

### Routing

`RoutingBrain` picks the adapter from `BrainTask.settings.provider` and builds each one once;
an unknown provider returns `brain error: unknown provider`. Three tiers in `settings.json`
(`domain/settings.py` `tier`):

| Tier | Used for | Default |
|---|---|---|
| chat (top-level) | chat, scout, compact | gpt-5.5 low |
| `heavy` | replan, reconcile, `research` and `writing` tasks | gpt-6-astra high |
| `coder` | `coding` and `system` tasks | claude sonnet high |

A task can run on the other tier's provider when `task.provider` names it (the
"Approve · other provider" button sets this).

### Who writes files

```mermaid
flowchart LR
  BRAIN["chat / planner brain<br/>read-only"] -- "returns document" --> UC[use case] -- "writes" --> FS[(data/)]
  BRAIN -. never .-> FS
  WORKER["worker brain<br/>write=true"] -- "files, report" --> WD["work dir<br/>(coding: project repo + work dir)"]
```

Chat and planning stay read-only. Only the worker gets `write=True`, with `cwd` = its work dir
(the project repo for `coding` tasks, plus the work dir via `extra_dirs`).

| Provider | Read mode | Write mode (worker) |
|---|---|---|
| Codex | `-s read-only` | `-s workspace-write`, network on, `web_search=live`, `--add-dir` for extra dirs; kernel-sandboxed by bubblewrap |
| Claude | tools `Read,Grep` | tools `Read,Grep,Glob,Write,Edit,Bash,WebSearch,WebFetch`, `acceptEdits`; permission rules only, no kernel sandbox |

With `BROWSER_CDP_URL` set, write mode also attaches an MCP server named `browser`
(`@playwright/mcp` via `npx`, `--cdp-endpoint`) to both providers. Read-only browsing, "never
submit" and "never send" are prompt rules in `prompts/work.md` and `work_brain.py`, not enforced.

Why Codex read mode is read-only: `workspace-write` needs bubblewrap; Ubuntu 24.04 blocks
unprivileged userns. `deploy/apparmor-bwrap` (per-binary profile) lets shell commands run in the sandbox.

### One Codex call

```mermaid
flowchart LR
  T[BrainTask] --> CMD["codex exec -o TMP.json -m M -c model_reasoning_effort=E<br/>-s read-only | workspace-write -C CWD --ignore-user-config<br/>--output-schema prompts/output_schema.json -- PROMPT"]
  CMD -- "stdin closed · no timeout; streamed runs stall-guard at 60 min of silence" --> TMP[TMP.json]
  TMP --> R[BrainResult] --> DEL[TMP deleted]
  CMD -- "non-zero / stalled / cancelled" --> ERR["reply: brain error: <stderr tail>"]
```

Streaming: when `BrainTask.on_step` is set (worker, replan, scout), Codex adds `--json` (JSONL events on
stdout, `-o` still holds the answer) and Claude uses `--output-format stream-json --verbose` (the closing
`result` event is the json-mode output). `adapters/brain/stream.py` reads stdout line by line, enforces the
stall guard and cancel() (kill the process group) and maps tool calls to short lines ("ran `ls`", "edited a.txt").
Unknown or broken events are skipped. Without `on_step` the commands are unchanged.

`--ignore-user-config`: this machine's `~/.codex/config.toml` routes to a local proxy and MCP servers that hang headless.

### Allowed models (`domain/settings.py`)

```mermaid
flowchart LR
  subgraph codex
    A["gpt-5.5 · low..xhigh"]
    B["gpt-5.6-luna · low..max"]
    C["gpt-5.6-sol/terra · gpt-6-astra · low..ultra"]
    D["gpt-reserve · low..max"]
  end
  subgraph claude
    E["haiku · low..high"]
    F["sonnet · opus · fable · claude-opus-5-5 · low..max"]
  end
  CHAT[chat default] --> A
  HEAVY[heavy default] --> C
```

## 6. Task graph and work loop

`data/tasks.json` is the source of truth. `data/plan.md` and the pinned message are rendered
from it by `apply_plan.refresh` after every change (Next / In progress / Waiting on you / Failed /
Then / Done n of m). Replan and check-in Approve write the graph through `apply_plan.run`: parse,
reject cycles or unknown deps, then merge so runtime fields (`files`, `approved`, `provider`,
`proposal`) and non-final statuses survive. A running task missing from the new graph is kept.

Task: `id`, `title`, `project`, `kind` (`research` `writing` `coding` `system` `user`), `deps`,
`due`, `status`, `note`, plus runtime fields. The next task is the first `todo` in list order
whose deps are all `done` or `dropped`, so a parked, failed or awaiting task blocks its dependents.

### Statuses

```mermaid
stateDiagram-v2
  [*] --> todo: replan or check-in Approve
  todo --> running: worker claims it
  running --> done: outcome done
  running --> awaiting_approval: outcome needs_approval
  running --> awaiting_user: needs_user or a user task parked
  running --> failed: outcome failed or brain error
  running --> todo: worker restart resets a stale running
  awaiting_approval --> todo: button Approve or Approve other provider, approved set
  awaiting_approval --> awaiting_user: button Reject, note asks what instead
  awaiting_user --> done: button Done
  failed --> todo: chat task_update todo is retry
  todo --> done: chat task_update done or replan
  awaiting_user --> done: chat task_update done
  todo --> dropped: chat task_update dropped or replan
  done --> [*]
  dropped --> [*]
```

Chat `task_update` accepts only `todo`, `done`, `dropped` for any task id; replan may only set
those same three. Buttons are compare-and-set: a press on a task no longer in the expected
status answers "Already handled." Approve with another provider sets `task.provider`.

### One loop iteration

```mermaid
flowchart TB
  K["kick: button · work · task_update · replan · morning job<br/>or hourly timer"] --> LK{"data/.work.lock<br/>free?"}
  LK -- no --> EX["exit: work loop already running"]
  LK -- yes --> RS["reset stale running to todo"] --> CL
  CL["claim under data/.lock: first ready task"] --> RD{"ready task?"}
  RD -- none --> FIN
  RD -- yes --> UT{"kind = user?"}
  UT -- yes --> PK["park: awaiting_user<br/>send 'Your turn' + Done button<br/>no brain call, no budget"]
  UT -- no --> BG{"daily runs left?<br/>work.daily_runs"}
  BG -- no --> FIN
  BG -- yes --> BR["brain run in work dir<br/>tier by kind"]
  BR --> OC{"task_result outcome"}
  OC -- done --> T1["finalize progress message + files + email drafts"]
  OC -- needs_user --> T2["send report + files + drafts<br/>+ exact action + Done button"]
  OC -- needs_approval --> T3["send proposal<br/>Approve · Approve other provider · Reject"]
  OC -- "failed or missing" --> T4["progress message: Failed + reply"]
  T1 & T2 & T3 & T4 --> NX[next ready task]
  PK --> NX
  NX --> CL
  FIN["send 'Work loop finished' summary<br/>refresh plan.md and pin"]
```

Progress message (`usecases/progress.py`): each worker run, replan and scout posts one HTML message
(`Chat.send_html`) — `⏳ title`, `kind · provider model · effort E · elapsed`, the step log in a
`<blockquote>` — re-rendered every 10 s by a daemon thread (`edit_html`). On finish the same message
becomes `✅ Done` / `🟡 Prepared` / `🟠 Needs approval` / `❌ Failed`, total time, the log collapsed
(`<blockquote expandable>`) and, for worker tasks, the brief plus the files list; replan and scout end
with just the status and keep their usual reply. It stays under 4096 chars: older steps are counted as
"(N earlier steps in steps.md)", a long brief is cut with "…" (full text in `report.md`). Every step
is also appended with a timestamp to `steps.md` in the work dir. Telegram errors are printed, never raised.
Buttons, files and drafts follow as separate plain-text messages.

Details:

- Work dir: `data/projects/<name>/work/<task id>/` (`data/work/<id>/` without a project). Dependencies'
  `report.md` paths and files are listed in the prompt as inputs.
- A run that is not a `user` task costs one of `work.daily_runs` (default 12 per day, counted in
  `state.json` `work`). Past the budget the loop stops and says so.
- Files are sent only from the work dir or project repo, up to 50 MB each. Email drafts go to Gmail
  Drafts over IMAP (`adapters/mail/imap.py`, `Mail.draft`); with no mail configured, or on an
  IMAP error, the draft text is sent in Telegram instead. Nothing is ever sent as email.
- Single instance: `mentor job work` takes `data/.work.lock` non-blocking. Kicked runs
  (`app/kick.py`, detached subprocess) log to `data/work.log`.

## 7. Projects are folders

```mermaid
flowchart LR
  subgraph data/projects
    T[project-one/] ~~~ C[project-two/] ~~~ N[project-three/]
  end
  T & C & N --> F["project.md (repo: line)<br/>timeline.md · plan.md"]
  F --> DISC[Store.projects discovers folders at run time]
  DISC --> MB[morning brief merges items by date]
  DISC --> GP["data/plan.md → pinned message"]
  DISC --> SC["scout reads only that repo_path"]
  ADD["\"add project x at ~/dev/x\""] -- add_project --> N
```

## 8. Scheduler is the command line

```mermaid
flowchart LR
  CR[cron · deploy/crontab] --> J
  SD["systemd user timers ← running now<br/>mentor-{morning,deadline,replan,compact,work}.timer"] --> J
  IP["in-process thread<br/>mentor serve --with-scheduler"] --> J
  J["mentor job morning | deadline | replan | compact | work"] --> L[flock data/.lock]
  L --> ID{done today?<br/>state.json}
  ID -- yes --> NO[no-op]
  ID -- no --> RUN[use case] --> MARK[mark state.json]
  J -. "work: own lock data/.work.lock, no daily mark" .-> WL[work loop]
  RUN -. "morning · replan" .-> KK["kick: mentor job work in background"] -.-> WL
```

| Job | When (Europe/Kyiv) | Brain |
|---|---|---|
| morning check-in → brief | daily 08:00 | chat; heavy if reconciling |
| check-in deadline | daily 09:00 | heavy (reconcile) if still pending |
| replan | Sunday 20:00 | heavy settings |
| compact | Sunday 21:00 | chat settings |
| work | hourly safety net, plus kicks | `heavy` or `coder` per task kind |

The weekly replan and the morning job kick the worker when they finish. A chat replan, a button
press (other than Reject), the chat actions `work` and `task_update` kick it too. Check-in Approve
and the 09:00 deadline job do not kick; the next kick or the hourly timer picks the new tasks up.

### Morning check-in

```mermaid
flowchart TB
  M["08:00 morning_checkin"] --> W{user wrote since<br/>last brief?}
  W -- yes --> R
  W -- no --> Q["'No updates… not done?' [Yes] [No]<br/>checkin.stage = asked"]
  Q -- Yes --> R
  Q -- No --> AW["'send updates by 09:00'<br/>stage = awaiting_updates"]
  AW -- chat message --> R
  Q & AW -- "09:00 deadline job" --> R
  R["reconcile · heavy brain<br/>prompts/reconcile.md"] -- "document null" --> B[morning brief]
  R -- document --> P["proposal [Approve] [Reject]<br/>stage = proposed · plan.md untouched"]
  P -- Approve --> AP["apply_plan: tasks.json → plan.md · edit pin"] --> B
  P -- Reject --> RJ["'What should I change instead?'<br/>next message → normal chat"]
```

State lives in `state.json` `checkin`; each transition is claimed under `data/.lock`, so a button
and the 09:00 job never both act. A press on a stale stage or old message → "Already handled."

## 9. Memory

```mermaid
flowchart LR
  subgraph "every brain call"
    F[fresh session] --> CTX["summary.md + last 2 day files<br/>+ project list + task"]
  end
  CTX -.-> G["brain may Grep data/history/"]
  subgraph "weekly compact"
    OLD[days older than 14] --> CH[cheap brain] --> SUM[summary.md]
  end
  SUM --> CTX
  CHAT[each message + reply] --> DAY["history/YYYY-MM-DD.md<br/>append-only, written by store"]
```

```mermaid
flowchart TB
  NOW["now: Markdown + Read/Grep · zero code"] --> Q{Grep insufficient?}
  Q -- no --> NOW
  Q -- yes --> MCP["adapters/mcp/memory_server.py · stdio"]
  MCP --> C1[claude --mcp-config] & C2[codex mcp_servers] & C3[Agent SDK options]
```

## 10. Files

```
mentor/
  domain/      settings.py actions.py project.py conversation.py tasks.py
  usecases/    handle_update.py handle_message.py busy.py morning_brief.py replan.py
               scout.py compact.py change_settings.py add_project.py send_image.py
               morning_checkin.py checkin.py checkin_state.py reconcile.py
               apply_plan.py work.py work_brain.py work_result.py progress.py task_buttons.py task_update.py
  ports/       chat.py brain.py store.py clock.py renderer.py mail.py
  adapters/    telegram/{api,markdown,fake}.py  brain/{router,codex_cli,claude_cli,stream,fake}.py
               store/{files,lock}.py  scheduler/inprocess.py  render/{kroki,fake}.py  mail/imap.py
  app/         config.py container.py cli.py jobs.py kick.py
data/          tasks.json plan.md settings.json state.json work.log history/
               projects/{_template,<name>}/{...,work/<task id>/}
prompts/       mentor.md replan.md reconcile.md work.md scout.md morning.md compact.md output_schema.json
deploy/        crontab mentor.service mentor-*.{service,timer} (incl. mentor-work) apparmor-bwrap README.md
tests/         unit/ usecases/ e2e/     scripts/live_smoke.sh     Dockerfile compose.yml
```

| Change… | Where |
|---|---|
| personality, rules | `prompts/mentor.md` |
| a project's deadlines | `data/projects/<name>/timeline.md`, or tell the bot |
| chat / heavy model | tell the bot (`set_settings`) → `data/settings.json` |
| coder model, work budget | `data/settings.json` `coder`, `work.daily_runs` |
| what the worker may do alone | `prompts/work.md` (a prompt rule, not enforced) |
| task kinds, statuses, ordering | `domain/tasks.py` |
| a task's outcome handling, buttons | `usecases/work_result.py`, `task_buttons.py` |
| email drafts | `adapters/mail/imap.py`; `GMAIL_USER`, `GMAIL_APP_PASSWORD` |
| allowed models | `domain/settings.py` ALLOWED |
| when jobs run | active scheduler (`deploy/`) |
| Telegram → Slack | new `adapters/` folder + one line in `container.py` |

## 11. Config and secrets

```mermaid
flowchart LR
  ENV[".env (gitignored, 600)<br/>TELEGRAM_BOT_TOKEN · TELEGRAM_CHAT_ID · DATA_DIR · TZ · KROKI_URL<br/>GMAIL_USER · GMAIL_APP_PASSWORD"] --> CFG[app/config.py]
  OAUTH["CLAUDE_CODE_OAUTH_TOKEN (optional)"] --> CFG
  CDP["BROWSER_CDP_URL (optional)"] -. "read from os.environ by the brain adapters" .-> CT
  CODEX["~/.codex/auth.json"] --> CX[codex exec]
  CFG --> CT[container.py]
  ENV -. never .-> DATA[(data/ volume)]
```

## 12. Tests

```mermaid
flowchart LR
  subgraph "tests/ · 143 · no network"
    U[unit: settings · store · markdown] --> UC[usecases: fake brain + fake chat]
    UC --> E2E["e2e: Bot API stub (http.server) + fake brain<br/>full day: chat → settings → replan → morning → compact"]
  end
  E2E --> LIVE["scripts/live_smoke.sh · real Telegram + Codex<br/>6 steps, screenshots in tests/e2e/evidence/"]
```

## 13. Hosting now and later

```mermaid
flowchart LR
  subgraph now["now: one process, long-poll"]
    TG1[Telegram] <-- getUpdates --> P1["mentor serve<br/>systemd user unit · or Docker on a VM"]
    P1 --- V1[(data/)]
  end
  subgraph later["later: webhook ingress + worker"]
    TG2[Telegram] -- webhook --> ING["ingress fn (Vercel/Lambda)<br/>verify secret · dedup · ack"]
    ING --> Q[queue] --> WK["worker (VM / Lambda container)<br/>runs codex/claude"]
    WK --- V2[(S3 store)]
  end
```

Already in place for "later": `handle_update` is the single inbound entry, no memory between updates, `Store` is a port, config from env only.

```mermaid
flowchart TB
  subgraph compose.yml
    IMG["python:3.12-slim + node<br/>@anthropic-ai/claude-code · @openai/codex"] --> C["container · user 1000:1000<br/>mentor serve --with-scheduler"]
    C --- D["./data → /data"]
    C --- S["~/.codex → /secrets/codex (CODEX_HOME)"]
  end
```
