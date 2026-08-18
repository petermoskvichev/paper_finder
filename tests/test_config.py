"""Tests for the structured research profile."""

from __future__ import annotations

import unittest
from pathlib import Path

from arxiv_digest.config import load_config


class ConfigTests(unittest.TestCase):
    def test_default_profile_loads_grouped_categories_and_themes(self) -> None:
        config = load_config(Path("profile.yaml"))

        self.assertEqual(
            config.arxiv.categories,
            ("cs.LG", "stat.ML", "cs.AI", "stat.ME"),
        )
        self.assertEqual(len(config.arxiv.category_groups), 1)
        self.assertEqual(config.arxiv.category_groups[0].fetch_limit, 700)
        self.assertEqual(config.arxiv.lookback_hours, 24)
        self.assertTrue(config.arxiv.use_announcement_window)
        self.assertEqual(config.ranking.max_papers, 5)
        self.assertTrue(config.ranking.semantic.enabled)
        self.assertIn(
            "trustworthy ML",
            next(
                theme.aliases
                for theme in config.ranking.themes
                if theme.name.startswith("Robust")
            ),
        )


if __name__ == "__main__":
    unittest.main()
