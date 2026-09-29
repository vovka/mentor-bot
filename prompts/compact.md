# Compact history

You have read-only access rooted at `history/` (your current working directory). Fold the old
daily history files below into an updated `summary.md` so raw days don't accumulate unbounded.

Preserve: every fact, decision, and commitment from the current summary and from the days being
folded in. Compress prose and merge duplicates, but do not drop information — this summary is the
only surviving record of these days once folded.

## Current summary (summary.md)

{summary}

## Days being folded in

{days}

## What to do

Do not write files. Put the COMPLETE new content of history/summary.md in the `document` field;
put a ≤600-char plain-text summary of what changed in `reply`; `actions` must be `[]`. Do not
touch the individual day files — they stay on disk untouched.
