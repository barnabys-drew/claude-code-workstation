#!/usr/bin/env bash
# SessionStart hook: makes sure Chrome's remote-debugging port is available
# for scrape_claude_usage.py (cron, every 5 min) to read Fable/Sonnet usage.
#
# The port is served by a DEDICATED, windowless Chrome instance with its own
# profile (%LOCALAPPDATA%\ClaudeUsageChrome, logged into claude.ai), running
# side by side with your normal Chrome. It never touches your normal Chrome.
#
# Why not your normal Chrome: Chrome 136+ refuses --remote-debugging-port on the
# default "User Data" directory, even when that path is passed explicitly. The
# flags on the taskbar pin and the HKCU link-handler override are therefore
# inert. (An earlier "fix" only appeared to work because Start-Process split
# the path at the space and silently ran a stray "Chrome\User" profile --
# that profile is what got moved to ClaudeUsageChrome.)
#
# Two Chromes with different --user-data-dir coexist fine, so healing never
# needs to close anything: if the port is down, start the instance.
#
# Test without touching anything:
#   HEAL_DRY_RUN=1 HEAL_FORCE_CHECK=1 bash ensure_chrome_debug.sh
set -u

DEBUG_PORT=9222
CHROME_WIN='C:\Program Files\Google\Chrome\Application\chrome.exe'
PROFILE_SUBDIR='ClaudeUsageChrome'
DRY_RUN="${HEAL_DRY_RUN:-0}"
# Herdr's server is started by systemd, so its panes -- and everything under
# them, including Claude Code hooks -- inherit a PATH without the Windows
# directories WSL normally appends. Fall back to the absolute path so a missing
# PATH entry cannot silently disable Chrome management.
PS_EXE=$(command -v powershell.exe 2>/dev/null) \
  || PS_EXE=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe

# A hook's JSON stdout is shown to the user; plain stderr is not.
notify() {
  python3 -c 'import json,sys; print(json.dumps({"systemMessage": sys.argv[1]}))' "$1" 2>/dev/null
  echo "[usage scraper] $1" >&2
}

port_up() {
  curl -s --connect-timeout 2 "http://localhost:${DEBUG_PORT}/json/version" >/dev/null 2>&1
}

# One string for -ArgumentList with the path quoted inside it: a list of
# separate args gets re-joined unquoted, and the path is split at any space.
launch_chrome() {
  "$PS_EXE" -NoProfile -Command "\$a = \"--remote-debugging-port=${DEBUG_PORT} --user-data-dir=\`\"\$env:LOCALAPPDATA\\${PROFILE_SUBDIR}\`\" --no-startup-window --no-first-run\"; Start-Process -FilePath '${CHROME_WIN}' -ArgumentList \$a" >/dev/null 2>&1
}

[ "${HEAL_SOURCE_ONLY:-0}" = "1" ] && return 0 2>/dev/null

if [ "${HEAL_FORCE_CHECK:-0}" != "1" ] && port_up; then
  exit 0
fi

[ -x "$PS_EXE" ] || exit 0

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] would start the ${PROFILE_SUBDIR} Chrome instance on :${DEBUG_PORT}"; exit 0
fi

launch_chrome
for _ in 1 2 3; do port_up && exit 0; sleep 1; done
port_up || notify "Started the usage-scraper Chrome but :${DEBUG_PORT} is not up yet. If the statusline stays stale, run: bash ~/.claude/scripts/fix_usage_scrape.sh"
exit 0
