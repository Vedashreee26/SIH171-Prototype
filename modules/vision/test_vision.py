"""Test example for the local vision module.

Run from the repository root:

    python -m unittest modules.vision.test_vision
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from modules.vision import analyze_screen

SAMPLE_DIR = Path(__file__).resolve().parent


class AnalyzeScreenTests(unittest.TestCase):
    def test_sample_login_page(self) -> None:
        sample_path = SAMPLE_DIR / "sample_input.json"
        with sample_path.open(encoding="utf-8") as handle:
            sample = json.load(handle)

        result = analyze_screen(sample)

        self.assertEqual(result["implementation"], "lightweight_dom")
        self.assertFalse(result["screenshot_present"])
        self.assertEqual(result["page"]["title"], "Example Login")

        types = [item["type"] for item in result["elements"]]
        self.assertEqual(
            types,
            ["heading", "input", "input", "button", "link", "selectable", "selectable"],
        )

        submit = next(item for item in result["elements"] if item["text"] == "Submit")
        self.assertEqual(submit["type"], "button")
        self.assertEqual(submit["bbox"], [80, 240, 180, 280])
        self.assertTrue(submit["interactive"])

        email = next(item for item in result["elements"] if item.get("id") == "email")
        self.assertEqual(email["type"], "input")
        self.assertEqual(email["bbox"], [80, 120, 360, 160])

    def test_empty_and_invalid_input(self) -> None:
        empty = analyze_screen(None)
        self.assertEqual(empty["elements"], [])
        self.assertEqual(analyze_screen("not-a-structure")["elements"], [])

    def test_skips_hidden_and_zero_size(self) -> None:
        result = analyze_screen(
            {
                "elements": [
                    {"tag": "button", "text": "OK", "bbox": [0, 0, 40, 20]},
                    {"tag": "button", "text": "Hidden", "bbox": [0, 0, 40, 20], "visible": False},
                    {"tag": "button", "text": "Zero", "bbox": [10, 10, 10, 20]},
                ]
            }
        )
        texts = [item["text"] for item in result["elements"]]
        self.assertEqual(texts, ["OK"])

    def test_aria_roles(self) -> None:
        result = analyze_screen(
            [
                {"role": "button", "text": "Continue", "bbox": [1, 1, 10, 10]},
                {"role": "link", "name": "Docs", "bbox": [1, 1, 10, 10]},
                {"role": "heading", "text": "Welcome", "bbox": [1, 1, 10, 10]},
                {"role": "checkbox", "text": "Agree", "bbox": [1, 1, 10, 10]},
            ]
        )
        self.assertEqual(
            [item["type"] for item in result["elements"]],
            ["button", "link", "heading", "selectable"],
        )


if __name__ == "__main__":
    unittest.main()
