#!/usr/bin/env bash
# Live smoke test against the real bot. Reads the token from .env but never echoes it.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f .env ]]; then
  echo "missing .env" >&2
  exit 1
fi

TELEGRAM_BOT_TOKEN=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2-)
TELEGRAM_CHAT_ID=$(grep -m1 '^TELEGRAM_CHAT_ID=' .env | cut -d= -f2-)

if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$TELEGRAM_CHAT_ID" ]]; then
  echo "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing from .env" >&2
  exit 1
fi

echo "== mentor doctor =="
.venv/bin/mentor doctor

echo
echo "== mentor job morning --dry-run =="
.venv/bin/mentor job morning --dry-run

echo
echo "== pinned message (id only; token never echoed) =="
pinned_id=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChat" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" | jq -r '.result.pinned_message.message_id // "none"')
echo "pinned_message_id: ${pinned_id}"

cat <<'EOF'

== manual chat steps ==
Send each message below in Telegram (typed by hand, or via browser automation), one at a
time, waiting for the bot's reply before sending the next. After each, check the listed file(s).

1. "what's due this week?"
   check: data/history/<today>.md has a matching user: and bot: line.

2. "use gpt-6-astra low"
   check: data/settings.json shows model=gpt-6-astra, effort=low.

3. "move the demo recording to Friday"
   check: data/plan.md updated; the pinned Telegram message edited to match it.

4. "add project jobpilot at /path/to/jobpilot"
   check: data/projects/jobpilot/ created from _template, project.md filled in.
EOF
