"""Tests for the line comparison: grouping, parity, local parity and defects."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
import compare  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class CompareTest(unittest.TestCase):
    def test_exact_layout_scores_one(self):
        result = compare.compare(load("word_lines.json"), load("engine_exact.json"))
        self.assertTrue(result["pageParity"])
        self.assertEqual(result["lines"]["lineParity"], 1.0)
        self.assertEqual(result["lines"]["localParity"], 1.0)
        self.assertEqual(result["defects"], [])
        self.assertIsNone(result["first"])
        self.assertEqual(result["lines"]["matched"], 3)

    def test_offset_cascades_on_line_parity_but_not_on_local_parity(self):
        result = compare.compare(load("word_lines.json"), load("engine_shifted.json"))
        self.assertEqual(result["lines"]["lineParity"], 0.0)
        # the first line establishes a +2pt offset; lines 2 and 3 keep it
        self.assertEqual(result["lines"]["localParity"], round(2 / 3, 4))
        self.assertEqual(len(result["defects"]), 1)
        self.assertEqual(result["defects"][0]["kind"], "position")
        self.assertEqual(result["first"]["kind"], "position")

    def test_horizontal_offset_does_not_affect_line_parity(self):
        engine = load("engine_exact.json")
        for page in engine["pages"]:
            for char in page["chars"]:
                char["x"] += 20.0
        result = compare.compare(load("word_lines.json"), engine)
        # x is not part of line parity (flow_score measures it separately)
        self.assertEqual(result["lines"]["lineParity"], 1.0)

    def test_line_break_difference_is_a_break_defect(self):
        word = load("word_lines.json")
        engine = {"pages": [{"chars": [
            {"t": "Hello world Second line", "x": 72.0, "y": 72.0, "w": 196.0, "s": 12.0},
        ]}, {"chars": [
            {"t": "Third line", "x": 72.0, "y": 72.0, "w": 78.0, "s": 12.0},
        ]}]}
        result = compare.compare(word, engine)
        self.assertEqual(result["first"]["kind"], "break")
        self.assertEqual(len(result["defects"]), 1)
        self.assertEqual(result["defects"][0]["kind"], "break")

    def test_whitespace_and_case_are_normalized_for_matching(self):
        word = load("word_lines.json")
        engine = load("engine_exact.json")
        engine["pages"][0]["chars"][0]["t"] = "Hello  world"
        result = compare.compare(word, engine)
        self.assertEqual(result["lines"]["lineParity"], 1.0)

    def test_empty_documents_agree(self):
        result = compare.compare({"pages": []}, {"pages": []})
        self.assertTrue(result["pageParity"])
        self.assertEqual(result["lines"]["lineParity"], 1.0)
        self.assertIsNone(result["first"])

    def test_chars_on_one_baseline_form_one_line(self):
        chars = [
            {"t": "a", "x": 72.0, "y": 72.0, "w": 6.0, "s": 12.0},
            {"t": "b", "x": 78.0, "y": 72.3, "w": 6.0, "s": 12.0},
            {"t": "c", "x": 84.0, "y": 90.0, "w": 6.0, "s": 12.0},
        ]
        lines = compare.group(chars)
        self.assertEqual([line["text"] for line in lines], ["ab", "c"])


if __name__ == "__main__":
    unittest.main()