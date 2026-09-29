# Compact history

You have workspace-write access rooted at `history/` (your current working directory). Fold the
old daily history files below into `summary.md` — the file directly in your cwd — so raw days
don't accumulate unbounded.

Preserve: every fact, decision, and commitment from the current summary and from the days being
folded in. Compress prose and merge duplicates, but do not drop information — this summary is the
only surviving record of these days once folded.

## Current summary (summary.md)

{summary}

## Days being folded in

{days}

## What to do

1. Rewrite `summary.md` in your cwd with the current summary plus the days above folded in.
2. Do not touch the individual day files — they stay on disk untouched.
3. Respond with JSON matching the output schema: `{{"reply": "...", "actions": []}}`. `actions`
   must always be `[]`. `reply` must be plain text, a short status of what was folded.
