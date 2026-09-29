# Mentor bot — architecture

Telegram bot that mentors the Tusk + CampaignLoop pitch effort: builds and pins a plan,
sends a morning brief with today's action items, and lets you renegotiate the plan in chat.
Runs on the local machine first; must move to a VM/container host without redesign.

## 1. Facts that shape the design (verified 2026-09-29)

**Claude subscription, headless — three documented ways, all use the same token:**

| Way | Auth | Notes |
|---|---|---|
| `claude -p …` | CLI login, or `CLAUDE_CODE_OAUTH_TOKEN` | `--bare` ignores OAuth, needs an API key — do **not** use `--bare` |
| Claude Agent SDK (`claude-agent-sdk` Python / `@anthropic-ai/claude-agent-sdk` TS) | same: it spawns the CLI, which reads `CLAUDE_CODE_OAUTH_TOKEN` | Docs: "Alternative to `/login` for SDK and automated environments" |
| GitHub Actions | `claude_code_oauth_token` secret | official flow, "runs use your Claude subscription instead of API billing" |

The token is what you remembered: `claude setup-token` → long-lived token, Pro/Max/Team/Enterprise
("tied to the subscription of the person who ran it"). The Anthropic HTTP SDK (`anthropic` package)
does **not** take it — that SDK is API-key billing only. Docs also state Anthropic does not allow
third parties to *offer* claude.ai login/rate limits in their products; a single-user bot on your own
subscription is the same shape as the documented CI use.

**ChatGPT subscription, headless:** `codex exec` "reuses saved CLI authentication by default"
(`~/.codex/auth.json`, or `CODEX_HOME` pointing at a dir containing it). Docs allow seeding that file
on a trusted runner and letting Codex refresh it in place; `CODEX_API_KEY` is the API-billing route.
No SDK for subscription use — subprocess only. Model/effort: `-m <model> -c model_reasoning_effort=<low|medium|high>`.

**Consequence:** the "brain" port has two adapters, both subprocesses. Claude adapter can be
`claude -p` (simplest, mirrors the Codex adapter) or the Agent SDK (more control, same auth).

**Deployment:** the bot is a long-lived process with a filesystem, a Node binary (`claude`) and a
Rust binary (`codex`). That is a container on a VM (AWS Lightsail/EC2, Fly.io, Hetzner, your
own box), not Vercel. Vercel/Lambda-style serverless breaks on all three points (no persistent
disk, execution time limits, no CLI login state). "Deployment-ready" therefore = one Docker image
+ one volume for `data/` + secrets via env. Webhook mode can be added later behind the same
`Chat` port if a host wants inbound HTTP instead of long-polling.

## 2. Clean architecture, light

Four layers, dependencies point inward only. Small enough to fit in a head.

```
mentor/
  domain/          plain dataclasses, no I/O
    plan.py        Plan, ActionItem, Milestone
    timeline.py    Event(deadline, format, cost, project, status)
    settings.py    BrainSettings(provider, model, effort) + ALLOWED table + validate()
    conversation.py Message(role, text, at)
  usecases/        one file per verb the bot can do; orchestrate ports, no I/O of their own
    handle_message.py   inbound chat → brain → reply, log both, re-pin if plan changed
    morning_brief.py    today's items from plan+timeline → chat
    replan.py           full replan (brain, heavy) → plan.md → post + pin
    compact.py          fold day files older than N days into summary.md
    change_settings.py  validate + persist new BrainSettings
  ports/           Protocols (interfaces)
    chat.py        send(text) / edit(msg_id, text) / pin(msg_id) / poll() -> [Message]
    brain.py       run(task: BrainTask) -> BrainResult    (task = prompt + files it may touch)
    store.py       read/write plan, timeline, settings, history, state
    clock.py       now()
  adapters/        one folder per external thing; only place with I/O
    telegram/      long_poll.py (stdlib urllib), webhook.py (later)
    brain/         claude_cli.py, codex_cli.py, claude_sdk.py (optional), fake.py (tests)
    store/         files.py (Markdown/JSON under data/), later s3.py if ever needed
    scheduler/     see §4 — cron, systemd, in-process
  app/             wiring + entrypoints
    config.py      env → settings (TELEGRAM_BOT_TOKEN, CHAT_ID, DATA_DIR, CLAUDE_CODE_OAUTH_TOKEN, CODEX_HOME)
    container.py   builds adapters from config, hands them to use cases
    cli.py         `mentor serve` | `mentor job morning|replan|compact` | `mentor scheduler`
data/              the bot's memory; a volume in deployment
  plan.md timeline.md settings.json state.json
  history/YYYY-MM-DD.md history/summary.md
prompts/           mentor.md (system prompt), morning.md, replan.md, compact.md
.claude/agents/    planner.md (fable), scout.md (haiku), reviewer.md (opus)  — Claude-only
Dockerfile  compose.yml  deploy/{crontab,mentor.service,mentor-*.timer}
```

"Where do I change…"

| …personality / rules | `prompts/mentor.md` |
| …plan, deadlines | `data/plan.md`, `data/timeline.md` (or tell the bot) |
| …chat model / planner model | `data/settings.json` / `.claude/agents/planner.md` |
| …allowed models | `domain/settings.py` ALLOWED table |
| …when jobs run | whichever scheduler adapter is active (§4) |
| …Telegram → Slack | new folder in `adapters/`, implements `ports/chat.py`, one line in `container.py` |
| …memory | `data/history/`, `data/history/summary.md` |

## 3. Brain: cheap conversational agent + expensive workers

Use case `handle_message` always calls the brain with the *conversational* settings
(default: Claude Haiku/Sonnet, low effort). The system prompt says: answer small changes
yourself (edit `plan.md`, `settings.json`); for re-planning, research, or anything touching
the repos, delegate to a named subagent and summarise its result.

- **Claude adapter:** subagents are the files in `.claude/agents/`, run natively by Claude
  Code's Agent tool. Zero orchestration code. `claude -p --model … --effort … --add-dir data
  --allowedTools Read,Edit,Write,Grep,Agent --permission-mode acceptEdits --permission-prompts none
  --output-format json`.
- **Codex adapter:** no subagent files; one model per call. `replan` use case then runs with the
  heavy settings directly. Acceptable — Claude is primary.
- **Agent SDK variant (optional, later):** same auth, same subagent files; gains typed `@tool`
  functions (`send_telegram`, `set_settings`) instead of "edit this file", streaming, hooks. Swap
  `claude_cli.py` for `claude_sdk.py`; nothing above `ports/` changes.

Model/effort switching by chat: agent edits `settings.json`; `change_settings` use case validates
against `ALLOWED` before the next spawn and replies with the allowed list on a bad value.

## 4. Scheduler is a port, jobs are commands

The substitution point is the command line, not a Python interface:
`mentor job morning`, `mentor job replan`, `mentor job compact`. Any scheduler that can run a
command works; three adapters ship, pick one per host:

| Adapter | Where | How |
|---|---|---|
| `cron` | local box | `deploy/crontab` → `crontab deploy/crontab` |
| `systemd` | local box / VM | `deploy/mentor.service` (serve) + `mentor-morning.timer` … → `systemctl --user enable --now` |
| `in-process` | container | `mentor serve --with-scheduler`: a thread with `sched`/`time` (stdlib) or APScheduler; schedule read from `data/schedule.json` |

Jobs are idempotent per day (`state.json: last_brief_date`), so a double fire or a missed-and-
retried fire is harmless. Timezone from config, default `Europe/Kyiv`.

## 5. Memory without a months-long session

- Every brain call is a fresh session. Context = `summary.md` + last 2 day files + the task.
- Day files are append-only, written by the store adapter, never by the model.
- Older history: the agent greps `data/history/` itself (Grep is in `--allowedTools`).
- `compact` weekly: cheap model folds days older than 14 into `summary.md` (keep decisions,
  deadlines, preferences; drop chit-chat). Day files are kept.
- Optional: `--session-id` per calendar day so same-day follow-ups share context; reset at midnight.

## 6. Options, smallest to largest

| | A: flat scripts | **B: clean-arch + CLI brains (recommended)** | C: B + Agent SDK brain |
|---|---|---|---|
| files | ~6 | ~20 small ones | ~24 |
| lines | ~250 | ~500 | ~700 |
| swap Telegram/scheduler/brain | edit code | swap adapter folder | same |
| tests | ad hoc | use cases tested with `fake.py` brain + in-memory store | same + SDK hooks |
| Codex support | yes | yes | yes (still CLI) |
| when | you want it today | you want to maintain it for months | file-as-tool proves flaky |

A is B with the layers collapsed into `bot.py`/`agent.py`/`jobs.py`; it is the earlier draft.
B costs ~250 more lines, all of them boilerplate-free Protocols and dataclasses; that is the
price of "I can find where things are in a month".

## 7. Runtime / deployment

- Python 3.12, stdlib for HTTP (`urllib`) and scheduling; `python-telegram-bot` only if webhooks.
- `Dockerfile`: python base + `npm i -g @anthropic-ai/claude-code` + codex binary; `data/` volume;
  env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `CLAUDE_CODE_OAUTH_TOKEN`, `CODEX_HOME=/secrets/codex`.
- Local: `mentor serve` in a herdr tab or a systemd user service; same image via `compose.yml`.
- Secrets never in `data/` (the volume may be backed up/synced); `.env` gitignored.

## 8. Foundations for later (decided 2026-09-29, not built now)

### 8.1 Serverless ingress (Vercel / Lambda)

Telegram webhooks can call an HTTPS function, yes. What cannot run there is the brain: the
`claude`/`codex` subprocess needs a Node/Rust binary, a writable disk with login state, and
minutes of wall time. Lambda *container images* (15-min limit, 10 GB image, `/tmp` scratch) can
run it; Vercel/edge functions cannot. So the future shape is **ingress + worker**:

```
Telegram ──webhook──▶ ingress fn (Vercel/Lambda, ms)  ──▶ queue / direct call ──▶ worker (VM or Lambda container)
                      validates secret, dedups update_id, acks 200          runs use case, replies via Chat port
```

Foundation laid now, at zero extra cost:

- `usecases/handle_update(update: dict) -> None` is the single entry for an inbound Telegram
  update. Long-poll adapter calls it in a loop; a webhook adapter calls it once per request.
  Both live in `adapters/telegram/`.
- No process memory between updates. Everything the use case needs is read through `Store`.
  `state.json` records `last_update_id` for dedup.
- `Store` is a port; `files.py` today, `s3.py`/`dynamo.py` later without touching use cases.
- Config from env only (`app/config.py`), never from files the code path assumes exist.
- `CLAUDE_CODE_OAUTH_TOKEN` is an env var, so it travels to any host. Codex's `auth.json`
  refreshes itself on disk; on serverless it must be written back to a secret store after each
  run (`adapters/brain/codex_cli.py` gets a `persist_auth()` hook, no-op on a VM).

### 8.2 Projects are plug-ins

The two products are examples. A project is a folder; adding one is adding a folder.

```
data/projects/
  tusk/          project.md  (what it is, repo path, goals, who it is for)
                 timeline.md (events, deadlines)   plan.md (project-level plan)
  campaignloop/  same
  <new>/         same — the bot discovers folders at run time
data/plan.md     cross-project plan the pinned message is rendered from
```

Domain: `Project(name, path, repo_path)`; `Store.projects()` lists folders. Prompts get the
project list injected; `scout` subagent takes a project name and reads only that repo.
Morning brief merges per-project items by date. "Add project X at ~/dev/x" in chat →
agent creates the folder from a template.

### 8.3 Memory: files first, tool/MCP behind the same port

- Now: history is Markdown; the agent uses built-in `Read`/`Grep`. Zero code.
- `ports/store.py` already exposes `search_history(query, since, project)` for use cases.
- If structured search or Codex parity is needed: wrap that port in a stdio MCP server
  (`adapters/mcp/memory_server.py`, FastMCP, ~40 lines). Claude loads it with
  `--mcp-config`, Codex via `mcp_servers` in `config.toml`, Agent SDK via options. Same
  functions, three consumers. Not built until Grep proves insufficient.
