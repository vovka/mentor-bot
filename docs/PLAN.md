# Mentor bot — implementation plan (Option B, Codex default)

## Context

Telegram bot that mentors startup projects (Tusk, CampaignLoop first): keeps a pinned plan,
sends an 08:00 Europe/Kyiv brief, renegotiates the plan in chat, switches model/effort/provider
by chat. Architecture decided in `Pitches/mentor-bot/ARCHITECTURE.md` (clean-arch light, CLI
brains on subscriptions, projects as folders, replaceable scheduler). Published pages:
architecture https://claude.ai/artifact/Kz2GVi8aQ5SpxxtQVg1HFD, plan
https://claude.ai/artifact/7a24JXnoSFx4oAwGhgyGvj.

Decisions since: **Codex is the default brain** (already logged in, ChatGPT), Claude adapter
secondary. Keys are obtained autonomously via Claude in Chrome (web.telegram.org and claude.ai
are logged in); implementer may message the bot. New repo `~/dev/mentor-bot`, Python 3.12,
stdlib-first, pytest.

Two design changes from the docs, driven by Codex facts found on this machine:

1. Codex has no subagents → delegation is **structured output** for both CLIs: the chat brain
   returns `{reply, document, actions:[replan|scout|set_settings|add_project]}`; `handle_message`
   executes actions in code. The brain never writes files — the sandbox is always `read-only`
   (workspace-write needs bubblewrap, which fails under this host's apparmor userns restriction
   and in containers). `replan`/`compact` get the new plan/summary back in `document` and the
   use case writes it via the store. Model switching is validated by code, never by the agent
   editing `settings.json`.
2. `~/.codex/config.toml` sets `model_provider="headroom"` (local proxy 127.0.0.1:8787) →
   every codex call passes `--ignore-user-config` (auth.json still applies; MCP servers in the user config hang headless).

## File tree (≤100 lines per file)

```
~/dev/mentor-bot/
  mentor/
    domain/   plan.py timeline.py settings.py(ALLOWED+validate) conversation.py
              actions.py (Action, BrainTask, BrainResult, OUTPUT_SCHEMA) project.py
    usecases/ handle_update.py (dedup by update_id) handle_message.py (brain → dispatch actions)
              replan.py scout.py change_settings.py add_project.py morning_brief.py compact.py
    ports/    chat.py brain.py store.py clock.py   (Protocols)
    adapters/ telegram/{long_poll.py, markdown.py(escape_v2, chunk 4096), fake.py}
              brain/{codex_cli.py, claude_cli.py, fake.py}
              store/{files.py, lock.py(fcntl.flock data/.lock)}
              scheduler/inprocess.py (threading + zoneinfo Europe/Kyiv)
    app/      config.py(env only) container.py cli.py
              (`mentor serve [--with-scheduler] | job morning|replan|compact | doctor`)
  data/       plan.md settings.json state.json history/ projects/_template/ projects/<name>/
  prompts/    mentor.md replan.md scout.md compact.md morning.md output_schema.json
  deploy/     crontab mentor.service mentor-{morning,replan,compact}.timer
  Dockerfile compose.yml .env.example
  tests/      unit/ usecases/ e2e/   scripts/live_smoke.sh
```

## Contracts

- `BrainTask(prompt, cwd, write: bool, settings)`; `BrainResult(reply, actions, raw)`.
- `Chat: send(text)->id, edit(id,text), pin(id), poll(offset)->[Update]`.
- `Store: read/write plan(project?), read timeline(project?), settings, state, append_history,
  read_recent_history(days=2), projects(), add_project(name, repo_path)`.
- `settings.json = {"provider":"codex","model":"gpt-5.5","effort":"low"}`; ALLOWED:
  codex `gpt-5.5(low..xhigh) gpt-6-astra(low..max) gpt-6-sol gpt-6-astra(low..ultra)`;
  claude `haiku sonnet opus fable claude-opus-5-5 (low..max)`. Heavy settings for replan
  default `gpt-6-astra high`, overridable in `settings.json.heavy`.
- Sandbox map: chat → `-s read-only` / `--allowedTools Read,Grep`; replan, compact →
  `-s workspace-write -C data/` / `Read,Edit,Write,Grep --permission-mode acceptEdits`;
  scout → read-only over `project.repo_path`.

Codex: `codex exec -o OUT.json -m M -c model_reasoning_effort=E -s SANDBOX -C CWD
--skip-git-repo-check -c approval_policy=never --ignore-user-config
--output-schema prompts/output_schema.json -- PROMPT`; parse `json.load(OUT)`; timeout 180 s.
Claude: `claude -p PROMPT --model M --effort E --output-format json --json-schema "$(cat …)"
--allowedTools … --permission-prompts none --add-dir CWD`; parse `structured_output`; never `--bare`.

## Phases (each ends with a check)

**0. Keys, autonomous via Claude in Chrome.** web.telegram.org → @BotFather `/newbot` (name
`Mentor`, username `vova_mentor_bot` or next free) → token to `.env`. Send "hi" to the bot as
the user → `getUpdates` → chat id. Claude token deferred until the Claude adapter is enabled
(`claude setup-token`, approve on claude.ai). Check: `mentor doctor` sends one Telegram message
and runs `codex exec "say ok"`.

**1. Skeleton + domain.** pyproject, domain, ports, config, cli, `store/files.py`, fakes,
seed `data/projects/{tusk,campaignloop}` from `Pitches/*/action-items.md` and `events/*.md`.
Check: `pytest tests/unit`.

**2. Chat loop.** long_poll, handle_update/handle_message, codex_cli, change_settings,
add_project, prompts/mentor.md, pin logic (edit ≤4096 else post+re-pin; pinned plan truncated
with "see plan.md"). Check: `pytest tests/usecases`.

**3. Jobs + scheduler.** morning_brief/replan/compact/scout, `mentor job`, idempotent markers
in `state.json` under the lock, deploy/crontab + systemd units, inprocess scheduler.
Check: `mentor job morning --dry-run`; `systemctl --user list-timers` shows three.

**4. E2E tier 1.** `tests/e2e/`: `http.server` Bot API stub + fake brain, one scenario:
message→reply; "use gpt-6-astra low"→settings; "move demo to Friday"→replan action→plan.md diff→
`editMessageText`/`pinChatMessage`; replayed update_id→zero calls; `job morning`→one send;
`job compact` with 20 fixture days→summary.md, day files kept.

**5. Claude adapter + Docker.** claude_cli.py, Dockerfile (python:3.12-slim + tzdata + node +
`@anthropic-ai/claude-code` + codex), compose with `data/` volume and `~/.codex` mount.
Check: `docker compose up`; `mentor doctor` inside passes.

**6. E2E tier 2, live smoke.** `scripts/live_smoke.sh` + Claude in Chrome on web.telegram.org
acting as the user, ≤6 model calls: due-this-week; switch to gpt-6-astra low; switch to claude
(skipped if no token); move an item→pin edited; `job morning`; add project jobpilot. Screenshot
each step to `tests/e2e/evidence/<date>/`, send to user.

## Reuse

- MarkdownV2 reserved-char regex: `~/dev/_utils/claude-mem/src/services/integrations/TelegramNotifier.ts`.
- flock pattern: `~/dev/business_ideas/etsy-ai-images/agent-harness/automation/` (`flock` in run.sh); use blocking lock.
- Seed content: `Pitches/{tusk,campaignloop}/{action-items,intent-improved}.md`, `events/*.md`.

## Pitfalls handled

4096 chunking; MarkdownV2 escaping; codex writes only under `-C` dir; headroom proxy override;
`zoneinfo` + tzdata in Docker; per-day idempotency markers; single global `fcntl` lock between
`serve` and cron `job` processes (`# ponytail:` note, per-file locks only if contention measured).

## Verification (end-to-end)

1. `pytest` green (unit, usecases, e2e).
2. `mentor doctor` OK locally and in Docker.
3. Live smoke evidence folder reviewed by user; pinned plan visible in Telegram; 08:00 timer
   fires next morning (check `journalctl --user -u mentor-morning`).
