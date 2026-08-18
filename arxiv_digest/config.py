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
class CategoryGroup:
    """One independently queried set of related arXiv categories."""

    name: str
    categories: tuple[str, ...]
    fetch_limit: int


@dataclass(frozen=True, slots=True)
class ArxivConfig:
    """Settings controlling grouped arXiv queries."""

    category_groups: tuple[CategoryGroup, ...]
    lookback_hours: int
    request_delay_seconds: float
    use_announcement_window: bool

    @property
    def categories(self) -> tuple[str, ...]:
        """Return all configured categories in stable, deduplicated order."""
        return tuple(
            dict.fromkeys(
                category
                for group in self.category_groups
                for category in group.categories
            )
        )


@dataclass(frozen=True, slots=True)
class ResearchTheme:
    """A research interest used for lexical and semantic matching."""

    name: str
    description: str
    aliases: tuple[str, ...]
    weight: float


@dataclass(frozen=True, slots=True)
class SemanticConfig:
    """Settings for local embedding-based relevance scoring."""

    enabled: bool
    model_name: str
    semantic_weight: float
    lexical_weight: float
    min_similarity: float
    top_theme_matches: int


@dataclass(frozen=True, slots=True)
class RankingConfig:
    """Settings controlling hybrid scoring and output size."""

    max_papers: int
    title_multiplier: float
    themes: tuple[ResearchTheme, ...]
    negative_keywords: dict[str, float]
    semantic: SemanticConfig


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


def _non_negative_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ConfigError(f"'{name}' must be a non-negative number.")
    return float(value)


def _bounded_float(value: Any, name: str, minimum: float, maximum: float) -> float:
    number = _non_negative_float(value, name)
    if not minimum <= number <= maximum:
        raise ConfigError(f"'{name}' must be between {minimum} and {maximum}.")
    return number


def _keyword_weights(value: Any, name: str) -> dict[str, float]:
    mapping = _require_mapping(value, name)
    weights: dict[str, float] = {}
    for keyword, weight in mapping.items():
        if not isinstance(keyword, str) or not keyword.strip():
            raise ConfigError(f"Every key in '{name}' must be a non-empty string.")
        weights[keyword.strip()] = _positive_float(weight, f"{name}.{keyword}")
    return weights


def _non_empty_string(value: Any, name: str, *, allow_line_breaks: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{name}' must be a non-empty string.")
    cleaned = " ".join(value.split()) if allow_line_breaks else value.strip()
    if not allow_line_breaks and ("\r" in cleaned or "\n" in cleaned):
        raise ConfigError(f"'{name}' cannot contain line breaks.")
    return cleaned


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"'{name}' must be true or false.")
    return value


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise ConfigError(f"'{name}' must be a non-empty list of strings.")
    return tuple(dict.fromkeys(item.strip() for item in value))


def _category_groups(value: Any) -> tuple[CategoryGroup, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError("'arxiv.category_groups' must be a non-empty list.")

    groups: list[CategoryGroup] = []
    seen_names: set[str] = set()
    for index, raw_group in enumerate(value):
        path = f"arxiv.category_groups[{index}]"
        group = _require_mapping(raw_group, path)
        name = _non_empty_string(group.get("name"), f"{path}.name")
        if name in seen_names:
            raise ConfigError(f"Category group name '{name}' is duplicated.")
        seen_names.add(name)
        groups.append(
            CategoryGroup(
                name=name,
                categories=_string_list(group.get("categories"), f"{path}.categories"),
                fetch_limit=_positive_int(
                    group.get("fetch_limit", 200), f"{path}.fetch_limit"
                ),
            )
        )
    return tuple(groups)


def _research_themes(value: Any) -> tuple[ResearchTheme, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError("'ranking.themes' must be a non-empty list.")

    themes: list[ResearchTheme] = []
    seen_names: set[str] = set()
    for index, raw_theme in enumerate(value):
        path = f"ranking.themes[{index}]"
        theme = _require_mapping(raw_theme, path)
        name = _non_empty_string(theme.get("name"), f"{path}.name")
        if name.casefold() in seen_names:
            raise ConfigError(f"Research theme name '{name}' is duplicated.")
        seen_names.add(name.casefold())
        themes.append(
            ResearchTheme(
                name=name,
                description=_non_empty_string(
                    theme.get("description"),
                    f"{path}.description",
                    allow_line_breaks=True,
                ),
                aliases=_string_list(theme.get("aliases"), f"{path}.aliases"),
                weight=_positive_float(theme.get("weight", 1.0), f"{path}.weight"),
            )
        )
    return tuple(themes)


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
    semantic = _require_mapping(ranking.get("semantic", {}), "ranking.semantic")
    email = _require_mapping(root.get("email"), "email")

    semantic_weight = _non_negative_float(
        semantic.get("semantic_weight", 0.7), "ranking.semantic.semantic_weight"
    )
    lexical_weight = _non_negative_float(
        semantic.get("lexical_weight", 0.3), "ranking.semantic.lexical_weight"
    )
    if semantic_weight + lexical_weight <= 0:
        raise ConfigError("At least one semantic or lexical ranking weight must be positive.")

    enabled = _boolean(semantic.get("enabled", True), "ranking.semantic.enabled")

    return AppConfig(
        arxiv=ArxivConfig(
            category_groups=_category_groups(arxiv.get("category_groups")),
            lookback_hours=_positive_int(
                arxiv.get("lookback_hours", 48), "arxiv.lookback_hours"
            ),
            request_delay_seconds=_non_negative_float(
                arxiv.get("request_delay_seconds", 3.0),
                "arxiv.request_delay_seconds",
            ),
            use_announcement_window=_boolean(
                arxiv.get("use_announcement_window", False),
                "arxiv.use_announcement_window",
            ),
        ),
        ranking=RankingConfig(
            max_papers=_positive_int(
                ranking.get("max_papers", 10), "ranking.max_papers"
            ),
            title_multiplier=_positive_float(
                ranking.get("title_multiplier", 2.0), "ranking.title_multiplier"
            ),
            themes=_research_themes(ranking.get("themes")),
            negative_keywords=_keyword_weights(
                ranking.get("negative_keywords", {}), "ranking.negative_keywords"
            ),
            semantic=SemanticConfig(
                enabled=enabled,
                model_name=_non_empty_string(
                    semantic.get("model_name", "sentence-transformers/all-MiniLM-L6-v2"),
                    "ranking.semantic.model_name",
                ),
                semantic_weight=semantic_weight,
                lexical_weight=lexical_weight,
                min_similarity=_bounded_float(
                    semantic.get("min_similarity", 0.25),
                    "ranking.semantic.min_similarity",
                    0.0,
                    1.0,
                ),
                top_theme_matches=_positive_int(
                    semantic.get("top_theme_matches", 3),
                    "ranking.semantic.top_theme_matches",
                ),
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
