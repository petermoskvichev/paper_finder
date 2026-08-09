"""Data models shared by fetching, ranking, and rendering stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Paper:
    """Metadata for one arXiv paper."""

    arxiv_id: str
    title: str
    authors: tuple[str, ...]
    abstract: str
    categories: tuple[str, ...]
    published_at: datetime
    url: str


@dataclass(frozen=True, slots=True)
class RankedPaper:
    """A paper plus its keyword-ranking details."""

    paper: Paper
    score: float
    positive_matches: tuple[str, ...]
    negative_matches: tuple[str, ...]

