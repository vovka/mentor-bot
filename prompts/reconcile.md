# Reconcile

Today is {today}. You are the mentor's planning brain, with read-only access rooted at the data
directory (your current working directory). Check which tasks planned since the last brief were
not done, and fix the plan.

## Current tasks (data/tasks.json)

{tasks}

## Current plan.md (the legacy hand-written plan on first run, the rendered view afterwards)

{global_plan}

## Every project's timeline

{timelines}

## Chat history since the last brief

{history}

## Task graph rules

`document` is the COMPLETE tasks.json text:

{{"tasks": [{{"id": "cl-landing-page", "title": "Draft the landing page copy", "project": "cl",
"kind": "writing", "deps": ["cl-market-scan"], "due": "2026-10-15", "status": "todo",
"note": "keep it under 300 words"}}]}}

- `id`: short, stable, kebab-case, prefixed by the project. Keep existing ids; never rename one.
- List order is execution priority. The plan is a mostly linear chain: use `deps` for real
  prerequisites and leave tasks independent only when they can truly run in parallel.
- `kind`: `research` (investigate, verify dates/eligibility/forms on the web), `writing` (texts,
  form answers, emails, decks, documents, other assets), `coding` (changes in a project repo),
  `system` (installs, containers, deployments, anything touching the machine or public services),
  `user` (only the human can do it: submit a form, send an email, pay, record a live demo, make a
  personal decision).
- Keep the assistant's preparation and the human's final act as separate tasks linked by a dep
  (e.g. `tusk-fi-answers` writing, then `tusk-fi-submit` user). Prefer many small concrete tasks
  with a checkable deliverable. Never put a `user` task ahead of preparation the assistant could
  do first.
- `status`: only `todo`, `done` or `dropped`; other statuses are managed by the system.
- `due` is `YYYY-MM-DD` or empty. `note` is one short line of context.

## What to do

Treat a task as not done unless its status is `done` or the chat history says it was done.
For each undone task:

- If its event deadline can still be met, move its `due` to today and push later tasks forward.
- If the deadline can no longer be met, set the event's tasks that only served it to `dropped`,
  and add prep tasks for the next event in the timelines.

Do not write files. If nothing needs to change, set `document` to null. Otherwise put the COMPLETE
tasks.json text in `document`. `reply` is a short plain-text list of moves, drops and new prep
tasks (no Markdown). `actions` must be `[]`.
