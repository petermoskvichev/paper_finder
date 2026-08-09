"""One-time local OAuth setup for Gmail API delivery."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .gmail_sender import GMAIL_SEND_SCOPE


def build_parser() -> argparse.ArgumentParser:
    """Build arguments for the one-time Gmail authorization helper."""
    parser = argparse.ArgumentParser(
        description="Authorize Gmail send access and save local/GitHub credentials."
    )
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=Path("credentials.json"),
        help="Downloaded Desktop OAuth client JSON (default: credentials.json).",
    )
    parser.add_argument(
        "--token-file",
        type=Path,
        default=Path("token.json"),
        help="Private local token output (default: token.json).",
    )
    parser.add_argument(
        "--github-env",
        type=Path,
        default=Path(".env.github"),
        help="Private dotenv output for 'gh secret set -f' (default: .env.github).",
    )
    return parser


def _write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def _required_credential(credentials: Any, name: str) -> str:
    value = getattr(credentials, name, None)
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise RuntimeError(f"Google authorization did not provide a valid {name}.")
    return value


def main() -> int:
    """Run browser consent and write ignored credential files."""
    args = build_parser().parse_args()
    if not args.client_secrets.is_file():
        print(
            f"Error: OAuth client file not found: {args.client_secrets}",
            file=sys.stderr,
        )
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Error: Google client libraries are not installed; run "
            "'python -m pip install -r requirements.txt'.",
            file=sys.stderr,
        )
        return 1

    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(args.client_secrets), [GMAIL_SEND_SCOPE]
        )
        credentials = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )
        refresh_token = _required_credential(credentials, "refresh_token")
        client_id = _required_credential(credentials, "client_id")
        client_secret = _required_credential(credentials, "client_secret")

        token_data = json.loads(credentials.to_json())
        token_data["scopes"] = [GMAIL_SEND_SCOPE]
        _write_private(args.token_file, json.dumps(token_data, indent=2) + "\n")
        github_env = (
            f"GMAIL_CLIENT_ID={client_id}\n"
            f"GMAIL_CLIENT_SECRET={client_secret}\n"
            f"GMAIL_REFRESH_TOKEN={refresh_token}\n"
        )
        _write_private(args.github_env, github_env)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: Gmail authorization failed: {exc}", file=sys.stderr)
        return 1

    print(f"Saved private local token: {args.token_file}")
    print(f"Saved GitHub Secrets import file: {args.github_env}")
    print("Next: python -m arxiv_digest --config profile.yaml --send-email")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

