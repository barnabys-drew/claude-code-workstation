---
name: light
description: Switch the terminal (every Herdr pane in WezTerm), Herdr's chrome and Claude Code to the light palette, then restart Herdr so the Claude panes take the new colour. Use when the user says /light, "light mode", or "switch to light".
---

Run `~/.claude/scripts/term-theme light --restart` with Bash. It rewrites the WezTerm,
Herdr and Claude Code configs (live reload), then restarts Herdr's server 4 seconds
later, which relaunches every pane with its Claude session resumed. This pane is
killed by that restart too, so reply in ONE short line immediately, before the
restart lands: say the mode is set and that they should type `herdr` in the shell
that appears. Do nothing else. If they say "no restart", run it without `--restart`
and note that Claude panes keep their old background until the next Herdr restart.
