"""Explainable hybrid lexical and semantic relevance ranking."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any, Protocol

from .config import RankingConfig, ResearchTheme
from .models import Paper, RankedPaper, ThemeMatch

WORD_SEPARATOR = re.compile(r"[-‐‑–—/]")
WHITESPACE = re.compile(r"\s+")


class SemanticRankingError(RuntimeError):
    """Raised when the configured embedding model cannot rank papers."""


class Embedder(Protocol):
    """Small protocol implemented by SentenceTransformer and test doubles."""

    def encode(self, sentences: Sequence[str], **kwargs: Any) -> Any:
        """Encode text strings as normalized vectors."""


def _normalise(value: str) -> str:
    value = WORD_SEPARATOR.sub(" ", value.casefold())
    return WHITESPACE.sub(" ", value).strip()


def _occurrences(text: str, keyword: str) -> int:
    normalised_keyword = _normalise(keyword)
    if not normalised_keyword:
        return 0
    pattern = rf"(?<!\w){re.escape(normalised_keyword)}(?!\w)"
    return len(re.findall(pattern, text))


def _theme_lexical_score(
    title: str,
    abstract: str,
    theme: ResearchTheme,
    title_multiplier: float,
) -> float:
    return theme.weight * sum(
        _occurrences(title, alias) * title_multiplier + _occurrences(abstract, alias)
        for alias in dict.fromkeys(_normalise(alias) for alias in theme.aliases)
    )


def _negative_score(
    title: str,
    abstract: str,
    keyword_weights: dict[str, float],
    title_multiplier: float,
) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    matches: list[str] = []
    for keyword, weight in keyword_weights.items():
        occurrences = (
            _occurrences(title, keyword) * title_multiplier
            + _occurrences(abstract, keyword)
        )
        if occurrences:
            score += weight * occurrences
            matches.append(keyword)
    return score, tuple(matches)


def _lexical_details(
    paper: Paper, config: RankingConfig
) -> tuple[float, tuple[str, ...], float, tuple[str, ...]]:
    title = _normalise(paper.title)
    abstract = _normalise(paper.abstract)
    positive_score = 0.0
    positive_matches: list[str] = []
    for theme in config.themes:
        theme_score = _theme_lexical_score(
            title, abstract, theme, config.title_multiplier
        )
        if theme_score:
            positive_score += theme_score
            positive_matches.append(theme.name)

    negative_score, negative_matches = _negative_score(
        title,
        abstract,
        config.negative_keywords,
        config.title_multiplier,
    )
    return positive_score, tuple(positive_matches), negative_score, negative_matches


def score_paper(paper: Paper, config: RankingConfig) -> RankedPaper:
    """Calculate lexical relevance only, useful when semantic ranking is disabled."""
    positive, positive_matches, negative, negative_matches = _lexical_details(
        paper, config
    )
    return RankedPaper(
        paper=paper,
        score=positive - negative,
        positive_matches=positive_matches,
        negative_matches=negative_matches,
        lexical_score=positive,
    )


def _load_embedder(model_name: str) -> Embedder:
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise SemanticRankingError(
            f"Could not load semantic model '{model_name}': {exc}"
        ) from exc


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return float(sum(float(a) * float(b) for a, b in zip(left, right, strict=True)))


def _semantic_signal(
    similarities: Sequence[float], themes: tuple[ResearchTheme, ...]
) -> float:
    """Combine the strongest theme match with a small multi-theme breadth bonus."""
    weighted = [max(0.0, score) * theme.weight for score, theme in zip(similarities, themes)]
    if not weighted:
        return 0.0
    strongest = max(weighted) / max(theme.weight for theme in themes)
    breadth = sum(sorted((max(0.0, score) for score in similarities), reverse=True)[:3])
    breadth /= min(3, len(similarities))
    return min(1.0, 0.8 * strongest + 0.2 * breadth)


def _rank_semantically(
    papers: list[Paper], config: RankingConfig, embedder: Embedder
) -> list[RankedPaper]:
    theme_texts = [theme.description for theme in config.themes]
    paper_texts = [f"Title: {paper.title}\nAbstract: {paper.abstract}" for paper in papers]
    try:
        vectors = embedder.encode(
            theme_texts + paper_texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    except Exception as exc:  # The model backend exposes several exception types.
        raise SemanticRankingError(f"Semantic encoding failed: {exc}") from exc

    theme_vectors = vectors[: len(config.themes)]
    paper_vectors = vectors[len(config.themes) :]
    total_weight = config.semantic.semantic_weight + config.semantic.lexical_weight
    semantic_weight = config.semantic.semantic_weight / total_weight
    lexical_weight = config.semantic.lexical_weight / total_weight

    ranked: list[RankedPaper] = []
    for paper, paper_vector in zip(papers, paper_vectors, strict=True):
        positive, positive_matches, negative, negative_matches = _lexical_details(
            paper, config
        )
        similarities = [_dot(paper_vector, vector) for vector in theme_vectors]
        semantic_score = _semantic_signal(similarities, config.themes)
        lexical_signal = 1.0 - math.exp(-positive / 10.0)
        negative_signal = 1.0 - math.exp(-negative / 10.0)
        score = 100.0 * (
            semantic_weight * semantic_score + lexical_weight * lexical_signal
        ) - 20.0 * negative_signal

        matches = sorted(
            (
                ThemeMatch(theme.name, similarity)
                for theme, similarity in zip(config.themes, similarities, strict=True)
                if similarity >= config.semantic.min_similarity
            ),
            key=lambda match: match.similarity,
            reverse=True,
        )[: config.semantic.top_theme_matches]
        ranked.append(
            RankedPaper(
                paper=paper,
                score=score,
                positive_matches=positive_matches,
                negative_matches=negative_matches,
                lexical_score=positive,
                semantic_score=semantic_score,
                semantic_matches=tuple(matches),
            )
        )
    return ranked


def rank_papers(
    papers: list[Paper], config: RankingConfig, embedder: Embedder | None = None
) -> list[RankedPaper]:
    """Rank papers by hybrid relevance, recency, and arXiv ID."""
    if config.semantic.enabled and papers:
        ranked = _rank_semantically(
            papers,
            config,
            embedder or _load_embedder(config.semantic.model_name),
        )
    else:
        ranked = [score_paper(paper, config) for paper in papers]

    return sorted(
        ranked,
        key=lambda item: (
            -item.score,
            -item.paper.published_at.timestamp(),
            item.paper.arxiv_id,
        ),
    )
