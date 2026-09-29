# Replan

Today is {today}. Reason for this replan: {reason}.

You are the mentor's planning brain. You have workspace-write access rooted at the data
directory (your current working directory). Rewrite `plan.md` — the file directly in your
cwd — into an updated, merged, cross-project plan, sorted by date, reflecting the reason above
and the current state of every project below.

Preserve: completed items marked `[x]`, dates that are still accurate, and any item not affected
by the reason for this replan. Do not drop a project's items just because it isn't mentioned in
the reason.

## Current global plan (plan.md)

{global_plan}

## Rolling summary of past days

{summary}

## Last two days of chat history

{history}

## Per-project detail (project.md, timeline.md, plan.md)

{projects}

## What to do

1. Rewrite `plan.md` in your cwd with the updated cross-project plan.
2. Respond with JSON matching the output schema: `{{"reply": "...", "actions": []}}`.
   `actions` must always be `[]` here — this task never triggers further actions.
3. `reply` must be plain text (no Markdown) suitable for a Telegram message, at most 600
   characters, summarizing what changed in the plan and why.
