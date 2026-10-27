#!/usr/bin/env python3
"""WSL side of the Stream Deck plugin. The plugin runs it through wsl.exe and
talks to it over stdin/stdout, so nothing listens on a port.

Commands on stdin, one per line:
  focus             focus the agent that most needs you (blocked, then done, then idle)
  theme             flip light <-> dark
  refresh           re-emit the current state

Emits one JSON line on stdout whenever the state changes:
  {"blocked": [...], "done": [...], "idle": [...], "working": n, "theme": "dark"}
where blocked/done/idle are lists of {"pane": id, "title": str}.
"""
import json
import os
import re
import select
import subprocess
import sys

HERDR = os.path.expanduser("~/.local/bin/herdr")
TERM_THEME = os.path.expanduser("~/.claude/scripts/term-theme")
# WezTerm config on the Windows side; term-theme resolves the same default.
WEZ = os.environ.get("WEZTERM_CONFIG") or (
    subprocess.run(["wslpath", subprocess.run(
        ["/mnt/c/Windows/System32/cmd.exe", "/c", "echo %USERPROFILE%"],
        capture_output=True, text=True).stdout.strip()],
        capture_output=True, text=True).stdout.strip() + "/.wezterm.lua")
POLL = 1.0

last = None
# A pane jumped to stays out of the queue until it changes state, so repeated
# presses walk through every agent that needs you instead of the same one.
visited = {}


def agents():
    out = subprocess.run([HERDR, "agent", "list"], capture_output=True, text=True, timeout=10)
    if out.returncode:
        raise RuntimeError(out.stderr.strip() or "herdr agent list failed")
    return json.loads(out.stdout)["result"]["agents"]


def theme():
    try:
        m = re.search(r"^local mode = '([a-z]+)'", open(WEZ).read(), re.M)
        return m.group(1) if m else "unknown"
    except OSError:
        return "unknown"


def state():
    s = {"blocked": [], "done": [], "idle": [], "working": 0, "theme": theme(), "error": None}
    try:
        for a in agents():
            st = a.get("agent_status")
            if st in ("blocked", "done", "idle"):
                s[st].append({"pane": a["pane_id"], "title": a.get("terminal_title_stripped") or a["pane_id"]})
            elif st == "working":
                s[st] += 1
    except Exception as e:  # herdr down or restarting: show it on the key, keep running
        s["error"] = str(e)[:200]
    return s


def emit(force=False):
    global last
    s = state()
    line = json.dumps(s)
    if force or line != last:
        print(line, flush=True)
        last = line
    return s


def focus():
    s = state()
    # Idle agents are ready for a prompt, so they come last rather than never.
    queue = s["blocked"] + s["done"] + s["idle"]
    status = {a["pane"]: st for st in ("blocked", "done", "idle") for a in s[st]}
    for pane in list(visited):
        if visited[pane] != status.get(pane):
            del visited[pane]
    target = next((a for a in queue if a["pane"] not in visited), None)
    if target is None and queue:  # walked them all: start over
        visited.clear()
        target = queue[0]
    if target:
        visited[target["pane"]] = status[target["pane"]]
        subprocess.run([HERDR, "agent", "focus", target["pane"]], capture_output=True, timeout=10)
        print(json.dumps({"focused": target}), flush=True)


def flip():
    mode = "light" if theme() == "dark" else "dark"
    subprocess.run([TERM_THEME, mode], capture_output=True, timeout=30)


def main():
    emit(force=True)
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], POLL)
        if ready:
            line = sys.stdin.readline()
            if not line:
                return  # plugin went away
            cmd = line.split()
            try:
                if cmd[:1] == ["focus"]:
                    focus()
                elif cmd[:1] == ["theme"]:
                    flip()
                emit(force=cmd[:1] == ["refresh"])
            except Exception as e:
                print(json.dumps({"error": str(e)[:200]}), flush=True)
        else:
            emit()


if __name__ == "__main__":
    main()
