#!/usr/bin/env python3
"""Print the last user prompt and last assistant text of a Claude session.
  last-turn.py <session-id> [max_chars]"""
import json, sys, glob, os
sid = sys.argv[1]; cap = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
if not paths:
    sys.exit(f"no transcript for {sid}")
last_user = last_asst = ""
for line in open(paths[0], errors="ignore"):
    try:
        e = json.loads(line)
    except Exception:
        continue
    if e.get("isSidechain"):
        continue
    m = e.get("message") or {}
    c = m.get("content")
    if e.get("type") == "user":
        if isinstance(c, str):
            last_user = c
        elif isinstance(c, list):
            t = " ".join(b.get("text", "") for b in c if b.get("type") == "text")
            if t.strip():
                last_user = t
    elif e.get("type") == "assistant" and isinstance(c, list):
        t = "\n".join(b.get("text", "") for b in c if b.get("type") == "text")
        if t.strip():
            last_asst = t
print("USER:", last_user.strip()[:600])
print("---")
print("ASSISTANT:", last_asst.strip()[-cap:])
