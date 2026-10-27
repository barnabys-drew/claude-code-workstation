#!/usr/bin/env bash
# One-time setup for the workboard orchestrator. Run it yourself: it creates
# things on GitHub.
#   1. an empty PRIVATE issues repo (default <you>/workboard) to hold the items
#   2. a private Project "Workboard", linked to that repo
#   3. Status options and Repo/Session/Pane/Priority/Gate fields
#   4. ~/.config/workboard/config.json
#   5. links ~/.claude/workboard -> this folder and the /orchestrate skill
# Needs gh with the "project" scope: gh auth refresh -s project
#
#   bash orchestrator/setup.sh [issues-repo-name]
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
owner=$(gh api user -q .login)
issues="$owner/${1:-workboard}"

if gh repo view "$issues" >/dev/null 2>&1; then
  [ "$(gh repo view "$issues" --json isPrivate -q .isPrivate)" = true ] \
    || { echo "$issues exists and is PUBLIC; items must live in a private repo" >&2; exit 1; }
  echo "using existing private repo $issues"
else
  gh repo create "$issues" --private \
    --description "Private issues for the workboard orchestrator (claude-code-workstation)"
fi

number=$(gh project list --owner "$owner" --format json \
  -q '.projects[] | select(.title=="Workboard") | .number' | head -1)
if [ -z "$number" ]; then
  number=$(gh project create --owner "$owner" --title Workboard --format json -q .number)
fi
gh project link "$number" --owner "$owner" --repo "$issues" >/dev/null 2>&1 || true

python3 "$here/board.py" init "$number" "$issues"

mkdir -p ~/.claude/skills
ln -sfn "$here" ~/.claude/workboard
ln -sfn "$(dirname "$here")/skills/orchestrate" ~/.claude/skills/orchestrate
echo "Project: https://github.com/users/$owner/projects/$number"
echo "Skill:   /orchestrate (new Claude Code sessions pick it up)"
