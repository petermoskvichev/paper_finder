"""Command-line entry point for the arXiv digest."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .arxiv_client import ArxivAPIError, ArxivClient
from .config import ConfigError, load_config
from .digest import render_digest
from .email_digest import render_html_digest
from .gmail_sender import GmailDeliveryError, send_email_via_gmail
from .ranking import SemanticRankingError, rank_papers


def positive_int(value: str) -> int:
    """Parse a strictly positive command-line integer."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


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
        "--lookback-hours",
        type=positive_int,
        help="Override profile.yaml's lookback window for this run only.",
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
        lookback_hours = args.lookback_hours or config.arxiv.lookback_hours
        client = ArxivClient()
        papers = client.fetch_recent(
            category_groups=config.arxiv.category_groups,
            lookback_hours=lookback_hours,
            request_delay_seconds=config.arxiv.request_delay_seconds,
        )
        ranked = rank_papers(papers, config.ranking)
    except (ConfigError, ArxivAPIError, SemanticRankingError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    selected_papers = ranked[: config.ranking.max_papers]
    digest = render_digest(
        selected_papers,
        lookback_hours=lookback_hours,
        categories=config.arxiv.categories,
    )
    print(digest)

    if args.send_email and not selected_papers:
        print("No recent papers found; email skipped.")
        return 0

    if args.send_email:
        email_text = render_digest(
            selected_papers,
            lookback_hours=lookback_hours,
            categories=config.arxiv.categories,
            abstract_length=None,
        )
        email_html = render_html_digest(
            selected_papers,
            lookback_hours=lookback_hours,
            categories=config.arxiv.categories,
        )
        subject = (
            f"{config.email.subject_prefix} | "
            f"{datetime.now(timezone.utc):%Y-%m-%d}"
        )
        try:
            message_id = send_email_via_gmail(
                sender=config.email.sender,
                recipient=config.email.recipient,
                subject=subject,
                body=email_text,
                html_body=email_html,
                token_file=args.gmail_token,
            )
        except GmailDeliveryError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Email sent to {config.email.recipient} (Gmail ID: {message_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
