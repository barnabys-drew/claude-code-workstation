#!/usr/bin/env python3
"""Regenerate assets/screenshot.png from the real statusline and fake data.

Runs statusline/statusline-command.sh against a synthetic payload and usage
cache (two scenarios), converts the ANSI output to HTML in the WezTerm dark
palette, and screenshots it with headless Chromium. Nothing here reads real
billing data, so the image is safe to publish.

    python3 docs/screenshot/render.py      # needs: pip install playwright
"""
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATUSLINE = os.path.join(ROOT, "statusline", "statusline-command.sh")
OUT = os.path.join(ROOT, "assets", "screenshot.png")

# WezTerm "dark" palette (wezterm/wezterm.lua), so the image matches the setup.
BG, FG = "#1B2A20", "#EDE6D6"
ANSI = {"30": "#2A3B2F", "31": "#E07A5F", "32": "#B5D86B", "33": "#D4B483",
        "34": "#8FC9B0", "35": "#D9A989", "36": "#BFE3CE", "37": "#EDE6D6",
        "90": "#8E9B88"}

NOW = time.time()

SCENARIOS = [
    {
        "title": "On Fable, inside the plan quota",
        "payload": {
            "session_name": "add-retry-to-webhook-client",
            "model": {"id": "claude-fable-5-1", "display_name": "Fable 5.1"},
            "effort": {"level": "high"}, "thinking": {"enabled": True},
            "rate_limits": {"five_hour": {"used_percentage": 34, "resets_at": NOW + 3 * 3600 + 720},
                            "seven_day": {"used_percentage": 58, "resets_at": NOW + 3 * 86400}},
            "pr": {"number": 42, "review_state": "approved"},
        },
        "fable": 41,
        "credits": ("0.00", "25"),
    },
    {
        "title": "Quota spent: overflowing to plan credits",
        "payload": {
            "session_name": "add-retry-to-webhook-client",
            "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
            "effort": {"level": "medium"}, "thinking": {"enabled": True},
            "rate_limits": {"five_hour": {"used_percentage": 100, "resets_at": NOW + 69 * 60},
                            "seven_day": {"used_percentage": 88, "resets_at": NOW + 3 * 86400}},
            "pr": {"number": 42, "review_state": "approved"},
        },
        "fable": 50,
        "credits": ("18.40", "50"),
    },
]

COMMON = {
    "context_window": {"used_percentage": 22, "context_window_size": 1_000_000,
                       "total_input_tokens": 220_400, "total_output_tokens": 4_120,
                       "current_usage": {"cache_read_input_tokens": 214_900}},
    "cost": {"total_cost_usd": 4.82, "total_duration_ms": 5_460_000,
             "total_lines_added": 156, "total_lines_removed": 23},
    "workspace": {"repo": {"owner": "acme", "name": "webhook-client"}},
}


def ansi_to_html(text):
    out, style = [], {}
    for part in re.split(r"(\x1b\[[0-9;]*m)", text):
        m = re.fullmatch(r"\x1b\[([0-9;]*)m", part)
        if m:
            for code in (m.group(1) or "0").split(";"):
                if code == "0":
                    style = {}
                elif code == "1":
                    style["bold"] = True
                elif code in ANSI:
                    style["color"] = ANSI[code]
            continue
        if not part:
            continue
        css = []
        if "color" in style:
            css.append(f"color:{style['color']}")
        if style.get("bold"):
            css.append("font-weight:700")
        esc = html.escape(part)
        out.append(f'<span style="{";".join(css)}">{esc}</span>' if css else esc)
    return "".join(out)


def render(scn, tmp):
    repo = os.path.join(tmp, "webhook-client")
    if not os.path.isdir(repo):
        subprocess.run(["git", "init", "-q", "-b", "feat/retry-backoff", repo], check=True)
        open(os.path.join(repo, "dirty.txt"), "w").close()  # shows the ● marker
    cache = os.path.join(tmp, "cache.json")
    spent, limit = scn["credits"]
    with open(cache, "w") as f:
        json.dump({"updated_at": NOW - 60, "plan": "Max (5x)",
                   "fable": {"used_pct": scn["fable"], "resets": "Friday 2:00 PM",
                             "cap": "Up to 50% of your weekly limit", "_fetched_at": NOW - 60},
                   "credits": {"spent": spent, "limit": limit,
                               "used_pct": round(100 * float(spent) / float(limit)),
                               "resets": "Nov 1", "balance": "$0", "_fetched_at": NOW - 60}}, f)
    payload = {**COMMON, **scn["payload"],
               "workspace": {**COMMON["workspace"], "current_dir": repo}}
    env = {**os.environ, "CLAUDE_USAGE_CACHE": cache,
           "CLAUDE_LIMITS_DIR": os.path.join(tmp, "limits"),
           "HERDR_CONFIG_PATH": os.path.join(tmp, "no-herdr.toml")}
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    res = subprocess.run(["bash", STATUSLINE], input=json.dumps(payload), env=env,
                         capture_output=True, text=True, check=True)
    return res.stdout.rstrip("\n")


def main():
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp:
        blocks = []
        for scn in SCENARIOS:
            blocks.append(f'<div class="t">{html.escape(scn["title"])}</div>'
                          f'<pre>{ansi_to_html(render(scn, tmp))}</pre>')
    page_html = f"""<!doctype html><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500;700&family=Noto+Color+Emoji&display=block" rel="stylesheet">
<style>
body {{ margin:0; background:{BG}; color:{FG}; }}
#shot {{ display:inline-block; padding:22px 26px 10px; background:{BG}; }}
pre {{ margin:0 0 22px; font:500 15px/1.5 'JetBrains Mono','DejaVu Sans Mono','Noto Color Emoji',monospace; }}
.t {{ font:700 13px/1 'JetBrains Mono','DejaVu Sans Mono',monospace; color:{ANSI['90']};
      text-transform:uppercase; letter-spacing:.08em; margin:0 0 10px; }}
</style><div id="shot">{''.join(blocks)}</div>"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2, viewport={"width": 1400, "height": 900})
        page.set_content(page_html, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.locator("#shot").screenshot(path=OUT)
        browser.close()
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
