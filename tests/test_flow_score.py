"""Tests for flow_score: geometry metrics over one saved case."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
import compare  # noqa: E402
import flow_score  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def score(word, engine):
    result = compare.compare(word, engine)
    with tempfile.TemporaryDirectory() as tmp:
        cmp_path = os.path.join(tmp, "case.cmp.json")
        engine_path = os.path.join(tmp, "case.engine.json")
        with open(cmp_path, "w", encoding="utf-8") as f:
            json.dump(result, f)
        with open(engine_path, "w", encoding="utf-8") as f:
            json.dump(engine, f)
        return flow_score.score_case(cmp_path, engine_path)


class FlowScoreTest(unittest.TestCase):
    def test_exact_layout(self):
        row = score(load("word_lines.json"), load("engine_exact.json"))
        self.assertEqual(row["structure"], 1.0)
        self.assertEqual(row["linesRatio"], 1.0)
        self.assertEqual(row["n"], 3)
        self.assertEqual(row["x0ok"], 1.0)
        self.assertEqual(row["dx0"], 0.0)
        self.assertEqual(row["wok"], 1.0)
        self.assertEqual(row["dw"], 0.0)
        self.assertEqual(row["sok"], 1.0)
        self.assertEqual(row["ds"], 0.0)
        self.assertEqual(row["wordLines"], 3)
        self.assertEqual(row["chipLines"], 0)

    def test_vertical_offset_keeps_structure_but_changes_geometry(self):
        row = score(load("word_lines.json"), load("engine_shifted.json"))
        self.assertEqual(row["structure"], 1.0)
        self.assertEqual(row["x0ok"], 0.0)
        self.assertEqual(row["dx0"], 1.0)

    def test_missing_engine_output_becomes_a_zero_row(self):
        row = flow_score.failed_row(100, "layout/corpus/x.docx", "layout/corpus")
        self.assertEqual(row["structure"], 0.0)
        self.assertEqual(row["wordLines"], 100)
        self.assertTrue(row["error"])

    def test_bootstrap_interval_brackets_the_mean(self):
        lo, hi = flow_score.boot_ci([0.5, 0.6, 0.7, 0.8], n=200)
        self.assertLessEqual(lo, 0.65)
        self.assertGreaterEqual(hi, 0.65)
        self.assertLess(lo, hi)


if __name__ == "__main__":
    unittest.main()