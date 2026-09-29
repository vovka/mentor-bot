# Mentor bot — architecture

**Status 2026-09-29:** built, 41 tests, live-tested (chat, settings switch, replan+pin,
add_project, morning brief), running as a systemd user service.

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

**Default brain is Codex** (`codex exec`, already logged into ChatGPT on this machine); the
Claude adapter is secondary, used only when the user switches to it. Every Codex call passes
`--ignore-user-config` — this machine's `~/.codex/config.toml` points `model_provider` at a
local proxy (`127.0.0.1:8787`) and lists MCP servers that hang headless; `auth.json` still
applies — closes stdin (`codex exec` blocks on an open one), runs under `-s read-only`, and
gets `--output-schema prompts/output_schema.json` with `-o` writing the last message to a
temp JSON file that gets parsed then deleted; a 180s subprocess timeout bounds every call.
Models the ChatGPT login accepts (probed 2026-09-29, `domain/settings.py` ALLOWED table):
`gpt-5.5`, `gpt-5.6-luna/sol/terra`, `gpt-6-astra`, `gpt-reserve`. Chat default is
`gpt-5.5 low`; heavy (replan/compact) default is `gpt-6-astra high`, overridable in
`settings.json.heavy`.

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
    settings.py    BrainSettings(provider, model, effort) + ALLOWED table + validate()
    actions.py     Action, BrainTask, BrainResult, OUTPUT_SCHEMA (loaded from prompts/output_schema.json)
    project.py     Project(name, path, repo_path)
    conversation.py Update(update_id, chat_id, text, at), Message(role, text, at)
  usecases/        one file per verb the bot can do; orchestrate ports, no I/O of their own
    handle_update.py    dedup by update_id (under the lock), skip blank text, → handle_message
    handle_message.py   inbound chat → brain → dispatch actions → reply
    morning_brief.py    today's items from plan+timelines → chat, idempotent per day
    replan.py           full replan (brain, heavy settings) → plan.md → post + pin
    compact.py          fold day files older than N days into summary.md
    change_settings.py  validate + persist BrainSettings (regular or heavy)
    add_project.py      validate slug + repo_path exists → create project folder
    scout.py            read-only Q&A over one project's repo_path
  ports/           Protocols (interfaces)
    chat.py        send(text) / edit(msg_id, text) / pin(msg_id) / poll(offset) -> [Update]
    brain.py       run(task: BrainTask) -> BrainResult    (task = prompt + files it may touch)
    store.py       read/write plan, timeline, settings, history, state, projects
    clock.py       now()
  adapters/        one folder per external thing; only place with I/O
    telegram/      api.py (long-poll + send/edit/pin, stdlib urllib; TELEGRAM_API_BASE env
                    lets tests point at a stub), markdown.py (escape_v2, chunk 4096), fake.py
    brain/         codex_cli.py (default), claude_cli.py (secondary), fake.py (tests)
    store/         files.py (Markdown/JSON under data/), lock.py (fcntl.flock data/.lock)
    scheduler/     inprocess.py (see §4) — cron/systemd are deploy/ files, not code
  app/             wiring + entrypoints
    config.py      env → settings (TELEGRAM_BOT_TOKEN, CHAT_ID, DATA_DIR, CLAUDE_CODE_OAUTH_TOKEN, CODEX_HOME)
    container.py   builds adapters from config, hands them to use cases
    cli.py         `mentor serve [--with-scheduler]` | `mentor job morning|replan|compact` | `mentor doctor`
    jobs.py        `mentor job <name>` → build a container, dispatch to the use case
data/              the bot's memory; a volume in deployment
  plan.md settings.json state.json history/YYYY-MM-DD.md history/summary.md
  projects/_template/ projects/<name>/{project.md,timeline.md,plan.md}
prompts/           mentor.md (system prompt), morning.md, replan.md, scout.md, compact.md,
                   output_schema.json
tests/             unit/ usecases/ e2e/  (41 tests)
scripts/           live_smoke.sh
deploy/            crontab, mentor.service, mentor-{morning,replan,compact}.{service,timer},
                   apparmor-bwrap, README.md
Dockerfile  compose.yml
```

"Where do I change…"

| …personality / rules | `prompts/mentor.md` |
| …plan, deadlines | `data/plan.md`, `data/projects/<name>/timeline.md` (or tell the bot) |
| …chat / heavy (replan) model | `data/settings.json` — via chat (`set_settings` action), never hand-edited by the agent |
| …allowed models | `domain/settings.py` ALLOWED table |
| …when jobs run | whichever scheduler adapter is active (§4) |
| …Telegram → Slack | new folder in `adapters/`, implements `ports/chat.py`, one line in `container.py` |
| …memory | `data/history/`, `data/history/summary.md` |

## 3. Brain: cheap chat + expensive workers, via actions

Use case `handle_message` always calls the brain with the *conversational* settings
(default: Codex `gpt-5.5`, low effort). The system prompt says: answer small talk yourself;
for anything that changes the plan, reads a project's repo, changes settings, or adds a
project, emit a structured action instead of doing it yourself.

Codex has no subagents, so delegation is **not** native Agent-tool subagents — there is no
`.claude/agents/` directory, for either provider. Both brain adapters return the same JSON
contract: `{"reply": str, "document": str | null, "actions": [{"kind": ..., "args": {...}}]}`,
kinds `replan | scout | set_settings | add_project`. `handle_message` dispatches each action
to the matching use case in code:

- `replan` → `replan.run`: reruns the brain with *heavy* settings (default `gpt-6-astra high`,
  overridable in `settings.json.heavy`), still sandboxed read-only; the new plan comes back
  whole in `document`, and `replan` writes it to `plan.md` through the store.
- `scout` → `scout.run`: reruns the brain read-only over just that project's `repo_path`,
  answers a question, writes nothing.
- `set_settings` → `change_settings.run`: validates provider/model/effort (or the heavy block)
  against `ALLOWED` before persisting; a bad value gets the allowed list back in the reply.
- `add_project` → `add_project.run`: validates the name is a slug and `repo_path` exists on
  disk before creating the project folder from the template.

**The brain never writes files** — sandbox is `read-only` everywhere, chat and heavy calls
alike. Codex's bubblewrap sandbox cannot start on this host: Ubuntu 24.04 blocks unprivileged
user namespaces, so `workspace-write` is out. The fix is a per-binary AppArmor profile
(`deploy/apparmor-bwrap`, see `deploy/README.md`), not disabling the global restriction —
that's why `replan`/`compact` return the whole new file in `document` instead of editing it
in place.

- **Codex adapter (default):** `codex exec -o OUT.json -m MODEL -c model_reasoning_effort=EFFORT
  -s read-only -C CWD --skip-git-repo-check -c approval_policy=never --ignore-user-config
  --output-schema prompts/output_schema.json -- PROMPT`, stdin closed, 180s timeout. Models
  the ChatGPT login accepts: `gpt-5.5`, `gpt-5.6-luna/sol/terra`, `gpt-6-astra`, `gpt-reserve`.
- **Claude adapter (secondary):** `claude -p --model M --effort E --output-format json
  --json-schema "$(cat prompts/output_schema.json)" --allowedTools Read,Grep --permission-mode
  default --permission-prompts none --add-dir CWD`; never `--bare`.

Model/effort switching by chat: the agent emits `set_settings`; code validates against
`ALLOWED` before the next spawn — the agent never edits `settings.json` itself.

## 4. Scheduler is a port, jobs are commands

The substitution point is the command line, not a Python interface:
`mentor job morning`, `mentor job replan`, `mentor job compact`. Any scheduler that can run a
command works; three adapters ship, pick one per host:

| Adapter | Where | How |
|---|---|---|
| `cron` | local box | `deploy/crontab` → `crontab deploy/crontab` |
| `systemd` | local box / VM | `deploy/mentor.service` (serve) + `mentor-{morning,replan,compact}.{service,timer}` → `systemctl --user enable --now` |
| `in-process` | container | `mentor serve --with-scheduler`: a thread polling every 30s with stdlib `time`; schedule read from `data/schedule.json`, default `{morning: 08:00, replan: Sun 20:00, compact: Sun 21:00}` |

Running on this machine: systemd user units (`mentor.service` + the three timers),
`loginctl enable-linger` set so they fire without a login session. Jobs are idempotent per
day (`state.json: last_brief_date` / `last_replan` / `compacted_through`), so a double fire or
a missed-and-retried fire is harmless. Timezone from config, default `Europe/Kyiv`.

## 5. Memory without a months-long session

- Every brain call is a fresh session. Context = `summary.md` + last 2 day files + the task.
- Day files are append-only, written by the store adapter, never by the model.
- Older history: the chat brain may grep `data/history/` itself, through its read-only
  sandbox (Codex `-s read-only`; Claude `--allowedTools Read,Grep`).
- `compact` weekly: cheap model folds days older than 14 into `summary.md` (keep decisions,
  deadlines, preferences; drop chit-chat). Day files are kept.
- Optional: `--session-id` per calendar day so same-day follow-ups share context; reset at midnight.

## 6. Options, smallest to largest

| | A: flat scripts | **B: clean-arch + CLI brains (built)** | C: B + Agent SDK brain |
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

## 8. Foundations for later (decided 2026-09-29; 8.1 not built, 8.2/8.3 built)

### 8.1 Serverless ingress (Vercel / Lambda)

Telegram webhooks can call an HTTPS function, yes. What cannot run there is the brain: the
`claude`/`codex` subprocess needs a Node/Rust binary, a writable disk with login state, and
minutes of wall time. Lambda *container images* (15-min limit, 10 GB image, `/tmp` scratch) can
run it; Vercel/edge functions cannot. So the future shape is **ingress + worker**:

```
Telegram ──webhook──▶ ingress fn (Vercel/Lambda, ms)  ──▶ queue / direct call ──▶ worker (VM or Lambda container)
                      validates secret, dedups update_id, acks 200          runs use case, replies via Chat port
```

Foundation laid now, at zero extra cost — and already built, not just planned:

- `usecases/handle_update.run(store, brain, chat, clock, update)` is the single entry for an
  inbound Telegram update: dedups by `update_id` under the store lock, skips blank text, then
  calls `handle_message`. The long-poll adapter (`adapters/telegram/api.py`) calls it in a
  loop; a webhook adapter — still "later" — would call it once per request. Tests point the
  adapter at a stub via `TELEGRAM_API_BASE`.
- No process memory between updates. Everything the use case needs is read through `Store`.
  `state.json` records `last_update_id` for dedup.
- `Store` is a port; `files.py` today, `s3.py`/`dynamo.py` later without touching use cases.
- Config from env only (`app/config.py`), never from files the code path assumes exist.
- `CLAUDE_CODE_OAUTH_TOKEN` is an env var, so it travels to any host. Codex's `auth.json`
  refreshes itself on disk; on serverless it must be written back to a secret store after each
  run (`adapters/brain/codex_cli.py` gets a `persist_auth()` hook, no-op on a VM).

### 8.2 Projects are plug-ins (built)

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
project list injected; the `scout` action takes a project name and reads only that repo.
Morning brief merges per-project items by date. "Add project X at ~/dev/x" in chat → a
`add_project` action validates the path and creates the folder from a template.

### 8.3 Memory: files first, tool/MCP behind the same port

- Now: history is Markdown; the agent uses built-in `Read`/`Grep`. Zero code.
- `Store` gets a `search_history(query, since, project)` method when needed; today the brain greps the files directly.
- If structured search or Codex parity is needed: wrap that port in a stdio MCP server
  (`adapters/mcp/memory_server.py`, FastMCP, ~40 lines). Claude loads it with
  `--mcp-config`, Codex via `mcp_servers` in `config.toml`, Agent SDK via options. Same
  functions, three consumers. Not built until Grep proves insufficient.
