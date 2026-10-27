# WezTerm and light/dark theme

[← back to README](../README.md)

## WezTerm

[`wezterm/wezterm.lua`](../wezterm/wezterm.lua) → `%USERPROFILE%\.wezterm.lua`
on the Windows side. It opens straight into WSL Ubuntu with JetBrains Mono, and
holds two palettes:

| Mode | Look |
|---|---|
| `dark` | Pine green `#1B2A20` with bone text |
| `light` | Warm bone paper `#DCD6C5` with dark ink, forest-green and tan accents |

One line, `local mode = 'dark'`, picks the palette. `term-theme` rewrites it,
and WezTerm reloads on save.

### Windows clipboard habits

| Key | Does |
|---|---|
| `Ctrl+C` | Copies if text is selected, otherwise interrupts, as in Windows Terminal |
| `Ctrl+V` | Pastes text |
| `Ctrl+Shift+V` | Sends a raw `^V` to the pane, so Claude Code can paste a **screenshot** from the clipboard (WezTerm's own paste drops images) |
| `Ctrl+click` | Opens the link under the cursor, even through Herdr's mouse capture |

Mouse release **never** writes the clipboard. WezTerm copies on release by
default, and on Windows there is no separate primary selection, so clicking
back into a pane was replacing a freshly snipped screenshot with terminal text.

## term-theme

```bash
term-theme dark              # or light
term-theme light --restart   # also restart Herdr (see below)
term-theme status            # what each piece is set to
```

One command flips everything that has a colour:

| What | Dark | Light |
|---|---|---|
| WezTerm palette | `dark` | `light` |
| Windows Terminal scheme | rewritten to the dark palette | rewritten to the light palette |
| Claude Code `theme` | `dark-ansi` | `custom:paper` |
| Herdr's own chrome | unchanged | unchanged |

`custom:paper` ([`theme/paper.json`](../theme/paper.json), installed to
`~/.claude/themes/`) is `light-ansi` with its prompt and bash backgrounds set to
the paper colour. `light-ansi` paints them with ANSI white, which the light
palette makes near-black, and Claude's built-in `light` theme uses fixed
colours that wash out on the paper.

`--restart` restarts Herdr four seconds later. The Herdr server caches the
terminal background it saw at startup and paints it into Claude panes, so a
switch is only complete after a restart. The delay lets the calling pane print
before the restart kills it.

### Install

```bash
cp theme/term-theme ~/.claude/scripts/ && chmod +x ~/.claude/scripts/term-theme
mkdir -p ~/.claude/themes && cp theme/paper.json ~/.claude/themes/
```

It finds your Windows home by asking `cmd.exe` for `%USERPROFILE%`. Set
`WIN_HOME` (a WSL path such as `/mnt/c/Users/you`) or `WEZTERM_CONFIG` to skip
the lookup. The Windows Terminal step edits a scheme named "Monokai Cursor";
rename it in the script to match yours, or ignore the
`windows terminal not updated` notice.

The [`/dark` and `/light` skills](skills.md) and the
[Stream Deck theme key](../streamdeck/README.md) both call `term-theme`.
