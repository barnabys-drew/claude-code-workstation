#!/usr/bin/env python3
"""
Scrapes claude.ai/settings/usage for the statusline: the plan name, the Fable
sub-cap of the weekly quota, and the plan's optional usage-credits overflow.
The session and weekly quotas come from the statusLine hook payload instead.

The Console (platform.claude.com/settings/billing) API-credit scrape was removed
on 2026-09-16: the Console account is no longer used, so it only ever reported
LoggedOut and kept the statusline in a permanent "partial" state.

Requires a real (non-headless) Chrome window already running with
--remote-debugging-port=9222, logged into claude.ai — headless browsers
get stopped by Cloudflare's bot challenge even with valid session cookies.
Never launches or kills Chrome itself; if the debug port isn't up, or a
session has expired, it just leaves the existing cache file (and its
staleness) alone.
"""
import base64
import json
import os
import re
import socket
import struct
import time
import urllib.error
import urllib.request

CACHE_FILE = os.path.expanduser("~/.claude/claude-usage-cache.json")
LOG_FILE = os.path.expanduser("~/.claude/scripts/scrape_claude_usage.log")
CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
LOG_MAX_BYTES = 256_000


class LoggedOut(Exception):
    """The page rendered its login screen. Raised rather than returned so main()
    records it as "<site>:LoggedOut" -- a timeout waiting for a heading that
    will never render said nothing about the actual fix, which is to sign in."""


def _next_month_first():
    """The spend line only says "this month", so the reset is the 1st of next."""
    t = time.localtime()
    month = 1 if t.tm_mon == 12 else t.tm_mon + 1
    return time.strftime("%b", time.strptime(str(month), "%m")) + " 1"


def log(status, detail=""):
    """One line per run. Silence was the original bug: cron fired every 5
    minutes for 50 hours against a closed debug port and left no trace, so the
    only symptom was a statusline quietly showing Friday's numbers."""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
            with open(LOG_FILE) as f:
                tail = f.readlines()[-500:]
            with open(LOG_FILE, "w") as f:
                f.writelines(tail)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"{stamp} {status}{(' ' + detail) if detail else ''}\n")
    except Exception:
        pass  # logging must never break the scrape


def parse_usage(text):
    """Plan name and the usage-credits pool.

    The session and weekly quota rows used to be parsed here too. They now come
    from the statusLine hook payload (rate_limits.five_hour / .seven_day), which
    is live and carries epoch reset times, so scraping them was strictly worse.

    The per-model "Fable" cap disappeared in September 2026 and came back by
    late October as a sub-limit of the weekly quota ("Up to 50% of your weekly
    limit"). The payload still has no bucket for it (CLI 2.1.311 knows only
    seven_day_opus/_sonnet/... keys), so it is scraped here. Its row carries
    _fetched_at like every other, so if it vanishes again the statusline flags
    it as stale instead of serving a frozen number.
    """
    result = {}
    # "Your usage" heads the panel, with the plan name on the next line. Match
    # the whole line: \w+ silently missed "Max (5x)" and left a stale "Pro".
    plan_m = re.search(r"Your usage\s*\n\s*([^\n]+?)\s*\n", text)
    if plan_m:
        result["plan"] = plan_m.group(1)

    # "Fable" / "Up to 50% of your weekly limit" / "Resets Friday 2:00 PM" /
    # "38% used". The cap line is optional so a reworded blurb still parses.
    fable_m = re.search(
        r"\nFable\s*\n(?:\s*(Up to [^\n]+)\n)?\s*Resets ([^\n]+)\n\s*(\d+(?:\.\d+)?)% used",
        text)
    if fable_m:
        result["fable"] = {
            "used_pct": float(fable_m.group(3)),
            "resets": fable_m.group(2).strip(),
            "cap": (fable_m.group(1) or "").strip() or None,
        }

    # The September 2026 redesign dropped the "$X spent / Resets <date> / N% used"
    # block and the "Plan usage limits" heading this used to anchor on. What is
    # left is the credit balance under "Usage credits" (after a one-line blurb)
    # and a single "$spent of $limit this month · Auto-reload on|off" line under
    # "Monthly spend limit", so used_pct is derived rather than scraped.
    balance_m = re.search(r"Usage credits\s*\n[^\n]*\n\s*(-?\$[\d,.]+)\s*\n", text)
    spend_m = re.search(
        r"Monthly spend limit\s*\n\s*\$([\d,.]+) of \$([\d,.]+) this month"
        r"(?:\s*·\s*Auto-reload (on|off))?", text, re.IGNORECASE)
    if spend_m:
        spent, limit = spend_m.group(1), spend_m.group(2)
        try:
            pct = round(100 * float(spent.replace(",", "")) / float(limit.replace(",", "")))
        except (ValueError, ZeroDivisionError):
            pct = 0
        result["credits"] = {
            "spent": spent,
            "limit": limit,
            "used_pct": pct,
            "resets": _next_month_first(),
            "balance": balance_m.group(1) if balance_m else None,
        }
        if spend_m.group(3):
            result["credits"]["auto_reload"] = spend_m.group(3).lower()
    return result


class CDPHung(Exception):
    """The debug port answers HTTP but the CDP command channel does not."""


class CDP:
    """Minimal stdlib CDP client over the browser WebSocket.

    Playwright's connect_over_cdp auto-attaches to EVERY open tab and waits for
    each to answer. One frozen or hung renderer (2026-10-11: a hung tab) made
    it time out, which this script logged as "no-cdp" for hours while the port
    was up. Attaching only to a tab we create ourselves sidesteps that, and
    never navigates any of the user's own tabs."""

    def __init__(self, timeout=10):
        # CDP_URL is a hardcoded loopback http:// constant, never user input.
        with urllib.request.urlopen(CDP_URL + "/json/version", timeout=3) as r:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            ws_url = json.load(r)["webSocketDebuggerUrl"]
        path = "/" + ws_url.split("/", 3)[3]
        self.sock = socket.create_connection(("127.0.0.1", CDP_PORT), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{CDP_PORT}\r\n"
             "Upgrade: websocket\r\nConnection: Upgrade\r\n"
             f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                raise CDPHung("handshake closed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise CDPHung("handshake refused")
        self.next_id = 0

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise CDPHung("socket closed")
            buf += chunk
        return buf

    def _recv_frame(self):
        b0, b1 = self._recv_exact(2)
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._recv_exact(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._recv_exact(8))[0]
        return b0 & 0x0F, self._recv_exact(n)

    def call(self, method, params=None, session=None, timeout=10):
        self.next_id += 1
        msg = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        payload = json.dumps(msg).encode()
        mask = os.urandom(4)
        n = len(payload)
        hdr = b"\x81" + (bytes([0x80 | n]) if n < 126 else
                         b"\xfe" + struct.pack(">H", n) if n < 65536 else
                         b"\xff" + struct.pack(">Q", n))
        self.sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        deadline = time.time() + timeout
        while True:  # skip events and other replies until ours arrives
            self.sock.settimeout(max(0.1, deadline - time.time()))
            try:
                op, data = self._recv_frame()
            except socket.timeout:
                raise CDPHung(f"{method} got no reply in {timeout}s")
            if op == 8:
                raise CDPHung("browser closed the socket")
            if op != 1:
                continue
            reply = json.loads(data)
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error'].get('message')}")
                return reply.get("result", {})

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


_READ_PAGE = ("JSON.stringify({t: document.title, u: location.href,"
              " b: document.body ? document.body.innerText : ''})")


def scrape_claude_ai(cdp):
    # A background tab of our own, so the user's tabs (and focus) are untouched.
    target = cdp.call("Target.createTarget", {"url": "about:blank", "background": True})["targetId"]
    try:
        session = cdp.call("Target.attachToTarget",
                           {"targetId": target, "flatten": True})["sessionId"]
        # Settings is a hash route now (claude.ai/new#settings/usage) and the
        # plain path redirects there.
        cdp.call("Page.navigate", {"url": "https://claude.ai/settings/usage"},
                 session=session, timeout=15)

        body_text, deadline = "", time.time() + 25
        while time.time() < deadline:
            time.sleep(0.5)
            try:
                res = cdp.call("Runtime.evaluate",
                               {"expression": _READ_PAGE, "returnByValue": True},
                               session=session, timeout=5)
                page = json.loads(res["result"]["value"])
            except (KeyError, ValueError, RuntimeError):
                continue  # mid-navigation; try again
            if "sign in" in page["t"].lower() or "/login" in page["u"]:
                raise LoggedOut()
            body_text = page["b"]
            idx = body_text.find("Usage credits")
            if idx != -1 and "Loading" not in body_text[idx:idx + 600]:
                break

        return parse_usage(body_text) or None
    finally:
        try:
            cdp.call("Target.closeTarget", {"targetId": target}, timeout=5)
        except Exception:
            pass


def record_status(status, detail=""):
    """Record a failed run into the cache WITHOUT touching updated_at, so the
    statusline can say *why* its numbers are old instead of only that they are.
    Bumping updated_at here would relabel stale data as fresh."""
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    cache["last_run"] = {"at": time.time(), "status": status, "detail": detail}
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cache, f)
        os.replace(tmp, CACHE_FILE)
    except Exception:
        pass


def main():
    try:
        cdp = CDP()
    except (OSError, urllib.error.URLError, KeyError, ValueError):
        # Nothing listening — the common failure: Chrome relaunched without
        # --remote-debugging-port. Leave the cache as-is.
        log("FAIL", "no-cdp (Chrome not on :9222) — run fix_usage_scrape.sh")
        record_status("no-cdp")
        return

    try:
        try:
            cdp.call("Browser.getVersion", timeout=5)
        except CDPHung as e:
            log("FAIL", f"cdp-hung (port up, browser not answering: {e})")
            record_status("cdp-hung", str(e))
            return

        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
        except Exception:
            cache = {}

        # Rows this scraper no longer produces. Without pruning they would sit
        # in the cache forever at whatever value they last held, since nothing
        # refreshes or reads them any more.
        for retired in ("current_session", "all_models", "console_credits"):
            cache.pop(retired, None)

        now = time.time()
        fetched, failed = [], []

        try:
            usage = scrape_claude_ai(cdp)
            if usage:
                # Stamp each row individually. cache.update() merges partial
                # results over old ones, so without per-row stamps a regex that
                # silently stops matching keeps serving a stale value forever
                # under a fresh top-level updated_at.
                for key, val in usage.items():
                    if isinstance(val, dict):
                        val["_fetched_at"] = now
                cache.update(usage)
                fetched.extend(k for k in usage if isinstance(usage[k], dict))
            else:
                failed.append("claude.ai:no-data")
        except Exception as e:
            failed.append(f"claude.ai:{type(e).__name__}")
    finally:
        cdp.close()

    if not fetched:
        log("FAIL", "no rows scraped — " + ", ".join(failed))
        record_status("no-data", detail=", ".join(failed))
        return

    cache["updated_at"] = now
    cache["last_run"] = {
        "at": now,
        "status": "partial" if failed else "ok",
        "fetched": sorted(fetched),
        "failed": failed,
    }
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f)
    os.replace(tmp, CACHE_FILE)

    if failed:
        log("PARTIAL", f"got {sorted(fetched)}; missed {failed}")
    else:
        log("OK", f"{len(fetched)} rows")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Previously a missing playwright install produced a cron traceback
        # nobody read; now any crash is logged and shown on the statusline.
        log("ERROR", f"{type(e).__name__}: {e}")
        record_status("error", f"{type(e).__name__}: {e}")
