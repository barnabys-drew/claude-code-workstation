#!/usr/bin/env python3
"""The Workboard GitHub Project, from the command line.

Every work item is an issue in a private issues repo, added to the Project.
Issues live there (not in the repo the work happens in) so decision threads
about public repos never become public.

    board.py init <project-number> <owner/issues-repo>   one-time (setup.sh runs it)
    board.py list [--status S]            items with their fields
    board.py show <n>                     body, fields, comments
    board.py add --title T --repo R [--body B] [--status S] [--priority P1|P2|P3] [--gate auto|ask]
    board.py set <n> [--status S] [--session ID] [--pane ID] [--repo R] [--priority P] [--gate G]
    board.py comment <n> <text>           posted with the orchestrator marker
    board.py answer <n>                   your newest comment, if it postdates the orchestrator's
    board.py poll                         print board events since the last poll
"""
import argparse
import json
import os
import subprocess
import sys
import time

CONFIG = os.path.expanduser(os.environ.get("WORKBOARD_CONFIG") or "~/.config/workboard/config.json")
STATE_DIR = os.path.expanduser("~/.local/state/workboard")
POLL_STATE = os.path.join(STATE_DIR, "poll.json")

# Every comment the orchestrator posts starts with this, so a comment without
# it is yours. Both are posted with the same GitHub account, so the author
# can't tell them apart.
MARKER = "🤖 **Orchestrator:**"

STATUSES = ["Backlog", "Ready", "In progress", "Needs you", "Review", "Done"]
STATUS_COLORS = ["GRAY", "BLUE", "YELLOW", "RED", "PURPLE", "GREEN"]
STATUS_HELP = {
    "Backlog": "Not started; the orchestrator ignores it",
    "Ready": "Orchestrator may pick it up, or resume it if it has a session",
    "In progress": "A pane is working it",
    "Needs you": "Waiting on your decision: answer in a comment",
    "Review": "Finished; look it over",
    "Done": "Finished",
}
FIELDS = ("Status", "Checkout", "Session", "Pane", "Priority", "Gate")


def gh(*args, stdin=None):
    res = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if res.returncode:
        sys.exit(f"gh {' '.join(args[:3])}: {res.stderr.strip()}")
    return res.stdout


def gh_json(*args, stdin=None):
    return json.loads(gh(*args, stdin=stdin) or "null")


def load_config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit("no config.json: run setup.sh first")


# ---------- one-time setup ----------

def init(number, issues_repo):
    owner = gh_json("api", "user")["login"]
    proj = gh_json("project", "view", str(number), "--owner", owner, "--format", "json")

    def field_list():
        return gh_json("project", "field-list", str(number), "--owner", owner,
                       "--format", "json")["fields"]

    fields = {f["name"]: f for f in field_list()}
    # The built-in Status field ships with Todo / In Progress / Done.
    body = {"query": """
        mutation($f: ID!, $opts: [ProjectV2SingleSelectFieldOptionInput!]) {
          updateProjectV2Field(input: {fieldId: $f, singleSelectOptions: $opts}) {
            projectV2Field { ... on ProjectV2SingleSelectField { id } } } }""",
            "variables": {"f": fields["Status"]["id"],
                          "opts": [{"name": s, "color": c, "description": STATUS_HELP[s]}
                                   for s, c in zip(STATUSES, STATUS_COLORS)]}}
    gh("api", "graphql", "--input", "-", stdin=json.dumps(body))

    wanted = {"Checkout": ("TEXT", None), "Session": ("TEXT", None), "Pane": ("TEXT", None),
              "Priority": ("SINGLE_SELECT", "P1,P2,P3"), "Gate": ("SINGLE_SELECT", "auto,ask")}
    for name, (kind, opts) in wanted.items():
        if name in fields:
            continue
        args = ["project", "field-create", str(number), "--owner", owner,
                "--name", name, "--data-type", kind]
        if opts:
            args += ["--single-select-options", opts]
        gh(*args)

    cfg = {
        "owner": owner,
        "repo": issues_repo,
        "project_number": number,
        "project_id": proj["id"],
        "project_url": proj.get("url", ""),
        "fields": {f["name"]: {"id": f["id"],
                               "options": {o["name"]: o["id"] for o in f.get("options", [])}}
                   for f in field_list() if f["name"] in FIELDS},
        # Checkout field -> path. Anything not listed resolves to ~/code/<checkout>. ("Repo" is
        # reserved by GitHub for the built-in Repository field.)
        "repo_paths": {},
        "max_panes": 4,
        # Nudges ("proceed") per item per hour before it goes to Needs you.
        "max_nudges_per_hour": 6,
    }
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    print(f"wrote {CONFIG}")


# ---------- items ----------

def items(cfg):
    raw = gh_json("project", "item-list", str(cfg["project_number"]), "--owner", cfg["owner"],
                  "--format", "json", "--limit", "500")["items"]
    out = []
    for it in raw:
        c = it.get("content") or {}
        if c.get("type") != "Issue":
            continue
        low = {k.lower(): v for k, v in it.items()}
        out.append({"item_id": it["id"], "number": c["number"], "title": c.get("title", ""),
                    "url": c.get("url", ""), "body": c.get("body", ""),
                    **{k: low.get(k.lower()) or "" for k in FIELDS}})
    return out


def find(cfg, number):
    for it in items(cfg):
        if it["number"] == int(number):
            return it
    sys.exit(f"#{number} is not on the board")


def set_fields(cfg, item_id, **values):
    for name, value in values.items():
        if value is None:
            continue
        field = cfg["fields"][name]
        args = ["project", "item-edit", "--id", item_id, "--project-id", cfg["project_id"],
                "--field-id", field["id"]]
        if field["options"]:
            if value not in field["options"]:
                sys.exit(f"{name} must be one of: {', '.join(field['options'])}")
            args += ["--single-select-option-id", field["options"][value]]
        elif value == "":
            args += ["--clear"]
        else:
            args += ["--text", value]
        gh(*args)


def comments(cfg, number):
    return gh_json("issue", "view", str(number), "-R", cfg["repo"], "--json", "comments")["comments"]


def latest_answer(cfg, number):
    """Your newest comment, provided the orchestrator hasn't posted since."""
    for c in reversed(comments(cfg, number)):
        return None if c["body"].startswith(MARKER) else c
    return None


# ---------- polling ----------

def poll(cfg):
    """Print one line per board change the orchestrator must act on:
      BOARD READY #n new|resume P? | title   item moved into Ready
      BOARD ANSWER #n | title                you commented on an item that Needs you
    Costs one item-list call, plus one issue read per item in Needs you."""
    os.makedirs(STATE_DIR, exist_ok=True)
    try:
        with open(POLL_STATE) as f:
            prev = json.load(f)
    except (FileNotFoundError, ValueError):
        prev = {"status": {}, "answered": {}}
    status, answered = {}, dict(prev.get("answered", {}))
    for it in items(cfg):
        n = str(it["number"])
        status[n] = it["Status"]
        if it["Status"] == "Ready" and prev["status"].get(n) != "Ready":
            kind = "resume" if it["Session"] else "new"
            print(f"BOARD READY #{n} {kind} {it['Priority'] or '-'} | {it['title']}")
        if it["Status"] == "Needs you":
            ans = latest_answer(cfg, n)
            if ans and answered.get(n) != ans["id"]:
                answered[n] = ans["id"]
                print(f"BOARD ANSWER #{n} | {it['title']}")
    with open(POLL_STATE, "w") as f:
        json.dump({"status": status, "answered": answered, "at": time.time()}, f)


# ---------- CLI ----------

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("number", type=int); s.add_argument("issues_repo")
    s = sub.add_parser("list"); s.add_argument("--status")
    s = sub.add_parser("show"); s.add_argument("n")
    s = sub.add_parser("add")
    s.add_argument("--title", required=True); s.add_argument("--repo", required=True)
    s.add_argument("--body", default=""); s.add_argument("--status", default="Backlog")
    s.add_argument("--priority", default="P2"); s.add_argument("--gate", default="auto")
    s = sub.add_parser("set"); s.add_argument("n")
    for f in ("status", "session", "pane", "repo", "priority", "gate"):
        s.add_argument("--" + f)
    s = sub.add_parser("comment"); s.add_argument("n"); s.add_argument("text")
    s = sub.add_parser("answer"); s.add_argument("n")
    sub.add_parser("poll")
    a = p.parse_args()

    if a.cmd == "init":
        return init(a.number, a.issues_repo)
    cfg = load_config()
    if a.cmd == "list":
        rows = [i for i in items(cfg) if not a.status or i["Status"] == a.status]
        rows.sort(key=lambda i: (STATUSES.index(i["Status"]) if i["Status"] in STATUSES else 9,
                                 i["Priority"] or "P9", i["number"]))
        for i in rows:
            print(f"#{i['number']:<4} {i['Status'] or '-':<12} {i['Priority'] or '-':<3} "
                  f"{i['Gate'] or '-':<5} {i['Checkout'] or '-':<24} {i['title']}"
                  + (f"  [pane {i['Pane']}]" if i["Pane"] else ""))
    elif a.cmd == "show":
        i = find(cfg, a.n)
        print(json.dumps({k: v for k, v in i.items() if k != "body"}, indent=1))
        print("\n" + (i["body"] or "(no body)"))
        for c in comments(cfg, a.n):
            print(f"\n--- {c['author']['login']} {c['createdAt']}\n{c['body']}")
    elif a.cmd == "add":
        url = gh("issue", "create", "-R", cfg["repo"], "--title", a.title,
                 "--body", a.body or a.title).strip()
        item = gh_json("project", "item-add", str(cfg["project_number"]), "--owner", cfg["owner"],
                       "--url", url, "--format", "json")
        set_fields(cfg, item["id"], Status=a.status, Checkout=a.repo, Priority=a.priority, Gate=a.gate)
        print(url)
    elif a.cmd == "set":
        i = find(cfg, a.n)
        set_fields(cfg, i["item_id"], Status=a.status, Session=a.session, Pane=a.pane,
                   Checkout=a.repo, Priority=a.priority, Gate=a.gate)
    elif a.cmd == "comment":
        gh("issue", "comment", str(a.n), "-R", cfg["repo"], "--body", f"{MARKER} {a.text}")
    elif a.cmd == "answer":
        c = latest_answer(cfg, a.n)
        print(c["body"] if c else "")
    elif a.cmd == "poll":
        poll(cfg)


if __name__ == "__main__":
    main()
