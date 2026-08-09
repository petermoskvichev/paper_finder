"""Tests for reusable digest rendering and MIME message creation."""

from __future__ import annotations

import unittest

from arxiv_digest.digest import render_digest
from arxiv_digest.gmail_sender import build_email_message


class EmailTests(unittest.TestCase):
    def test_empty_digest_can_be_used_as_email_body(self) -> None:
        body = render_digest([], 48, ("cs.LG", "stat.ML"))

        self.assertIn("Papers shown: 0", body)
        self.assertIn("No papers were published", body)

    def test_email_message_has_expected_headers_and_plain_text(self) -> None:
        message = build_email_message(
            sender="sender@example.com",
            recipient="reader@example.com",
            subject="Daily digest",
            body="One interesting paper.",
        )

        self.assertEqual(message["From"], "sender@example.com")
        self.assertEqual(message["To"], "reader@example.com")
        self.assertEqual(message["Subject"], "Daily digest")
        self.assertEqual(message.get_content().strip(), "One interesting paper.")


if __name__ == "__main__":
    unittest.main()

