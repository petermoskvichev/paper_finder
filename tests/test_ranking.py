"""Tests for the deterministic keyword ranking stage."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from arxiv_digest.config import RankingConfig
from arxiv_digest.models import Paper
from arxiv_digest.ranking import rank_papers, score_paper


def make_paper(arxiv_id: str, title: str, abstract: str) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title=title,
        authors=("Example Author",),
        abstract=abstract,
        categories=("cs.LG",),
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        url=f"https://arxiv.org/abs/{arxiv_id}",
    )


class RankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = RankingConfig(
            max_papers=10,
            title_multiplier=2.0,
            positive_keywords={"distribution shift": 4.0, "RKHS": 3.0},
            negative_keywords={"survey": 1.0},
        )

    def test_title_matches_receive_multiplier_and_hyphens_are_normalised(self) -> None:
        paper = make_paper(
            "2601.00001",
            "Distribution-Shift Detection with RKHS Models",
            "We study distribution shift in a new setting.",
        )

        ranked = score_paper(paper, self.config)

        self.assertEqual(ranked.score, 18.0)
        self.assertEqual(ranked.positive_matches, ("distribution shift", "RKHS"))

    def test_negative_keywords_subtract_from_score(self) -> None:
        paper = make_paper(
            "2601.00002",
            "A Survey of RKHS Methods",
            "This survey covers reproducible results.",
        )

        ranked = score_paper(paper, self.config)

        self.assertEqual(ranked.score, 3.0)
        self.assertEqual(ranked.negative_matches, ("survey",))

    def test_rank_papers_sorts_highest_score_first(self) -> None:
        low = make_paper("2601.00003", "Unrelated paper", "No matching terms.")
        high = make_paper("2601.00004", "RKHS theory", "An RKHS result.")

        ranked = rank_papers([low, high], self.config)

        self.assertEqual([item.paper.arxiv_id for item in ranked], ["2601.00004", "2601.00003"])


if __name__ == "__main__":
    unittest.main()

