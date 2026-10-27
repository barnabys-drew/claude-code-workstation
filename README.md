# claude-code-workstation

My [Claude Code](https://claude.com/claude-code) workstation, published whole:
a statusline that says which pool is paying for each session, the
Herdr + WezTerm setup that runs a grid of Claude panes on
WSL2, one-key light/dark theming, and a Stream Deck plugin that tells me when an
agent needs me.

Built on and for **WSL2 + Windows** (WezTerm and Chrome on the Windows side,
Claude Code and Herdr in Ubuntu). The statusline core is portable; most of the
rest assumes that split.

![statusline screenshot](assets/screenshot.png)

*Illustrative numbers, not real billing data. Taken before the Fable row
returned and the API-credits row was retired.*

| Folder | What | Install to |
|---|---|---|
| [`statusline/`](#statusline) | `statusLine` command + usage scraper and its Chrome helpers | `~/.claude/statusline-command.sh`, `~/.claude/scripts/` |
| [`herdr/`](#herdr) | Herdr config, mute toggle, focus-pane-N, WSL sound shim | `~/.config/herdr/config.toml`, `~/.local/bin/` |
| [`wezterm/`](#wezterm) | WezTerm config with both palettes | `%USERPROFILE%\.wezterm.lua` |
| [`theme/`](#lightdark) | `term-theme` switcher + Claude Code "paper" theme | `~/.claude/scripts/term-theme`, `~/.claude/themes/` |
| [`skills/`](#skills) | `/regrid`, `/dark`, `/light` Claude Code skills | `~/.claude/skills/` |
| [`streamdeck/`](#stream-deck) | Stream Deck plugin (Windows) | `npm run install-plugin` |
| [`config/`](config/) | Example `settings.json` hooks and crontab | merge into your own |

Paths in the examples use `/home/YOU`; substitute your own.

---

## Statusline

Answers one question first — **which pool is paying for this session?** — then
fills in context window, session and weekly limits, the Fable sub-cap, session
cost and burn rate, git state, open PR, and the Herdr mute state.

### Which pool is paying

| Marker | Meaning |
|---|---|
| <code>▸</code> green | **Plan quota** — the rolling 5-hour and 7-day limits. Free at the point of use. |
| <code>▸</code> yellow | **Plan credits** — the usage-credit overflow, which takes over when either limit hits 100%. Real money. |
| <code>▸</code> red | **API credits** — a Console account billed per token (API-key sessions). |
| <code>○</code> | A pool that exists but is not paying for this session. |
| <code>∙</code> | Not a billing pool — context window, session cost estimate. |

Quota and plan credits are a sequence; API credits are an alternative to both,
so only one `▸` is ever lit. The Fable row is lit only while the session runs on
Fable, since other models draw on "All models" alone.

The paying pool is inferred: `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` in the
environment is decisive, otherwise `rate_limits` in the payload marks a
subscription and its percentages pick quota vs. credits. Before the first API
response nothing is marked rather than guessed. `∙` is U+2219, not the middle
dot: Herdr reads a line starting with U+00B7 and ending in `…` as the Claude
spinner and would mark an idle pane as working forever.

### Where each row comes from

| Row id | Shows | Source |
|---|---|---|
| `context` | Context window used, token breakdown | payload |
| `session` | 5-hour limit | payload |
| `weekly` | 7-day limit ("All models") | payload |
| `fable` | Fable's sub-cap of the weekly limit | scraper |
| `cost` | Session cost, burn rate, lines changed, duration | payload |
| `plan_credits` | Usage-credit overflow | scraper |
| `rl:<key>[=Label]` | Any other `rate_limits` bucket | payload |

Default: `context,session,weekly,fable,cost,plan_credits`. Override with
`STATUSLINE_ROWS`; drop `fable` and `plan_credits` and the scraper is
unnecessary:

```json
{ "statusLine": { "type": "command",
  "command": "STATUSLINE_ROWS=context,session,weekly,cost bash /home/YOU/.claude/statusline-command.sh" } }
```

The footer always shows the model and its configuration (`effort`, `thinking`,
`fast`), repo, branch with `●` when dirty and `↑`/`↓` against upstream, and the
open PR coloured by review state. Above the rows sits a Herdr sound line
(`🔊 sound on` / `🔇 muted · 42m left`, see [Herdr](#herdr)).

Each time the 5-hour or weekly figure moves, a snapshot is appended to
`$CLAUDE_LIMITS_DIR/limits.jsonl` (default `~/.local/share/claude-limits`) for
charting. It never blocks or breaks the render.

### Why a scraper

The payload carries the 5-hour and weekly buckets live, with epoch reset times.
It does **not** carry money, and it has no bucket for the per-model Fable cap
("up to 50% of your weekly limit") — that cap was retired in September 2026 and
came back in October, and the CLI still only knows legacy keys. Both exist only
on `claude.ai/settings/usage`, so `scripts/scrape_claude_usage.py` reads them
on a cron.

It is stdlib Python (no Playwright). It attaches over the DevTools protocol to
a **dedicated, windowless Chrome** with its own profile
(`%LOCALAPPDATA%\ClaudeUsageChrome`), opens a background tab of its own, reads
the page text and closes the tab. Headless is not an option: Cloudflare's
challenge blocks it even with a valid session.

Why a dedicated instance: Chrome 136+ refuses `--remote-debugging-port` on the
default `User Data` directory, even when the path is passed explicitly. A
second Chrome with its own `--user-data-dir` runs fine beside your normal one,
so nothing ever has to close your browser.

### Install

1. Copy `statusline/statusline-command.sh` to `~/.claude/` and
   `statusline/scripts/*` to `~/.claude/scripts/`.
2. Merge [`config/settings.example.json`](config/settings.example.json) into
   `~/.claude/settings.json`. The `SessionStart` hook (`ensure_chrome_debug.sh`)
   starts the scraper Chrome if :9222 is down — about 3 seconds, never closes
   anything.
3. Run `bash ~/.claude/scripts/fix_usage_scrape.sh` once. It starts the
   instance; log into claude.ai in it (open it with
   `--user-data-dir=%LOCALAPPDATA%\ClaudeUsageChrome`).
4. Add the line from [`config/crontab.example`](config/crontab.example).

The scraper never writes to stdout: `~/.claude/scripts/scrape_claude_usage.log`
has one line per run (`OK 2 rows`, `FAIL no-cdp …`, `cdp-hung`). When the
statusline goes stale, `fix_usage_scrape.sh` is the whole recovery.

### Staleness

Cached rows carry their own `_fetched_at`. A partial scrape merges over the
cache, so without per-row stamps a regex that stops matching would serve its
last value forever under a fresh top-level timestamp — which is how the first
retired Fable row went unnoticed for weeks. Rows older than the scrape are
marked `(row from 13d ago)`, and a warning line names the failure and the fix.

Caveats: Anthropic's markup changes, and the regexes follow. The scraper fails
closed (keeps the last good cache) and says so. The "credit" figure is a
prepaid balance, not limit-minus-spent; a negative one is flagged `unpaid` past
$1, red on the pool that is paying.

---

## Herdr

[`herdr/config.toml`](herdr/config.toml) — only the settings that differ from
`herdr --default-config`:

- **Sidebar rows** show each Claude pane's session name (`terminal_title_stripped`)
  instead of four identical `w1 t1 / claude` entries.
- **Pine theme** for Herdr's own chrome, fixed in both light and dark, because a
  live reload only applies some tokens.
- **Sound + toasts** when an agent finishes or needs attention. Bring your own
  mp3 as `~/.config/herdr/sounds/notify.mp3`; none ships here.
- **`alt+1…9`** focuses the Nth agent row, **`prefix+alt+1…9`** the Nth pane
  of any kind, **`prefix+m`** mutes for an hour.

`herdr/bin/` (to `~/.local/bin/`):

| Script | Does |
|---|---|
| `herdr-toggle-toasts` | Flips toasts and sound together, records a one-hour deadline in `~/.cache/herdr-mute-until`, and starts a detached timer to unmute. The statusline shows the countdown and fires the unmute itself if the timer died (WSL restart). |
| `herdr-focus-pane N` | Focuses the Nth pane in reading order via the socket API (the CLI only moves by direction). |
| `mpg123` | Stand-in player so Herdr can play sounds on WSL with no audio packages: ffmpeg through WSLg's PulseAudio, falling back to Windows audio when WSLg's PulseServer hangs. Detaches, so Herdr's 15 s kill doesn't cut long clips. Needs a static `ffmpeg` in `~/.local/bin`. |

Herdr is started by systemd, so its panes (and every Claude Code hook under
them) get a PATH with no `/mnt/c` entries. Every script here calls Windows
binaries by absolute path for that reason.

## WezTerm

[`wezterm/wezterm.lua`](wezterm/wezterm.lua) opens straight into WSL and holds
both palettes (pine dark, bone-paper light); `term-theme` flips its
`local mode = …` line. Clipboard habits are Windows-like: Ctrl+C copies when
text is selected and interrupts otherwise, mouse release never overwrites the
clipboard (it was clobbering snipped screenshots), Ctrl+Shift+V sends a raw ^V
so Claude Code can paste an image, and Ctrl+click opens links through Herdr's
mouse capture.

## Light/dark

`theme/term-theme light|dark|status [--restart]` flips WezTerm, the Windows
Terminal scheme and Claude Code's theme together (`dark-ansi` in dark,
`custom:paper` in light — `paper.json` is light-ansi with backgrounds set to the
bone paper). `--restart` restarts Herdr four seconds later, since its server
caches the host background at startup. It finds your Windows home itself; set
`WIN_HOME` or `WEZTERM_CONFIG` to override.

## Skills

Copy each folder to `~/.claude/skills/`.

- **`/regrid`** — re-tiles the current Herdr tab into a near-square grid (4 → 2×2,
  6 → 3×2, never 3+1), keeping every process. `--dry-run` previews.
  Tests: `python3 -m unittest discover -s skills/regrid`.
- **`/dark`, `/light`** — run `term-theme` with `--restart`.

## Stream Deck

[`streamdeck/`](streamdeck/) is a Windows Stream Deck plugin ("Workstation
Deck"): a **Claude needs you** key (blocked agents flash red, done ones amber;
press to jump to the next, WezTerm comes to the front), the **light/dark**
switch, YouTube Music play/pause/skip and Chrome-only volume, a window
screenshot key, and a page of every `tailscale serve` service with up/down
status. See its [README](streamdeck/README.md); set `HERDR_BRIDGE` in
`src/config.ts` to your checkout first.

## License

MIT — see [LICENSE](LICENSE).
