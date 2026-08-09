"""Tests for lexical and semantic ranking."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from arxiv_digest.config import RankingConfig, ResearchTheme, SemanticConfig
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
            themes=(
                ResearchTheme(
                    name="Distribution shift",
                    description="Learning when training and deployment data differ.",
                    aliases=("distribution shift",),
                    weight=4.0,
                ),
                ResearchTheme(
                    name="Kernel methods",
                    description="Kernel methods in reproducing kernel Hilbert spaces.",
                    aliases=("RKHS",),
                    weight=3.0,
                ),
            ),
            negative_keywords={"survey": 1.0},
            semantic=SemanticConfig(
                enabled=False,
                model_name="unused",
                semantic_weight=0.7,
                lexical_weight=0.3,
                min_similarity=0.25,
                top_theme_matches=3,
            ),
        )

    def test_title_matches_receive_multiplier_and_hyphens_are_normalised(self) -> None:
        paper = make_paper(
            "2601.00001",
            "Distribution-Shift Detection with RKHS Models",
            "We study distribution shift in a new setting.",
        )

        ranked = score_paper(paper, self.config)

        self.assertEqual(ranked.score, 18.0)
        self.assertEqual(
            ranked.positive_matches, ("Distribution shift", "Kernel methods")
        )

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

    def test_semantic_ranking_finds_a_paraphrase_without_exact_aliases(self) -> None:
        config = RankingConfig(
            max_papers=10,
            title_multiplier=2.0,
            themes=(
                ResearchTheme(
                    name="Reliable ML",
                    description="Dependable learning systems under failures.",
                    aliases=("trustworthy ML",),
                    weight=1.0,
                ),
            ),
            negative_keywords={},
            semantic=SemanticConfig(
                enabled=True,
                model_name="fake-model",
                semantic_weight=0.7,
                lexical_weight=0.3,
                min_similarity=0.25,
                top_theme_matches=2,
            ),
        )
        relevant = make_paper(
            "2601.00005",
            "Failure-resistant learning systems",
            "We make predictive models dependable in hostile deployment settings.",
        )
        unrelated = make_paper(
            "2601.00006",
            "A stellar catalogue",
            "We measure the spectra of nearby stars.",
        )

        class FakeEmbedder:
            def encode(self, sentences: list[str], **_: object) -> list[list[float]]:
                vectors = []
                for sentence in sentences:
                    if sentence.startswith("Dependable"):
                        vectors.append([1.0, 0.0])
                    elif "Failure-resistant" in sentence:
                        vectors.append([0.95, 0.31])
                    else:
                        vectors.append([0.0, 1.0])
                return vectors

        ranked = rank_papers([unrelated, relevant], config, embedder=FakeEmbedder())

        self.assertEqual(ranked[0].paper.arxiv_id, relevant.arxiv_id)
        self.assertEqual(ranked[0].positive_matches, ())
        self.assertEqual(ranked[0].semantic_matches[0].name, "Reliable ML")
        self.assertGreater(ranked[0].score, ranked[1].score)


if __name__ == "__main__":
    unittest.main()
