# Skills

[← back to README](../README.md)

Claude Code skills: copy each folder under [`skills/`](../skills/) to
`~/.claude/skills/`, and Claude picks them up by name or from what you say.

## /regrid

Re-tiles the current Herdr tab into an even grid. Running processes and agents
are kept; only the geometry changes.

It picks the number of rows that makes the panes look most square for the
window's actual size, counting a terminal cell as about twice as tall as it is
wide. Rows stay balanced, so panes split 2 + 2 or 3 + 2, never 3 + 1. Six panes
come out as 3 + 3 on a wide window and 2 + 2 + 2 on a squarer one.

Say "regrid" or "tidy the panes", or run it directly:

```bash
python3 ~/.claude/skills/regrid/regrid.py --dry-run   # preview
python3 ~/.claude/skills/regrid/regrid.py             # apply
```

Requires `HERDR_ENV=1`, which Herdr sets in its panes. Tests:
`python3 -m unittest discover -s skills/regrid`.

## /orchestrate

Runs the [workboard orchestrator](orchestrator.md) in the current pane. It is
linked by `orchestrator/setup.sh` rather than copied, because it calls the
scripts in `orchestrator/`.

## /dark and /light

Run [`term-theme`](terminal-and-theme.md#term-theme) with `--restart`, then tell
you to type `herdr` in the shell that appears once Herdr has restarted. Say "no
restart" to skip that step.
