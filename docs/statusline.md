# Statusline

[← back to README](../README.md)

A Claude Code `statusLine` command that answers one question first — **which
pool is paying for this session?** — and then fills in everything else worth a
glance: context window, 5-hour and weekly limits, the Fable sub-cap, plan
credits, session cost and burn rate, git state and the open PR.

- [Reading it](#reading-it)
- [Rows](#rows)
- [Install](#install)
- [The scraper (optional)](#the-scraper-optional)
- [Staleness](#staleness)
- [Troubleshooting](#troubleshooting)

## Reading it

The first column marks billing:

| Marker | Meaning |
|---|---|
| <code>▸</code> green | **Plan quota.** The rolling 5-hour and 7-day limits. Free at the point of use. |
| <code>▸</code> yellow | **Plan credits.** The usage-credit overflow that takes over when either limit hits 100%. Real money. |
| <code>▸</code> red | **API credits.** A Console account billed per token, for API-key sessions. |
| <code>○</code> | A pool that exists but isn't paying for this session. |
| <code>∙</code> | Not a billing pool: context window, cost estimate. |

Quota and plan credits are a sequence (spend flows from one into the other at
100%). API credits are an alternative to both. So only one pool is ever lit,
and a `◂ billing here` note sits on that row.

The Fable row is lit only while the session itself runs on Fable. Other models
draw on "All models" alone.

How the paying pool is worked out, since the payload has no "you are billing
to X" field:

1. `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in the environment → **API**.
2. Otherwise `rate_limits` in the payload means a subscription. Either bucket
   at 100% → **credits**, else **quota**.
3. Non-zero cost but no `rate_limits` → **API** (a key from stored
   credentials rather than the environment).
4. Nothing billed yet → nothing is marked, rather than a guess.

## Rows

| Row id | Shows | Source |
|---|---|---|
| `context` | Context window used; input, output and cached tokens | payload |
| `session` | 5-hour limit, labelled with the plan | payload |
| `weekly` | 7-day limit ("All models") | payload |
| `fable` | Fable's sub-cap of the weekly limit | scraper |
| `cost` | Session cost, $/hr, lines changed, duration | payload |
| `plan_credits` | Usage-credit overflow: spent / limit, prepaid balance | scraper |
| `rl:<key>[=Label]` | Any other `rate_limits` bucket | payload |

Choose rows and their order with `STATUSLINE_ROWS`. The default is
`context,session,weekly,fable,cost,plan_credits`.

```bash
STATUSLINE_ROWS=context,session,weekly,cost   # payload only, no scraper needed
STATUSLINE_ROWS=session,weekly,rl:opus=Opus   # render a bucket the payload happens to carry
```

Always drawn as well:

- **Header:** the Herdr sound state (`🔊 sound on` or `🔇 muted · 42m left`; see
  [Herdr](herdr.md#mute-for-an-hour)) and the session name.
- **Footer:** the model and its configuration (`1M context · effort high ·
  thinking · fast`), repo, branch with `●` when dirty and `↑`/`↓` against
  upstream, and the open PR coloured by review state.

The `cost` row is Claude Code's own client-side estimate and resets on
`/clear`, so it gets no bar and a note saying so, to keep it apart from billed
figures.

Every time the 5-hour or weekly figure moves, a snapshot is appended to
`$CLAUDE_LIMITS_DIR/limits.jsonl` (default `~/.local/share/claude-limits`) for
charting later. Failures there never touch the render.

## Install

1. Copy `statusline/statusline-command.sh` to `~/.claude/`.
2. Add the `statusLine` block from
   [`config/settings.example.json`](../config/settings.example.json) to
   `~/.claude/settings.json`.
3. Restart Claude Code.

`rate_limits` only appears for Pro/Max subscribers and only after the first API
response, so the quota rows are briefly missing at startup. They are left out
rather than drawn as zero.

| Variable | Default | Purpose |
|---|---|---|
| `STATUSLINE_ROWS` | see above | rows and order |
| `CLAUDE_USAGE_CACHE` | `~/.claude/claude-usage-cache.json` | scraper cache (handy for fixtures) |
| `CLAUDE_LIMITS_DIR` | `~/.local/share/claude-limits` | limit-history log |
| `HERDR_CONFIG_PATH` | `~/.config/herdr/config.toml` | where the mute state is read |

## The scraper (optional)

The payload carries the 5-hour and weekly buckets live. It carries **no money**
and **no Fable bucket**: the per-model cap ("up to 50% of your weekly limit")
was retired in September 2026 and came back in October, and Claude Code still
only knows legacy bucket names. Both exist only on `claude.ai/settings/usage`,
so `statusline/scripts/scrape_claude_usage.py` reads them every five minutes.

How it reads the page:

- **Stdlib Python, no Playwright.** A minimal DevTools-protocol client opens its
  own background tab, reads the page text and closes the tab. It never touches
  your tabs. (Playwright attaches to *every* tab, and one hung renderer stalled
  it for hours.)
- **A dedicated, windowless Chrome** with its own profile
  (`%LOCALAPPDATA%\ClaudeUsageChrome`). Chrome 136+ refuses
  `--remote-debugging-port` on the default profile, even when the path is
  passed explicitly. A second instance runs fine beside your everyday Chrome,
  so nothing ever needs to close your browser.
- **Not headless.** Cloudflare's challenge blocks headless Chrome even with a
  valid session.

Setup (WSL2):

1. Copy `statusline/scripts/*` to `~/.claude/scripts/`.
2. Add the `SessionStart` hook from
   [`config/settings.example.json`](../config/settings.example.json).
   `ensure_chrome_debug.sh` starts the scraper Chrome when :9222 is down
   (about 3 seconds) and never closes anything.
3. Run `bash ~/.claude/scripts/fix_usage_scrape.sh` once, then sign in to
   claude.ai in that Chrome (open it with
   `--user-data-dir=%LOCALAPPDATA%\ClaudeUsageChrome`).
4. Add the cron line from [`config/crontab.example`](../config/crontab.example).

The scraper never writes to stdout. `~/.claude/scripts/scrape_claude_usage.log`
gets one line per run: `OK 2 rows`, `FAIL no-cdp …`, `cdp-hung`, `LoggedOut`.

## Staleness

Cached numbers are never shown as live:

- **Per-row stamps.** Each cached row carries its own `_fetched_at`. A partial
  scrape merges over the cache, so without them a regex that silently stopped
  matching would keep its last value forever under a fresh overall timestamp.
  That is exactly how the first Fable row went unnoticed for weeks.
- **Inline marks.** A row older than the scrape as a whole is tagged
  `(row from 13d ago)`.
- **A warning line** names the failure and the fix when the cache is stale:

  ```
  ⚠ usage data 2d ago — Chrome not on debug port :9222  fix: bash ~/.claude/scripts/fix_usage_scrape.sh
  ```

  It only appears when a cached row is actually on screen.

The scraper fails closed: on any error it leaves the last good cache in place
and records why, rather than writing partial garbage.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `⚠ … Chrome not on debug port` | The scraper Chrome isn't running. `bash ~/.claude/scripts/fix_usage_scrape.sh` |
| `cdp-hung` in the log | The port answers but the browser doesn't. Same fix. |
| `LoggedOut` | Sign in to claude.ai again in the scraper profile. |
| Fable row missing | The usage page has no Fable cap right now, or the markup moved. Check the log for `OK` with fewer rows. |
| Quota rows missing | No API response yet this session, or an API-key session (which has no quotas). |
| Hooks can't find `powershell.exe` under Herdr | Herdr panes get no Windows PATH. The scripts call Windows binaries by absolute path for this reason. |

Caveats: Anthropic's markup changes and the regexes follow it. The "credit"
figure is a prepaid balance, not limit minus spent. A negative balance is
flagged `unpaid` only past $1 (below that it is settlement lag): red when that
pool is paying, yellow otherwise.
