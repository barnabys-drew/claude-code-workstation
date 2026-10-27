#!/usr/bin/env bash
# Restore the Claude usage scrape when the statusline goes stale.
#
# Starts the dedicated usage-scraper Chrome (its own profile, no window) if
# :9222 is down, then runs the scraper and checks the cache really refreshed.
# Your normal Chrome is never closed.
#
#   bash ~/.claude/scripts/fix_usage_scrape.sh
set -u

DEBUG_PORT=9222
CHROME_WIN='C:\Program Files\Google\Chrome\Application\chrome.exe'
# Herdr's server is started by systemd, so its panes -- and everything under
# them, including Claude Code hooks -- inherit a PATH without the Windows
# directories WSL normally appends. Fall back to the absolute path so a missing
# PATH entry cannot silently disable Chrome management.
PS_EXE=$(command -v powershell.exe 2>/dev/null) \
  || PS_EXE=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
SCRAPER="$HOME/.claude/scripts/scrape_claude_usage.py"

# Playwright usually lives in a virtualenv rather than the system python. Rather
# than hardcode a path, take the first candidate that can actually import it:
# an explicit override, then whatever interpreter the cron entry already uses
# (so there is exactly one place to configure), then the system python.
pick_python() {
  local cron_py candidate
  cron_py=$(crontab -l 2>/dev/null | grep scrape_claude_usage \
    | grep -oE '/[^[:space:]]*python[0-9.]*' | head -1)
  for candidate in "${STATUSLINE_PYTHON:-}" "$cron_py" python3; do
    [ -n "$candidate" ] || continue
    if "$candidate" -c "import playwright" >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

say() { printf '%s\n' "$*" >&2; }

port_up() {
  curl -s --connect-timeout 2 "http://localhost:${DEBUG_PORT}/json/version" >/dev/null 2>&1
}

run_scraper() {
  local py
  if ! py=$(pick_python); then
    say "   no python with Playwright installed found."
    say "   Set STATUSLINE_PYTHON=/path/to/venv/bin/python3 and re-run."
    return 1
  fi
  say "-> running scraper ($py)..."
  "$py" "$SCRAPER"
  # Check the cache actually got NEW data. A failed scrape leaves the old file
  # perfectly readable, so "the file parses" proves nothing -- only a recent
  # updated_at does.
  local age
  age=$(python3 - "$HOME/.claude/claude-usage-cache.json" <<'PY' 2>/dev/null
import json, sys, time
try:
    with open(sys.argv[1]) as f:
        c = json.load(f)
    u = c.get("updated_at")
    print(-1 if not u else int(time.time() - u))
except Exception:
    print(-1)
PY
)
  age=${age:--1}
  if [ "$age" -ge 0 ] 2>/dev/null && [ "$age" -lt 120 ]; then
    say "   cache refreshed (${age}s ago)."
    return 0
  fi
  if [ "$age" -lt 0 ] 2>/dev/null; then
    say "   cache unreadable or never written."
  else
    say "   cache NOT refreshed -- still ${age}s old."
  fi
  return 1
}

if port_up; then
  say "Chrome is already on :${DEBUG_PORT} -- no restart needed."
  run_scraper && say "Done." || say "Scraper still failed; see ~/.claude/scripts/scrape_claude_usage.log"
  exit 0
fi

[ -x "$PS_EXE" ] || { say "powershell.exe not found at $PS_EXE; cannot manage Chrome."; exit 1; }

# The port lives on a dedicated windowless Chrome (its own profile), side by
# side with your normal Chrome -- see ensure_chrome_debug.sh for why. Starting
# it never requires closing anything.
say "-> starting the usage-scraper Chrome on :${DEBUG_PORT}..."
HEAL_SOURCE_ONLY=1 . "$HOME/.claude/scripts/ensure_chrome_debug.sh"
launch_chrome

for i in $(seq 1 20); do
  port_up && { say "   port ${DEBUG_PORT} up after ~$((i * 2))s."; break; }
  sleep 2
done

if ! port_up; then
  say "Chrome did not expose :${DEBUG_PORT}. Is the ClaudeUsageChrome profile still under %LOCALAPPDATA%?"
  exit 1
fi

if run_scraper; then
  say "Done. Statusline should read 'usage data updated just now'."
else
  say "Port is up but the scrape failed -- you may need to re-login to claude.ai"
  say "in that profile (open it with --user-data-dir=%LOCALAPPDATA%\\ClaudeUsageChrome). See scrape_claude_usage.log"
  exit 1
fi
