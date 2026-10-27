#!/usr/bin/env python3
"""Pane mechanics for the orchestrator: start, message, read and release the
Claude panes that work board items. Decisions stay with the orchestrator;
this only does what it is told.

    dispatch.py start <n>              open a pane for item n, hand it the brief
    dispatch.py send <n> <text>        message item n's pane (reopens it from its session if closed)
    dispatch.py nudge <n>              send "proceed" unless the hourly nudge budget is spent
    dispatch.py last <n>               the pane's last reply and its STATUS footer
    dispatch.py release <n>            /exit the pane and close it (the session is kept)
    dispatch.py panes                  item -> pane map with live agent state

Panes open in one Herdr tab labelled "workboard". State lives in
~/.local/state/workboard/.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board  # noqa: E402

STATE = board.STATE_DIR
PANES = os.path.join(STATE, "panes.json")      # {"<n>": "<pane id>"}
TAB = os.path.join(STATE, "tab.json")          # {"tab": "<tab id>"}
NUDGES = os.path.join(STATE, "nudges.json")    # {"<n>": [epoch, ...]}
BRIEFS = os.path.join(STATE, "briefs")

PROTOCOL = """\
## How to work this item

You were started by the workboard orchestrator, not by a person typing. Work
on your own toward the goal above; the orchestrator reads your replies and
keeps you moving.

- Be terse: do the work, then report results and blockers. No recaps or
  option menus unless asked.
- Never do anything public, paid or outward-facing yourself: pushing to a
  public repo, posting, submitting, sending messages or email, spending money,
  changing DNS or cloud resources. Stop and ask instead (needs-decision).
- Follow the repo's CLAUDE.md and the user's global rules (git, public-repo
  data hygiene).
- Before stopping, commit your work as those rules allow.

End EVERY reply with exactly one final line in one of these forms:

    STATUS: continuing — <the next step you will take>
    STATUS: needs-decision — <the question, the options, and your recommendation>
    STATUS: done — <one-line result>
"""

FOOTER = re.compile(r"^\s*\**STATUS:?\**\s*(continuing|needs-decision|done)\b\s*[—:-]*\s*(.*)$",
                    re.IGNORECASE | re.MULTILINE)


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def herdr(*args, check=True):
    res = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if check and res.returncode:
        sys.exit(f"herdr {' '.join(args[:2])}: {(res.stderr or res.stdout).strip()}")
    try:
        return json.loads(res.stdout)
    except ValueError:
        return {"raw": res.stdout, "error": res.stderr, "code": res.returncode}


def agents():
    return {a["pane_id"]: a for a in herdr("agent", "list")["result"]["agents"]}


def live_panes():
    """Item -> pane for panes that still exist; dead entries are dropped."""
    panes, alive = load(PANES, {}), agents()
    kept = {n: p for n, p in panes.items() if p in alive}
    if kept != panes:
        save(PANES, kept)
    return kept, alive


def repo_path(cfg, repo):
    path = os.path.expanduser(cfg.get("repo_paths", {}).get(repo) or f"~/code/{repo}")
    if not os.path.isdir(path):
        sys.exit(f"repo checkout not found: {path} (add it to repo_paths in config.json)")
    return path


def new_pane(cwd):
    """A shell pane in the workboard tab, creating the tab if needed."""
    tab = load(TAB, {}).get("tab")
    if tab and herdr("tab", "get", tab, check=False).get("result"):
        last = [p["pane_id"] for p in herdr("pane", "list")["result"]["panes"]
                if p.get("tab_id") == tab]
        if last:
            return herdr("pane", "split", last[-1], "--direction", "right",
                         "--cwd", cwd)["result"]["pane"]["pane_id"]
    res = herdr("tab", "create", "--label", "workboard", "--cwd", cwd, "--no-focus")["result"]
    save(TAB, {"tab": res["tab"]["tab_id"]})
    return res["root_pane"]["pane_id"]


def start_claude(pane, name, *claude_args):
    herdr("agent", "start", name, "--kind", "claude", "--pane", pane,
          "--timeout", "60000", "--", *claude_args)


def session_of(pane, wait=30):
    deadline = time.time() + wait
    while time.time() < deadline:
        a = agents().get(pane) or {}
        sid = (a.get("agent_session") or {}).get("value")
        if sid:
            return sid
        time.sleep(1)
    return ""


def prompt(pane, text):
    # Wait until Herdr sees the pane start working. Otherwise the pane reads
    # "idle" for a moment after the prompt lands, watch.sh reports a stop that
    # never happened, and its transcript doesn't exist yet.
    res = herdr("agent", "prompt", pane, text, "--wait", "--until", "working",
                "--timeout", "20000", check=False)
    if res.get("code"):
        err = (res.get("error") or res.get("raw") or "").strip()
        if "stalled" in err or "timeout" in err:
            print(f"warning: pane {pane} took the prompt but was not seen working: {err}")
            return
        sys.exit(f"pane {pane} did not take the prompt: {err}")


def one_line(text):
    return " ".join(text.split())


# ---------- commands ----------

def start(n):
    cfg = board.load_config()
    item = board.find(cfg, n)
    panes, _ = live_panes()
    if str(n) in panes:
        sys.exit(f"#{n} already has pane {panes[str(n)]}")
    if len(panes) >= cfg.get("max_panes", 4):
        sys.exit(f"FULL: {len(panes)} panes busy (max_panes {cfg.get('max_panes', 4)})")
    cwd = repo_path(cfg, item["Checkout"])

    os.makedirs(BRIEFS, exist_ok=True)
    brief = os.path.join(BRIEFS, f"{n}.md")
    with open(brief, "w") as f:
        f.write(f"# Workboard #{n}: {item['title']}\n\nRepo: `{cwd}`  \n"
                f"Issue: {item['url']}  \nGate: {item['Gate'] or 'auto'}\n\n"
                f"## Goal\n\n{item['body'] or item['title']}\n\n{PROTOCOL}")

    pane = new_pane(cwd)
    start_claude(pane, f"wb-{n}")
    prompt(pane, f"[Orchestrator] You are working workboard item #{n}. "
                 f"Read your brief at {brief} and start.")
    sid = session_of(pane)
    panes[str(n)] = pane
    save(PANES, panes)
    board.set_fields(cfg, item["item_id"], Status="In progress", Pane=pane, Session=sid or None)
    board.gh("issue", "comment", str(n), "-R", cfg["repo"], "--body",
             f"{board.MARKER} started in pane `{pane}`" + (f", session `{sid}`" if sid else ""))
    print(f"#{n} -> pane {pane} session {sid or '?'}")


def send(n, text):
    cfg = board.load_config()
    if "\n" in text.strip() or len(text) > 400:
        # Multi-line text typed into a terminal can submit line by line, so it
        # goes through a file, like the brief.
        os.makedirs(BRIEFS, exist_ok=True)
        path = os.path.join(BRIEFS, f"{n}-msg-{int(time.time())}.md")
        with open(path, "w") as f:
            f.write(text.strip() + "\n")
        text = f"[Orchestrator] New message for item #{n} at {path}. Read it and continue."
    panes, alive = live_panes()
    pane = panes.get(str(n))
    if pane:
        if alive[pane]["agent_status"] == "working":
            sys.exit(f"pane {pane} is working; send when it settles")
        prompt(pane, text)
        print(f"sent to {pane}")
        return
    item = board.find(cfg, n)
    if not item["Session"]:
        sys.exit(f"#{n} has no pane and no session; use start")
    if len(panes) >= cfg.get("max_panes", 4):
        sys.exit("FULL: no free pane to resume into")
    pane = new_pane(repo_path(cfg, item["Checkout"]))
    start_claude(pane, f"wb-{n}", "--resume", item["Session"])
    prompt(pane, text)
    panes[str(n)] = pane
    save(PANES, panes)
    board.set_fields(cfg, item["item_id"], Pane=pane)
    print(f"resumed #{n} in {pane}")


def nudge(n):
    cfg = board.load_config()
    stamps = load(NUDGES, {})
    recent = [t for t in stamps.get(str(n), []) if t > time.time() - 3600]
    if len(recent) >= cfg.get("max_nudges_per_hour", 6):
        sys.exit(f"BUDGET: #{n} nudged {len(recent)} times this hour; escalate it")
    send(n, "[Orchestrator] Proceed.")
    stamps[str(n)] = recent + [time.time()]
    save(NUDGES, stamps)


def last(n):
    cfg = board.load_config()
    item = board.find(cfg, n)
    panes, alive = live_panes()
    sid = item["Session"] or (alive.get(panes.get(str(n), ""), {}).get("agent_session") or {}).get("value")
    if not sid:
        sys.exit(f"#{n} has no session yet")
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    if not paths:
        print("STATUS pending | no transcript yet; wait for the next event")
        return
    text = ""
    for line in open(paths[0], errors="ignore"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        c = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and not e.get("isSidechain") and isinstance(c, list):
            t = "\n".join(b.get("text", "") for b in c if b.get("type") == "text")
            if t.strip():
                text = t
    m = list(FOOTER.finditer(text))
    status = f"STATUS {m[-1].group(1).lower()} | {one_line(m[-1].group(2))}" if m else "STATUS none"
    pane = panes.get(str(n))
    state = alive.get(pane, {}).get("agent_status", "closed") if pane else "closed"
    print(f"{status}\nPANE {pane or '-'} {state}\n---\n{text.strip()[-3000:]}")


def release(n):
    cfg = board.load_config()
    panes, alive = live_panes()
    pane = panes.pop(str(n), None)
    if not pane:
        print(f"#{n} has no open pane")
        return
    if alive[pane]["agent_status"] == "working":
        sys.exit(f"pane {pane} is working; not closing it")
    herdr("agent", "prompt", pane, "/exit", check=False)  # saves the session
    time.sleep(4)
    herdr("pane", "close", pane, check=False)
    save(PANES, panes)
    item = board.find(cfg, n)
    board.set_fields(cfg, item["item_id"], Pane="")
    print(f"released {pane}")


def show_panes():
    panes, alive = live_panes()
    for n, p in sorted(panes.items(), key=lambda kv: int(kv[0])):
        print(f"#{n:<4} {p:<8} {alive[p]['agent_status']:<8} {alive[p].get('terminal_title_stripped', '')}")
    if not panes:
        print("no workboard panes open")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "start" and len(args) == 1:
        start(args[0])
    elif cmd == "send" and len(args) == 2:
        send(args[0], args[1])
    elif cmd == "nudge" and len(args) == 1:
        nudge(args[0])
    elif cmd == "last" and len(args) == 1:
        last(args[0])
    elif cmd == "release" and len(args) == 1:
        release(args[0])
    elif cmd == "panes":
        show_panes()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
