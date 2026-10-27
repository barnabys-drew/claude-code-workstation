---
name: regrid
description: "Re-tile the current Herdr tab's panes into a tidy, near-square grid (e.g. 4 panes -> 2x2, 6 -> 3x2). Use when the user says regrid, tidy/fix/reset the panes, or panes are a pile of skinny columns. Requires HERDR_ENV=1."
---

# regrid

Rebuilds the current Herdr tab's pane layout as an even grid so panes are as
square as possible. Running processes and agents are kept; only geometry changes.

## Run

```bash
test "${HERDR_ENV:-}" = 1 || { echo "not inside Herdr"; exit 1; }
python3 ~/.claude/skills/regrid/regrid.py --dry-run   # preview the grid
python3 ~/.claude/skills/regrid/regrid.py             # apply to the current tab
```

Options: `--tab w1:t2` (another tab), `--rows N` (force row count).

## How it works

- Picks the row count whose panes are closest to visually square (terminal
  cells are ~2x taller than wide, so square means width ~= 2 x height).
- Rows are balanced (4 -> 2+2, 5 -> 3+2), never 3+1.
- Keeps reading order (top-left to bottom-right) so panes stay near where they were.
- Herdr cannot re-tile, and `pane move` inside one tab is a no-op. The script
  parks every pane but the top-left in staging tabs, then moves each back with
  `--split` and `--ratio 1/k` so every row/column ends up equal.
- On error it moves any parked pane back, so none is stranded in a staging tab.

## Notes

- Panes briefly vanish and reappear (about a second); this is expected.
- Zoomed tabs are un-zoomed first.
- It moves the user's panes, so only run it when asked to regrid.
