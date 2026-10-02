# Mentor assistant bot

A personal Telegram mentor-assistant for anything you're working on: a business, a side
project, a job hunt, home chores, a move, studies. It keeps one task graph across all of them,
sends a morning brief, and does the tasks it can (research, drafts, files, code on a branch).
What it can't do, it prepares and hands to you: you get the files, the exact action and a Done
button. You change the plan by just talking to it.

It runs the `codex` and `claude` CLIs on your existing **ChatGPT or Claude subscription**, so
it needs no API keys. Python 3.12, standard library only.

```mermaid
flowchart LR
  You((you)) <-- Telegram --> BOT[mentor bot]
  BOT -- 08:00 brief · pinned plan · reports · files --> You
  BOT --> D[(data/tasks.json · projects/*)]
  BOT -. subscription .-> CX[codex exec]
  BOT -. subscription .-> CL[claude -p]
```

## What it does

| You say | Bot does |
|---|---|
| "what's due this week?" | answers from plans and timelines |
| "move the dentist to Friday" | replans with a heavier model, updates the pinned message |
| "switch to gpt-6-astra high" | validates and changes model/effort |
| "send a Gantt of the plan" | renders Mermaid to PNG and posts it |
| "what's in the website repo?" | reads a project's linked folder or repo, read-only |
| (silent since yesterday, 08:00) | asks Yes/No, proposes moves for undone tasks, writes plan.md on Approve |
| "add project renovation" | creates `data/projects/renovation/` from the template |
| "what's next?" | answers from the plan's Next line |
| "go on" | starts the work loop now |
| "I submitted the form" | marks that task done, the loop continues |
| (a task needs a risky step) | sends a proposal with Approve / Approve · other provider / Reject |

While it works you see 👀 on your message and "typing…"; 🤔 means a heavy step is running.

## What it does without asking

The worker takes the next ready task from `data/tasks.json` and ends it as done, needs approval,
needs you, or failed. The rules are in `prompts/work.md`.

| Without asking | Needs your approval | Stays with you |
|---|---|---|
| files in the task's work dir | system packages, global installs | submitting forms |
| commits on a new branch of the project repo (no push) | containers, VMs, downloads over ~500 MB | sending emails (drafts only) |
| installs inside the work dir | deploying, anything public | payments, logging in |
| reading the public web | accounts, spending, files outside work dir and repo | live recordings, personal decisions |

## Quick start

```bash
uv venv && uv pip install -e '.[dev]'
cp .env.example .env         # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
cp -r data.example data       # your plans live here; keep it in its own private repo
codex login                  # or: claude setup-token -> CLAUDE_CODE_OAUTH_TOKEN in .env
mentor doctor                # checks Telegram + brain
mentor serve                 # long-poll; add --with-scheduler for built-in jobs
```

Get the token from @BotFather. For the chat ID, message your bot and read `message.chat.id` from
`getUpdates`.

## Projects

A project is anything with goals and dates: a product launch, a garden, taxes, a trip. Each one
is a folder. Copy `data/projects/_template/` and fill in:

```
data/projects/<name>/
  project.md    what it is, goals, optional "repo: /path/to/folder"
  timeline.md   events and deadlines
  plan.md       project-level plan
data/plan.md    cross-project plan, rendered into the pinned message
```

## Scheduled jobs

```bash
mentor job morning   # 08:00 check-in, then the daily brief (idempotent per day)
mentor job deadline  # 09:00: no answer to the check-in -> reconcile the plan
mentor job replan    # weekly replan
mentor job compact   # fold old chat history into summary.md
mentor job work      # work loop: next ready task until none is left or the daily budget is used
```

The worker also starts after button presses, the chat actions `work` and `task_update`, replan
and the morning job. An hourly timer is the safety net. One instance runs at a time; its output
goes to `data/work.log`.

Run them from cron, systemd timers, or `mentor serve --with-scheduler`. See
[deploy/README.md](deploy/README.md) for all three and for Docker.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | required | bot token |
| `TELEGRAM_CHAT_ID` | required | the only chat the bot answers |
| `DATA_DIR` | `./data` | plans, projects, history, settings |
| `TZ` | `Europe/Kyiv` | schedule and "today" |
| `CLAUDE_CODE_OAUTH_TOKEN` | empty | enables the Claude brain |
| `KROKI_URL` | `https://kroki.io` | Mermaid renderer; self-host to keep plans private |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | empty | email drafts saved to Gmail Drafts over IMAP; unset: draft text is sent in Telegram |
| `BROWSER_CDP_URL` | empty | attach the Playwright MCP server to a running Chrome so the worker can read pages behind logins; needs `npx` on the service's PATH |

Chat and heavy model settings live in `data/settings.json` and are changed by chatting.
`coder` is a third tier with the same fields, used for `coding` and `system` tasks (default
Claude `sonnet` `high`); `work` sets `daily_runs` (default 12).

## Tests

```bash
.venv/bin/python -m pytest -q     # unit, use cases, e2e against a local Bot API stub
scripts/live_smoke.sh             # manual check with real Telegram and a real brain
```

## Architecture

Clean architecture, light: `domain/`, `usecases/`, `ports/`, `adapters/`, `app/`. In chat and
planning the brain never writes files: it returns `{reply, document, actions}`, and the use
cases execute them. Only the worker runs a write-enabled brain.
Diagrams are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Notes

- Codex runs with `--ignore-user-config` and stdin closed. Chat and planning use a read-only sandbox.
- Worker writes: on the host Codex is kernel-sandboxed to the work dir (and the project repo for
  coding tasks); Claude is limited by its permission rules only, with no kernel sandbox.
- "Never submit", "never send" and "browser is read-only" are rules in the prompt, not mechanisms.
- On Ubuntu 24.04, apply `deploy/apparmor-bwrap` so the Codex sandbox can start.
- A single-user bot on your own subscription matches the documented CI use of these CLIs. Do not
  offer it to others on your login.
