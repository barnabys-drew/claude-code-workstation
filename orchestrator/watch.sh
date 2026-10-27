#!/usr/bin/env bash
# Event stream for the orchestrator, run under Monitor. One line per thing it
# must act on, nothing while panes are busy:
#   PANE #<n> <pane> idle|done|blocked | <title>   a workboard pane stopped working
#   PANE #<n> <pane> gone                          its pane closed
#   BOARD READY #<n> new|resume <P> | <title>      from board.py poll
#   BOARD ANSWER #<n> | <title>                    you answered an item that Needs you
#
#   watch.sh [pane_interval_s] [board_interval_s]   (defaults 10 and 120)
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
panes_file="$HOME/.local/state/workboard/panes.json"
pane_every=${1:-10}
board_every=${2:-120}

prev=""
last_board=0
while true; do
  cur=$(herdr agent list 2>/dev/null | python3 -c '
import json, sys
try:
    agents = {a["pane_id"]: a for a in json.load(sys.stdin)["result"]["agents"]}
    panes = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for n, p in panes.items():
    a = agents.get(p)
    state = a["agent_status"] if a else "gone"
    title = (a or {}).get("terminal_title_stripped", "")
    print(f"{n}\t{p}\t{state}\t{title}")
' "$panes_file" | sort) || true

  # Report transitions out of "working" (and closes), not every poll.
  comm -13 <(echo "$prev") <(echo "$cur") | while IFS=$'\t' read -r n pane state title; do
    [ -z "$n" ] || [ "$state" = working ] && continue
    echo "PANE #$n $pane $state | $title"
  done
  prev="$cur"

  now=$(date +%s)
  if (( now - last_board >= board_every )); then
    python3 "$here/board.py" poll 2>&1 | sed '/^BOARD /!s/^/BOARD ERROR /'
    last_board=$now
  fi
  sleep "$pane_every"
done
