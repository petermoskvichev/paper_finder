"""Simple, explainable keyword relevance ranking."""

from __future__ import annotations

import re

from .config import RankingConfig
from .models import Paper, RankedPaper

WORD_SEPARATOR = re.compile(r"[-‐‑–—/]")
WHITESPACE = re.compile(r"\s+")


def _normalise(value: str) -> str:
    value = WORD_SEPARATOR.sub(" ", value.casefold())
    return WHITESPACE.sub(" ", value).strip()


def _occurrences(text: str, keyword: str) -> int:
    normalised_keyword = _normalise(keyword)
    if not normalised_keyword:
        return 0
    pattern = rf"(?<!\w){re.escape(normalised_keyword)}(?!\w)"
    return len(re.findall(pattern, text))


def _weighted_matches(
    title: str,
    abstract: str,
    keyword_weights: dict[str, float],
    title_multiplier: float,
) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    matches: list[str] = []
    for keyword, weight in keyword_weights.items():
        title_count = _occurrences(title, keyword)
        abstract_count = _occurrences(abstract, keyword)
        if title_count or abstract_count:
            score += weight * (title_count * title_multiplier + abstract_count)
            matches.append(keyword)
    return score, tuple(matches)


def score_paper(paper: Paper, config: RankingConfig) -> RankedPaper:
    """Calculate a paper's score and retain the matching terms for display."""
    title = _normalise(paper.title)
    abstract = _normalise(paper.abstract)
    positive_score, positive_matches = _weighted_matches(
        title,
        abstract,
        config.positive_keywords,
        config.title_multiplier,
    )
    negative_score, negative_matches = _weighted_matches(
        title,
        abstract,
        config.negative_keywords,
        config.title_multiplier,
    )
    return RankedPaper(
        paper=paper,
        score=positive_score - negative_score,
        positive_matches=positive_matches,
        negative_matches=negative_matches,
    )


def rank_papers(papers: list[Paper], config: RankingConfig) -> list[RankedPaper]:
    """Score papers and sort by relevance, then recency, then arXiv ID."""
    ranked = [score_paper(paper, config) for paper in papers]
    return sorted(
        ranked,
        key=lambda item: (
            -item.score,
            -item.paper.published_at.timestamp(),
            item.paper.arxiv_id,
        ),
    )

