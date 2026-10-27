# Workstation Deck

[← back to README](../README.md)

A Stream Deck plugin for Windows that makes the deck a status panel for Claude
Code agents running in [Herdr](../docs/herdr.md), with a few desk conveniences
alongside. Key faces are drawn in code as SVG (`src/keys.ts`) and update live.

## Keys

| Key | Face shows | Press |
|---|---|---|
| **Claude needs you** | Agents that are blocked (red, flashing) or done (amber), otherwise how many are working | Jumps to the next one, blocked first, then done, then idle. Herdr focuses the pane and WezTerm comes to the front. Repeat presses walk the queue. |
| **Light / dark** | Current terminal theme | Flips it with [`term-theme`](../docs/terminal-and-theme.md#term-theme). |
| **Play / pause** | Chrome's media session: state, title, artist | Toggles playback (YouTube Music in my case). |
| **Next / previous** | | Tap for the next track, hold for the previous one. |
| **Volume up / down** | Chrome's own mixer volume | ±5%, hold to repeat. Only Chrome's slider moves, not the system volume. |
| **Window screenshot** | | Captures the window in front to the clipboard and `Pictures\Screenshots`. Pressing a deck key doesn't steal focus, so "in front" is the window you were using. |
| **Services** | How many `tailscale serve` services answer | Opens a page linking each one with up/down status and latency. |

## How it fits together

```
Stream Deck ── plugin.js (Node, Windows)
                 ├─ wsl.exe … bridges/herdr-bridge.py      herdr agent list / focus, term-theme
                 ├─ powershell bridges/windows-bridge.ps1  media session, per-app volume, raise window, screenshot
                 └─ tailscale.exe serve status --json      + fetch, for the services page
```

The bridges are long-lived processes that speak JSON lines over stdin/stdout,
so nothing listens on a port. The Herdr bridge runs straight from your
checkout, so edits to it take effect the next time the plugin restarts it.

There is no album art: Windows PowerShell 5.1 can't read the media thumbnail
stream, and a standalone .NET Framework exe can't reach the media session
service.

## Build and install

```bash
npm install
npm run check            # typecheck
npm run install-plugin   # bundle, copy to %APPDATA%\Elgato\StreamDeck\Plugins, restart Stream Deck
```

Before installing, set the machine-specific values in
[`src/config.ts`](src/config.ts):

| Constant | Default | Set to |
|---|---|---|
| `HERDR_BRIDGE` | `/home/YOU/code/claude-code-workstation/streamdeck/bridges/herdr-bridge.py` | that file in your checkout (a WSL path) |
| `DISTRO` | `Ubuntu` | your WSL distro |
| `TAILSCALE` | `C:\Program Files\Tailscale\tailscale.exe` | your Tailscale CLI |
| `TERMINAL_PROCESS` | `wezterm-gui` | the process to bring to the front |
| `MEDIA_APP` | `chrome` | the app whose media and volume the keys control |

Requires Stream Deck 7.1+ (it runs plugins on Node 24) and Windows 10+.
