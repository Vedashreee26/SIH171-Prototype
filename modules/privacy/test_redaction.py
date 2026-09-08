"""
Runnable examples for modules.privacy.redaction.

Uses only fake / reserved example values (example.com, well-known test cards).
Does not print raw fixtures on failure beyond unittest diffs.

Run from the repo root:

    python -m unittest modules.privacy.test_redaction
"""

from __future__ import annotations

import json
import unittest

from modules.privacy.redaction import (
    REDACTED_CARD,
    REDACTED_EMAIL,
    REDACTED_ID,
    REDACTED_PASSWORD,
    REDACTED_PHONE,
    REDACTED_PII,
    redact_sensitive_data,
)


class RedactSensitiveDataTests(unittest.TestCase):
    def test_example_from_brief(self):
        data = {
            "elements": [
                {"type": "input", "label": "Email", "text": "someone@example.com"}
            ]
        }
        out = redact_sensitive_data(data)
        self.assertEqual(
            out,
            {
                "elements": [
                    {
                        "type": "input",
                        "label": "Email",
                        "text": REDACTED_EMAIL,
                    }
                ]
            },
        )
        # Structure preserved: still JSON.
        json.dumps(out)

    def test_does_not_mutate_input(self):
        data = {"text": "a@b.co"}
        redact_sensitive_data(data)
        self.assertEqual(data["text"], "a@b.co")

    def test_phone_and_email_in_same_string(self):
        text = "Call +1 415-555-2671 or write  someone@example.com "
        out = redact_sensitive_data({"text": text})
        self.assertNotIn("415-555-2671", out["text"])
        self.assertNotIn("someone@example.com", out["text"])
        self.assertIn(REDACTED_PHONE, out["text"])
        self.assertIn(REDACTED_EMAIL, out["text"])

    def test_password_field_by_type(self):
        data = {
            "elements": [
                {
                    "type": "password",
                    "label": "Password",
                    "text": "hunter2-not-a-real-password",
                }
            ]
        }
        out = redact_sensitive_data(data)
        self.assertEqual(out["elements"][0]["text"], REDACTED_PASSWORD)
        self.assertEqual(out["elements"][0]["type"], "password")
        self.assertEqual(out["elements"][0]["label"], "Password")

    def test_password_field_by_label_keeps_button_structure(self):
        data = {
            "elements": [
                {"type": "input", "label": "Password", "value": "abc"},
                {"type": "button", "text": "Submit"},
            ]
        }
        out = redact_sensitive_data(data)
        self.assertEqual(out["elements"][0]["value"], REDACTED_PASSWORD)
        self.assertEqual(out["elements"][1], {"type": "button", "text": "Submit"})

    def test_luhn_card_redacted_invalid_not(self):
        # Visa test BIN pattern; Luhn-valid.
        valid = "4111 1111 1111 1111"
        invalid = "4111 1111 1111 1112"
        out = redact_sensitive_data({"card": valid, "other": invalid})
        self.assertEqual(out["card"], REDACTED_CARD)
        self.assertEqual(out["other"], invalid)

    def test_pan_and_ssn_like(self):
        out = redact_sensitive_data(
            {"pan": "ABCDE1234F", "ssn": "123-45-6789", "note": "ok"}
        )
        self.assertEqual(out["pan"], REDACTED_ID)
        self.assertEqual(out["ssn"], REDACTED_ID)
        self.assertEqual(out["note"], "ok")

    def test_name_field_only(self):
        data = {
            "elements": [
                {"type": "input", "label": "Full Name", "text": "Ada Lovelace"},
                {"type": "button", "text": "Submit Form"},
            ]
        }
        out = redact_sensitive_data(data)
        self.assertEqual(out["elements"][0]["text"], REDACTED_PII)
        self.assertEqual(out["elements"][1]["text"], "Submit Form")

    def test_indian_mobile(self):
        out = redact_sensitive_data({"text": "Reach us at 9876543210 today"})
        self.assertNotIn("9876543210", out["text"])
        self.assertIn(REDACTED_PHONE, out["text"])

    def test_json_compatible_nested(self):
        data = {
            "title": "Checkout",
            "elements": [
                {"type": "input", "label": "Email", "text": "user@example.com"},
            ],
            "meta": {"ok": True, "n": 3},
        }
        out = redact_sensitive_data(data)
        encoded = json.dumps(out)
        self.assertIn(REDACTED_EMAIL, encoded)
        self.assertNotIn("user@example.com", encoded)


if __name__ == "__main__":
    unittest.main()
