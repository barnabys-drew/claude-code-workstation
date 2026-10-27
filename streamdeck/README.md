# workstation-deck

A Stream Deck plugin (Windows) with six keys:

| Key | Shows | Press |
|---|---|---|
| Claude needs you | Herdr agents that are `blocked` (red, flashing) or `done` (amber), otherwise how many are working | Jump to the next one (blocked, then done, then idle): Herdr focuses the pane, WezTerm comes to the front. Repeated presses walk the queue |
| Light / dark | Current terminal theme | `term-theme` flip. Herdr's own chrome is fixed in both modes, so no restart is needed |
| Play / pause | Chrome's media session: state, title, artist | Toggle play/pause |
| Volume up / down | Chrome's mixer volume | ±5%, hold to repeat. Only Chrome's slider moves |
| Services | How many `tailscale serve` services answer | Opens a page linking each one with status and latency |

## How it fits together

```
Stream Deck ── plugin.js (Node, Windows)
                 ├─ wsl.exe … bridges/herdr-bridge.py    herdr agent list / focus, term-theme
                 ├─ powershell bridges/windows-bridge.ps1  media session, per-app volume, raise window
                 └─ tailscale.exe serve status --json + fetch, for the services page
```

Bridges are long-lived processes speaking JSON lines on stdin/stdout. Nothing
listens on a port. The herdr bridge runs from this checkout, so edits to it
take effect when the plugin next restarts it.

No album art: Windows PowerShell 5.1 can't read the media thumbnail stream,
and a standalone .NET Framework exe can't reach the media session service.

## Build and install

```
npm install
npm run check            # tsc
npm run install-plugin   # bundle, copy to %APPDATA%\Elgato\StreamDeck\Plugins, restart Stream Deck
```

Paths (distro, bridge location, Tailscale, terminal process) are in `src/config.ts`.
