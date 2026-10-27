# Herdr

[← back to README](../README.md)

[Herdr](https://github.com/herdrdev/herdr) is a terminal multiplexer built for
coding agents: it knows which panes run Claude and whether each is working,
blocked or done. This folder is the config and the three small helpers that
make a grid of Claude panes on WSL2 pleasant to live in.

## Config

[`herdr/config.toml`](../herdr/config.toml) → `~/.config/herdr/config.toml`.
It only contains settings that differ from `herdr --default-config`.

| Setting | Why |
|---|---|
| Sidebar rows add `terminal_title_stripped` | By default every Claude pane reads `w1 t1 / claude`. Claude Code writes its session name to the terminal title, so the sidebar now shows that name and follows renames. |
| Pine `[theme.custom]` for Herdr's own chrome | Fixed in both light and dark. A live config reload only applies some tokens, so a per-mode sidebar needed a restart to look right. |
| `[ui.sound]` + `[ui.toast]` | A sound and a toast when an agent finishes or needs approval. Bring your own clip as `~/.config/herdr/sounds/notify.mp3`; none ships here. |
| `alt+1…9` | Focus the Nth agent in the sidebar and start typing. |
| `prefix+alt+1…9` | Focus the Nth pane of any kind, in reading order. |
| `prefix+m` | Mute sound and toasts for an hour. |

Shell commands in the config use `/home/YOU/.local/bin/…`; point them at your
home.

## Helpers

Copy `herdr/bin/*` to `~/.local/bin/` and make them executable.

### Mute for an hour

`herdr-toggle-toasts` flips toast delivery and sound together and reloads the
config. Muting writes a deadline to `~/.cache/herdr-mute-until` and starts a
detached timer that unmutes when it passes.

The [statusline](statusline.md) reads that file to show `🔇 Herdr muted ·
42m left`. If the timer died (WSL restarted), the deadline is already past when
the statusline next draws, so it runs the unmute itself rather than showing a
stale countdown.

### Focus pane N

`herdr-focus-pane N` focuses the Nth pane of the current tab in reading order.
Herdr's CLI only moves focus by direction, and its built-in `focus_agent` only
counts agent panes, so this goes through the socket API's `pane.focus`.

### Sound on WSL

Herdr plays sounds through the first of `paplay`, `pw-play`, `ffplay`,
`mpg123` or `mpv` it finds. A stock WSL install has none of them, and
installing them needs sudo. `herdr/bin/mpg123` is a stand-in:

- Plays the file with a static `ffmpeg` in `~/.local/bin`, through WSLg's
  PulseAudio bridge.
- WSLg's PulseServer sometimes hangs until `wsl --shutdown`. When a quick probe
  or the playback fails, it falls back to Windows audio through PowerShell.
- Herdr kills the player after 15 seconds and deletes its temp copy of the
  clip. The shim keeps its own copy and detaches, so long clips play out.

## A WSL gotcha

The Herdr server is started by systemd, so every pane, and every Claude Code
hook running inside one, inherits a PATH with **no `/mnt/c` entries**.
`powershell.exe` and `cmd.exe` are not found even though WSL interop works. Any
script here that calls a Windows binary uses its absolute path for this reason.
