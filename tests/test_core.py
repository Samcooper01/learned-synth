"""Unit tests for the parts of the harness that run without the chip flow.

Run from the repository root:  python3 -m unittest discover tests
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "harness"))

import recipes as rc                                    # noqa: E402
from harness import _fom                                # noqa: E402
from flagship_search import crossover, mutate           # noqa: E402

# resyn2 as ABC defines it in abc.rc: "b; rw; rf; b; rw; rwz; b; rfz; rwz; b"
ABC_SHORT = {"b": "balance", "rw": "rewrite", "rf": "refactor",
             "rwz": "rewrite -z", "rfz": "refactor -z"}
ABC_RESYN2 = "b; rw; rf; b; rw; rwz; b; rfz; rwz; b"


class TestRecipes(unittest.TestCase):
    def test_resyn2_matches_abc_definition(self):
        expected = tuple(ABC_SHORT[s.strip()] for s in ABC_RESYN2.split(";"))
        self.assertEqual(rc.RESYN2, expected)
        self.assertEqual(rc.resyn2().steps, expected)

    def test_script_wraps_the_searched_steps(self):
        lines = rc.resyn2().to_script().splitlines()
        self.assertEqual(lines[0], "strash")
        self.assertEqual(tuple(lines[1:1 + len(rc.RESYN2)]), rc.RESYN2)
        self.assertEqual(tuple(lines[1 + len(rc.RESYN2):]), rc.EPILOGUE)

    def test_variant_is_a_stable_fingerprint(self):
        a = rc.Recipe(steps=("balance", "rewrite"), label="x")
        self.assertEqual(a.variant, rc.Recipe(steps=("balance", "rewrite"), label="x").variant)
        self.assertNotEqual(a.variant, rc.Recipe(steps=("rewrite", "balance"), label="x").variant)

    def test_random_recipes_stay_in_bounds(self):
        rng = random.Random(0)
        for _ in range(200):
            r = rc.random_recipe(rng, min_len=6, max_len=14)
            self.assertTrue(6 <= len(r.steps) <= 14)
            self.assertTrue(set(r.steps) <= set(rc.ALPHABET))

    def test_random_recipes_are_reproducible(self):
        a = [rc.random_recipe(random.Random(7)).steps for _ in range(3)]
        b = [rc.random_recipe(random.Random(7)).steps for _ in range(3)]
        self.assertEqual(a, b)


class TestFigureOfMerit(unittest.TestCase):
    def test_no_penalty_when_timing_is_met(self):
        self.assertEqual(_fom(100.0, 5.0, wns_penalty=1.0), 100.0)

    def test_penalty_grows_with_negative_slack(self):
        self.assertEqual(_fom(100.0, -10.0, wns_penalty=2.0), 120.0)

    def test_missing_area_gives_no_score(self):
        self.assertIsNone(_fom(None, 0.0, wns_penalty=1.0))


class TestGeneticOperators(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(1)
        self.a = ["balance", "rewrite", "refactor", "balance", "rewrite"]
        self.b = ["resub", "rewrite -z", "refactor -z", "balance", "resub -z", "rewrite"]

    def test_crossover_joins_a_prefix_of_a_to_a_suffix_of_b(self):
        for _ in range(200):
            child = crossover(self.a, self.b, self.rng)
            self.assertTrue(0 < len(child) <= 20)
            joined = any(child[:i] == self.a[:i] and child[i:] == self.b[len(self.b) - (len(child) - i):]
                         for i in range(1, len(self.a)))
            self.assertTrue(joined, child)

    def test_mutate_changes_length_by_at_most_one_and_keeps_bounds(self):
        for _ in range(500):
            out = mutate(self.b, self.rng)
            self.assertLessEqual(abs(len(out) - len(self.b)), 1)
            self.assertTrue(4 <= len(out) <= 20)
            self.assertTrue(set(out) <= set(rc.ALPHABET))

    def test_mutate_does_not_modify_its_input(self):
        before = list(self.b)
        mutate(self.b, self.rng)
        self.assertEqual(self.b, before)


if __name__ == "__main__":
    unittest.main()
