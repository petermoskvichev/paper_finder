"""Tests for command-line argument validation."""

from __future__ import annotations

import argparse
import io
import sys
import unittest
from unittest.mock import patch

from arxiv_digest.__main__ import main, positive_int


class CLITests(unittest.TestCase):
    def test_positive_int_accepts_valid_override(self) -> None:
        self.assertEqual(positive_int("168"), 168)

    def test_positive_int_rejects_zero(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")

    @patch("arxiv_digest.__main__.send_email_via_gmail")
    @patch("arxiv_digest.__main__.ArxivClient")
    def test_empty_digest_skips_email(self, client_class, send_email) -> None:
        client_class.return_value.fetch_recent.return_value = []

        with patch.object(sys, "argv", ["arxiv_digest", "--send-email"]):
            with patch("sys.stdout", new_callable=io.StringIO) as stdout:
                exit_code = main()

        self.assertEqual(exit_code, 0)
        send_email.assert_not_called()
        self.assertIn("No recent papers found; email skipped.", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
