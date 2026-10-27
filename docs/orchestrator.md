# Orchestrator

[← back to README](../README.md)

A GitHub Project as the shared work queue for Claude Code panes in
[Herdr](herdr.md), and an orchestrator session that works it. It starts a pane
per item, keeps each one moving, and brings you in only for decisions it can't
make. You answer on the issue, from your phone if you like, and it picks the
work back up.

```
 Ready ──start──▶ In progress ──STATUS: done──────────────▶ Review / Done
                     │   ▲
      needs-decision │   │ you answer in a comment;
   or permission     ▼   │ the orchestrator passes it to the pane
   prompt         Needs you  ── push notification
```

- [How it works](#how-it-works)
- [The board](#the-board)
- [Worker protocol](#worker-protocol)
- [Guardrails](#guardrails)
- [Setup](#setup)
- [Day to day](#day-to-day)

## How it works

| Piece | Role |
|---|---|
| [`orchestrator/board.py`](../orchestrator/board.py) | Reads and writes the Project through `gh`: list, show, add, set fields, comment, and `poll` for changes |
| [`orchestrator/dispatch.py`](../orchestrator/dispatch.py) | Pane mechanics: open a pane for an item in a `workboard` tab, start Claude, hand it a brief, read its last reply, nudge, release, resume |
| [`orchestrator/watch.sh`](../orchestrator/watch.sh) | Event stream for Claude Code's Monitor: pane state changes every 10 s, board changes every 2 min |
| [`skills/orchestrate/`](../skills/orchestrate/SKILL.md) | `/orchestrate`, the policy the orchestrator session follows |

The orchestrator is an ordinary Claude Code session that runs `/orchestrate`
in a spare pane. It spends no tokens while the workers are busy: `watch.sh`
only wakes it when a worker stops, or when you move or answer something on the
board.

Two details that make it reliable:

- **Briefs go in files.** Typed into a terminal, a multi-line brief can submit
  line by line. Each worker is told "read your brief at …" instead.
- **Prompts wait for `working`.** Right after a prompt lands, Herdr still
  shows the pane as idle for a moment. Without waiting, the watcher would
  report a stop that never happened.

## The board

Items are issues in a **private issues repo**, added to the Project. They
don't live in the repo the work happens in, because an issue in a public repo
is public even when the Project is private, and decision threads tend to
discuss exactly what a public repo must not contain. The `Checkout` field says
where the work happens.

| Field | Values |
|---|---|
| Status | `Backlog` (ignored), `Ready`, `In progress`, `Needs you`, `Review`, `Done` |
| Checkout | checkout name under `~/code`, or mapped in `repo_paths` in the config |
| Priority | `P1`, `P2`, `P3`; P1 gets a free pane first |
| Gate | `auto`, or `ask` (always finishes in Review) |
| Session, Pane | filled in by the orchestrator, so a closed pane can be resumed |

## Worker protocol

Every worker's brief asks it to work on its own, stay terse, follow the repo's
`CLAUDE.md`, and end every reply with exactly one line:

```
STATUS: continuing — <next step>
STATUS: needs-decision — <question, options, recommendation>
STATUS: done — <result>
```

| Footer | Orchestrator does |
|---|---|
| `continuing` | Sends "Proceed." (at most 6 times an hour per item, then treats it as a loop) |
| `needs-decision` | Posts the question on the issue, sets **Needs you**, sends a push notification |
| `done` | Posts the result, sets Review or Done, closes the pane (the session is kept), starts the next item |
| missing | Asks once for the footer, then escalates |

## Guardrails

- **Never answers permission prompts.** A pane stuck on one becomes
  **Needs you** with the command in the question. One agent approving another
  would sidestep the permission system, and Herdr refuses to prompt a blocked
  pane anyway.
- **Nothing public, paid or outward-facing.** Pushing to a public repo,
  posting, submitting, sending messages, spending money, DNS or cloud changes
  always come to you, whatever the Gate.
- **Answers questions only from what's written down.** Only when the brief or
  an earlier answer of yours settles it; otherwise it asks you.
- **Stays in its lane.** It only touches items on the board and panes it
  opened, and never closes a pane that is working.

## Setup

Needs Herdr, `gh` with the `project` scope, and this repo checked out.

```bash
gh auth refresh -s project      # on WSL: BROWSER=/mnt/c/Windows/explorer.exe gh auth refresh -s project
bash orchestrator/setup.sh      # optional arg: issues repo name (default "workboard")
```

`setup.sh` creates the empty private issues repo and the Project, sets up the
fields, writes `~/.config/workboard/config.json`, and links
`~/.claude/workboard` and `~/.claude/skills/orchestrate` to this checkout.

In the config: `max_panes` (default 4), `max_nudges_per_hour` (6) and
`repo_paths` for checkouts that aren't at `~/code/<Checkout>`. Runtime state
(pane map, briefs, nudge counts, poll snapshot) lives in
`~/.local/state/workboard/`.

## Day to day

```bash
# queue work: say what "done" means in the body
python3 ~/.claude/workboard/board.py add --repo my-repo --status Ready --priority P1 \
  --title "Add retry with backoff to the webhook client" \
  --body "Retry 5xx up to 3 times with jittered backoff; tests pass; commit on a branch."

python3 ~/.claude/workboard/board.py list
```

Then run `/orchestrate` in a spare Herdr pane. When something lands in
**Needs you**, answer in a comment on the issue. The orchestrator sees it
within two minutes and passes it to the pane. Say "orchestrate stop" to end
it; the panes are left as they are.
