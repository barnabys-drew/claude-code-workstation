#!/usr/bin/env python3
"""Rebuild a Herdr tab's panes into a tidy, near-square grid.

Herdr has no "re-tile" command and `pane move` within one tab is a no-op, so
this parks every pane except one anchor in staging tabs, then moves each back
with a split whose ratio makes every row/column equal.

Usage: regrid.py [--tab TAB_ID] [--rows N] [--dry-run]
"""
import argparse
import json
import math
import os
import subprocess
import sys


def herdr(*args):
    p = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)}: {p.stderr.strip()}")
    return json.loads(p.stdout)["result"] if p.stdout.strip() else {}


def read_layout(tab):
    # `pane layout` wants a pane in the tab, so look one up first.
    panes = herdr("pane", "list")["panes"]
    in_tab = [p for p in panes if p["tab_id"] == tab]
    if not in_tab:
        sys.exit(f"no panes in tab {tab}")
    return herdr("pane", "layout", "--pane", in_tab[0]["pane_id"])["layout"]


def row_sizes(n, rows):
    base, extra = divmod(n, rows)
    return [base + (1 if i < extra else 0) for i in range(rows)]


def pick_rows(n, width, height):
    """Rows count whose panes look most square. A terminal cell is ~2x as
    tall as wide, so a visually square pane has width ~= 2 * height in cells."""
    best, best_score = 1, None
    for rows in range(1, n + 1):
        h = height / rows
        sizes = row_sizes(n, rows)
        if min(sizes) == 0:
            continue
        errs = []
        for size in sizes:
            errs += [abs(math.log((width / size) / (2 * h)))] * size
        score = sum(errs) / n
        if best_score is None or score < best_score - 1e-9:
            best, best_score = rows, score
    return best


def move_new_tab(pane):
    r = herdr("pane", "move", pane, "--new-tab", "--label", "regrid-stage", "--no-focus")
    return r["move_result"]["pane"]["pane_id"]


def move_split(pane, tab, target, direction, ratio):
    r = herdr("pane", "move", pane, "--tab", tab, "--split", direction,
              "--target-pane", target, "--ratio", f"{ratio:.4f}", "--no-focus")
    return r["move_result"]["pane"]["pane_id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", default=os.environ.get("HERDR_TAB_ID"))
    ap.add_argument("--rows", type=int, help="force this many rows")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.tab:
        sys.exit("not inside Herdr (no HERDR_TAB_ID); pass --tab")

    layout = read_layout(a.tab)
    if layout.get("zoomed") and not a.dry_run:
        herdr("pane", "zoom", "--pane", layout["panes"][0]["pane_id"], "--off")
    # Reading order keeps panes roughly where the user left them.
    panes = sorted(layout["panes"], key=lambda p: (p["rect"]["y"], p["rect"]["x"]))
    ids = [p["pane_id"] for p in panes]
    n = len(ids)
    if n < 2:
        print("nothing to do: one pane")
        return

    w, h = layout["area"]["width"], layout["area"]["height"]
    rows = a.rows or pick_rows(n, w, h)
    sizes = row_sizes(n, rows)
    grid, i = [], 0
    for s in sizes:
        grid.append(ids[i:i + s])
        i += s
    print(f"{n} panes in {w}x{h} cells -> {rows} rows: {sizes}")
    for r in grid:
        print("  " + " | ".join(r))
    if a.dry_run:
        return

    anchor = ids[0]
    staged = {}  # original id -> current id
    try:
        for pid in ids[1:]:
            staged[pid] = move_new_tab(pid)
        cur = {anchor: anchor}

        # Rows first: each split targets the pane that owns the remaining rows.
        row_heads = [anchor]
        for ri in range(1, rows):
            pid = grid[ri][0]
            k = rows - ri + 1  # rows still to share the target's region
            new = move_split(staged[pid], a.tab, row_heads[-1], "down", 1 / k)
            del staged[pid]
            cur[pid] = new
            row_heads.append(new)

        # Then columns inside each row.
        for ri, row in enumerate(grid):
            prev = row_heads[ri]
            for j in range(1, len(row)):
                pid = row[j]
                k = len(row) - j + 1
                new = move_split(staged[pid], a.tab, prev, "right", 1 / k)
                del staged[pid]
                cur[pid] = new
                prev = new
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        # Never strand a pane (and its running agent) in a staging tab.
        for pid, now in list(staged.items()):
            try:
                move_split(now, a.tab, anchor, "right", 0.5)
            except Exception as e2:
                print(f"could not restore {now}: {e2}", file=sys.stderr)
        sys.exit(1)

    final = read_layout(a.tab)
    for p in sorted(final["panes"], key=lambda p: (p["rect"]["y"], p["rect"]["x"])):
        r = p["rect"]
        print(f"{p['pane_id']:>8}  {r['width']}x{r['height']} at ({r['x']},{r['y']})")


if __name__ == "__main__":
    main()
