"""Tests for command-line argument validation."""

from __future__ import annotations

import argparse
import io
import sys
import unittest
from unittest.mock import patch

from arxiv_digest.__main__ import main, positive_int, timezone_aware_datetime


class CLITests(unittest.TestCase):
    def test_positive_int_accepts_valid_override(self) -> None:
        self.assertEqual(positive_int("168"), 168)

    def test_positive_int_rejects_zero(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            positive_int("0")

    def test_reference_time_requires_timezone_and_is_normalised_to_utc(self) -> None:
        parsed = timezone_aware_datetime("2026-08-10T08:15:00+08:00")

        self.assertEqual(parsed.isoformat(), "2026-08-10T00:15:00+00:00")
        with self.assertRaises(argparse.ArgumentTypeError):
            timezone_aware_datetime("2026-08-10T08:15:00")

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
