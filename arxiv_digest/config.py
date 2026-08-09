"""Load and validate the YAML research profile."""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the research profile is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ArxivConfig:
    """Settings controlling the arXiv query."""

    categories: tuple[str, ...]
    lookback_hours: int
    fetch_limit: int


@dataclass(frozen=True, slots=True)
class RankingConfig:
    """Settings controlling keyword scoring and output size."""

    max_papers: int
    title_multiplier: float
    positive_keywords: dict[str, float]
    negative_keywords: dict[str, float]


@dataclass(frozen=True, slots=True)
class EmailConfig:
    """Settings controlling email addressing and subject text."""

    sender: str
    recipient: str
    subject_prefix: str


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Complete application configuration."""

    arxiv: ArxivConfig
    ranking: RankingConfig
    email: EmailConfig


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"'{name}' must be a YAML mapping.")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"'{name}' must be a positive integer.")
    return value


def _positive_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"'{name}' must be a positive number.")
    return float(value)


def _keyword_weights(value: Any, name: str) -> dict[str, float]:
    mapping = _require_mapping(value, name)
    weights: dict[str, float] = {}
    for keyword, weight in mapping.items():
        if not isinstance(keyword, str) or not keyword.strip():
            raise ConfigError(f"Every key in '{name}' must be a non-empty string.")
        weights[keyword.strip()] = _positive_float(weight, f"{name}.{keyword}")
    return weights


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{name}' must be a non-empty string.")
    cleaned = value.strip()
    if "\r" in cleaned or "\n" in cleaned:
        raise ConfigError(f"'{name}' cannot contain line breaks.")
    return cleaned


def _email_address(value: Any, name: str) -> str:
    address = _non_empty_string(value, name)
    display_name, parsed = parseaddr(address)
    if display_name or parsed != address or "@" not in parsed:
        raise ConfigError(f"'{name}' must be a plain email address.")
    return address


def load_config(path: Path) -> AppConfig:
    """Read a profile file and return validated application settings."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {path}") from exc
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not read configuration file {path}: {exc}") from exc

    root = _require_mapping(raw, "root")
    arxiv = _require_mapping(root.get("arxiv"), "arxiv")
    ranking = _require_mapping(root.get("ranking"), "ranking")
    email = _require_mapping(root.get("email"), "email")

    categories_value = arxiv.get("categories")
    if (
        not isinstance(categories_value, list)
        or not categories_value
        or not all(isinstance(item, str) and item.strip() for item in categories_value)
    ):
        raise ConfigError("'arxiv.categories' must be a non-empty list of strings.")
    categories = tuple(dict.fromkeys(item.strip() for item in categories_value))

    positive_keywords = _keyword_weights(
        ranking.get("positive_keywords"), "ranking.positive_keywords"
    )
    if not positive_keywords:
        raise ConfigError("'ranking.positive_keywords' must contain at least one keyword.")

    return AppConfig(
        arxiv=ArxivConfig(
            categories=categories,
            lookback_hours=_positive_int(
                arxiv.get("lookback_hours", 48), "arxiv.lookback_hours"
            ),
            fetch_limit=_positive_int(
                arxiv.get("fetch_limit", 300), "arxiv.fetch_limit"
            ),
        ),
        ranking=RankingConfig(
            max_papers=_positive_int(
                ranking.get("max_papers", 10), "ranking.max_papers"
            ),
            title_multiplier=_positive_float(
                ranking.get("title_multiplier", 2.0), "ranking.title_multiplier"
            ),
            positive_keywords=positive_keywords,
            negative_keywords=_keyword_weights(
                ranking.get("negative_keywords", {}), "ranking.negative_keywords"
            ),
        ),
        email=EmailConfig(
            sender=_email_address(email.get("sender"), "email.sender"),
            recipient=_email_address(email.get("recipient"), "email.recipient"),
            subject_prefix=_non_empty_string(
                email.get("subject_prefix", "Daily arXiv research digest"),
                "email.subject_prefix",
            ),
        ),
    )
