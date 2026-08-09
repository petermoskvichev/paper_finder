"""Command-line entry point for the arXiv digest."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .arxiv_client import ArxivAPIError, ArxivClient
from .config import ConfigError, load_config
from .digest import render_digest
from .gmail_sender import GmailDeliveryError, send_email_via_gmail
from .ranking import rank_papers


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Fetch and rank recently submitted arXiv papers."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("profile.yaml"),
        help="Path to the YAML research profile (default: profile.yaml).",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send the rendered digest through the Gmail API after printing it.",
    )
    parser.add_argument(
        "--gmail-token",
        type=Path,
        default=Path("token.json"),
        help="Local Gmail OAuth token file (default: token.json).",
    )
    return parser


def main() -> int:
    """Run the fetch, rank, and terminal-rendering pipeline."""
    args = build_parser().parse_args()

    try:
        config = load_config(args.config)
        client = ArxivClient()
        papers = client.fetch_recent(
            categories=config.arxiv.categories,
            lookback_hours=config.arxiv.lookback_hours,
            fetch_limit=config.arxiv.fetch_limit,
        )
        ranked = rank_papers(papers, config.ranking)
    except (ConfigError, ArxivAPIError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    digest = render_digest(
        ranked[: config.ranking.max_papers],
        lookback_hours=config.arxiv.lookback_hours,
        categories=config.arxiv.categories,
    )
    print(digest)

    if args.send_email:
        subject = (
            f"{config.email.subject_prefix} | "
            f"{datetime.now(timezone.utc):%Y-%m-%d}"
        )
        try:
            message_id = send_email_via_gmail(
                sender=config.email.sender,
                recipient=config.email.recipient,
                subject=subject,
                body=digest,
                token_file=args.gmail_token,
            )
        except GmailDeliveryError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Email sent to {config.email.recipient} (Gmail ID: {message_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
