import unittest

from dispatch import grid_split


def pane(pid, x, y, w, h):
    return {"pane_id": pid, "rect": {"x": x, "y": y, "width": w, "height": h}}


def grow(width, height, n):
    """Split a width x height tab n-1 times the way new_pane does."""
    panes = [pane("p0", 0, 0, width, height)]
    for i in range(1, n):
        target, direction = grid_split(panes)
        p = next(p for p in panes if p["pane_id"] == target)
        r = p["rect"]
        if direction == "right":
            half = r["width"] // 2
            new = pane(f"p{i}", r["x"] + half, r["y"], r["width"] - half, r["height"])
            r["width"] = half
        else:
            half = r["height"] // 2
            new = pane(f"p{i}", r["x"], r["y"] + half, r["width"], r["height"] - half)
            r["height"] = half
        panes.append(new)
    return panes


def shape(panes):
    """(columns, rows) of the grid, from the distinct x and y positions."""
    return (len({p["rect"]["x"] for p in panes}), len({p["rect"]["y"] for p in panes}))


class GridSplit(unittest.TestCase):
    def test_second_pane_goes_beside_on_a_wide_tab(self):
        self.assertEqual(grid_split([pane("a", 0, 0, 257, 61)]), ("a", "right"))

    def test_second_pane_goes_below_on_a_tall_tab(self):
        self.assertEqual(grid_split([pane("a", 0, 0, 80, 80)]), ("a", "down"))

    def test_splits_the_biggest_pane(self):
        panes = [pane("small", 0, 0, 64, 30), pane("big", 64, 0, 128, 61)]
        self.assertEqual(grid_split(panes)[0], "big")

    def test_ties_go_to_the_top_left(self):
        panes = [pane("b", 128, 0, 128, 30), pane("a", 0, 0, 128, 30)]
        self.assertEqual(grid_split(panes)[0], "a")

    def test_four_workers_make_a_two_by_two_not_four_columns(self):
        self.assertEqual(shape(grow(257, 61, 4)), (2, 2))

    def test_three_workers_are_two_columns(self):
        self.assertEqual(shape(grow(257, 61, 3)), (2, 2))  # one full-height column, one split

    def test_never_a_pile_of_skinny_columns(self):
        for n in range(2, 9):
            for p in grow(257, 61, n):
                self.assertGreaterEqual(p["rect"]["width"], 50, n)


if __name__ == "__main__":
    unittest.main()
