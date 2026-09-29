# Mentor bot — architecture

Status 2026-09-29: built, 47 tests, live-tested, running as a systemd user service.
Published page with the same diagrams: https://claude.ai/artifact/Kz2GVi8aQ5SpxxtQVg1HFD

## 1. What it is

```mermaid
flowchart LR
  You((you)) <-- Telegram chat --> BOT[mentor bot]
  BOT -- 08:00 brief --> You
  BOT -- pinned plan --> You
  BOT --> P1[(tusk/)]
  BOT --> P2[(campaignloop/)]
  BOT --> P3[(new-project/)]
  BOT -. subscriptions, no API keys .-> CX[codex exec]
  BOT -. secondary .-> CL[claude -p]
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
  end
  subgraph adapters["adapters/ — all I/O"]
    TG[telegram/ api · markdown · fake]
    BR[brain/ codex_cli · claude_cli · fake]
    STO[store/ files · lock]
    SCH[scheduler/ inprocess]
    RND[render/ kroki · fake]
  end
  subgraph ports["ports/ — Protocols"]
    PC[Chat] --- PB[Brain] --- PS[Store] --- PK[Clock] --- PR[Renderer]
  end
  subgraph usecases["usecases/ — one file per verb"]
    U1[handle_update] --> U2[handle_message]
    U2 --> U4[replan · scout · change_settings · add_project]
    U3[morning_brief · compact]
  end
  subgraph domain["domain/ — no I/O"]
    D[Project · Action · BrainTask · BrainResult · BrainSettings · Update]
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

## 5. Brain: cheap chat, heavy workers, code executes

```mermaid
flowchart TB
  U[chat message] --> C["chat brain · gpt-5.5 low · read-only"]
  C --> OUT["{reply, document, actions:[{kind,args}]}"]
  OUT -- replan --> P["replan.run · heavy settings<br/>document → plan.md → pin"]
  OUT -- scout --> S["scout.run · read-only over project repo_path"]
  OUT -- set_settings --> V{"change_settings.run<br/>valid vs ALLOWED?"}
  OUT -- add_project --> A{"add_project.run<br/>slug ok · repo_path exists?"}
  OUT -- send_image --> I["send_image.run<br/>Mermaid → Kroki PNG → sendPhoto"]
  V -- yes --> W1[settings.json]
  V -- no --> R1[reply: allowed list]
  A -- yes --> W2["data/projects/&lt;name&gt;/ from _template"]
  A -- no --> R2[reply: rejected]
  P & S & W1 & W2 & I --> RES[folded into reply]
```

Images: the brain never renders. It emits `send_image{diagram, caption}`; the use case posts the
PNG from Kroki (`KROKI_URL`, default kroki.io, self-hostable) and a failure lands in the reply text.

### Who writes files

```mermaid
flowchart LR
  BRAIN["brain (codex / claude)"] -- "returns document" --> UC[use case] -- "writes" --> FS[(data/)]
  BRAIN -. never .-> FS
  FS -. "Read / Grep only" .-> BRAIN
```

Why: Codex `workspace-write` needs bubblewrap; Ubuntu 24.04 blocks unprivileged userns.
`deploy/apparmor-bwrap` (per-binary profile) lets shell commands run in the read-only sandbox.

### One Codex call

```mermaid
flowchart LR
  T[BrainTask] --> CMD["codex exec -o TMP.json -m M -c model_reasoning_effort=E<br/>-s read-only -C CWD --ignore-user-config<br/>--output-schema prompts/output_schema.json -- PROMPT"]
  CMD -- "stdin closed · 180 s timeout" --> TMP[TMP.json]
  TMP --> R[BrainResult] --> DEL[TMP deleted]
  CMD -- "non-zero / timeout" --> ERR["reply: brain error: <stderr tail>"]
```

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

## 6. Projects are folders

```mermaid
flowchart LR
  subgraph data/projects
    T[tusk/] ~~~ C[campaignloop/] ~~~ N[new-project/]
  end
  T & C & N --> F["project.md (repo: line)<br/>timeline.md · plan.md"]
  F --> DISC[Store.projects discovers folders at run time]
  DISC --> MB[morning brief merges items by date]
  DISC --> GP["data/plan.md → pinned message"]
  DISC --> SC["scout reads only that repo_path"]
  ADD["\"add project x at ~/dev/x\""] -- add_project --> N
```

## 7. Scheduler is the command line

```mermaid
flowchart LR
  CR[cron · deploy/crontab] --> J
  SD["systemd user timers ← running now<br/>mentor-{morning,replan,compact}.timer"] --> J
  IP["in-process thread<br/>mentor serve --with-scheduler"] --> J
  J["mentor job morning | replan | compact"] --> L[flock data/.lock]
  L --> ID{done today?<br/>state.json}
  ID -- yes --> NO[no-op]
  ID -- no --> RUN[use case] --> MARK[mark state.json]
```

| Job | When (Europe/Kyiv) | Brain |
|---|---|---|
| morning brief | daily 08:00 | chat settings |
| replan | Sunday 20:00 | heavy settings |
| compact | Sunday 21:00 | chat settings |

## 8. Memory

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

## 9. Files

```
mentor/
  domain/      settings.py actions.py project.py conversation.py
  usecases/    handle_update.py handle_message.py busy.py morning_brief.py replan.py
               scout.py compact.py change_settings.py add_project.py send_image.py
  ports/       chat.py brain.py store.py clock.py renderer.py
  adapters/    telegram/{api,markdown,fake}.py  brain/{codex_cli,claude_cli,fake}.py
               store/{files,lock}.py  scheduler/inprocess.py  render/{kroki,fake}.py
  app/         config.py container.py cli.py jobs.py
data/          plan.md settings.json state.json history/ projects/{_template,<name>}/
prompts/       mentor.md replan.md scout.md morning.md compact.md output_schema.json
deploy/        crontab mentor.service mentor-*.{service,timer} apparmor-bwrap README.md
tests/         unit/ usecases/ e2e/     scripts/live_smoke.sh     Dockerfile compose.yml
```

| Change… | Where |
|---|---|
| personality, rules | `prompts/mentor.md` |
| a project's deadlines | `data/projects/<name>/timeline.md`, or tell the bot |
| chat / heavy model | tell the bot (`set_settings`) → `data/settings.json` |
| allowed models | `domain/settings.py` ALLOWED |
| when jobs run | active scheduler (`deploy/`) |
| Telegram → Slack | new `adapters/` folder + one line in `container.py` |

## 10. Config and secrets

```mermaid
flowchart LR
  ENV[".env (gitignored, 600)<br/>TELEGRAM_BOT_TOKEN · TELEGRAM_CHAT_ID · DATA_DIR · TZ · KROKI_URL"] --> CFG[app/config.py]
  OAUTH["CLAUDE_CODE_OAUTH_TOKEN (optional)"] --> CFG
  CODEX["~/.codex/auth.json"] --> CX[codex exec]
  CFG --> CT[container.py]
  ENV -. never .-> DATA[(data/ volume)]
```

## 11. Tests

```mermaid
flowchart LR
  subgraph "tests/ · 41 · no network"
    U[unit: settings · store · markdown] --> UC[usecases: fake brain + fake chat]
    UC --> E2E["e2e: Bot API stub (http.server) + fake brain<br/>full day: chat → settings → replan → morning → compact"]
  end
  E2E --> LIVE["scripts/live_smoke.sh · real Telegram + Codex<br/>6 steps, screenshots in tests/e2e/evidence/"]
```

## 12. Hosting now and later

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
