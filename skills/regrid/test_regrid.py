import unittest

from regrid import pick_rows, row_sizes


class RowSizes(unittest.TestCase):
    def test_balanced_never_three_plus_one(self):
        self.assertEqual(row_sizes(4, 2), [2, 2])
        self.assertEqual(row_sizes(5, 2), [3, 2])
        self.assertEqual(row_sizes(7, 3), [3, 2, 2])

    def test_sums_to_pane_count(self):
        for n in range(1, 13):
            for rows in range(1, n + 1):
                self.assertEqual(sum(row_sizes(n, rows)), n)


class PickRows(unittest.TestCase):
    def test_wide_terminal(self):
        # Cells are ~2x taller than wide, so a wide area favours side-by-side.
        self.assertEqual(pick_rows(1, 209, 63), 1)
        self.assertEqual(pick_rows(2, 209, 63), 1)
        self.assertEqual(pick_rows(3, 209, 63), 1)
        self.assertEqual(pick_rows(4, 209, 63), 2)
        self.assertEqual(pick_rows(5, 209, 63), 2)
        self.assertEqual(pick_rows(6, 255, 71), 2)

    def test_tall_area_stacks(self):
        self.assertEqual(pick_rows(2, 60, 120), 2)

    def test_never_an_empty_row(self):
        for n in range(1, 13):
            rows = pick_rows(n, 200, 60)
            self.assertTrue(1 <= rows <= n)
            self.assertGreater(min(row_sizes(n, rows)), 0)


if __name__ == "__main__":
    unittest.main()
