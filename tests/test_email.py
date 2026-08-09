"""Tests for reusable digest rendering and MIME message creation."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from arxiv_digest.digest import render_digest
from arxiv_digest.email_digest import render_html_digest
from arxiv_digest.gmail_sender import build_email_message
from arxiv_digest.models import Paper, RankedPaper, ThemeMatch


def make_ranked_paper(abstract: str) -> RankedPaper:
    paper = Paper(
        arxiv_id="2608.00001",
        title="Safe <Reliable> Learning",
        authors=("Ada Example", "Grace Example"),
        abstract=abstract,
        categories=("cs.LG", "stat.ML"),
        published_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        url="https://arxiv.org/abs/2608.00001",
    )
    return RankedPaper(
        paper=paper,
        score=8.0,
        positive_matches=("trustworthy machine learning",),
        negative_matches=(),
        lexical_score=4.0,
        semantic_score=0.82,
        semantic_matches=(ThemeMatch("Reliable ML", 0.81),),
    )


class EmailTests(unittest.TestCase):
    def test_empty_digest_can_be_used_as_email_body(self) -> None:
        body = render_digest([], 48, ("cs.LG", "stat.ML"))

        self.assertIn("Papers shown: 0", body)
        self.assertIn("No papers were published", body)

    def test_email_message_contains_plain_text_and_html_alternatives(self) -> None:
        message = build_email_message(
            sender="sender@example.com",
            recipient="reader@example.com",
            subject="Daily digest",
            body="One interesting paper.",
            html_body="<p>One <strong>interesting</strong> paper.</p>",
        )

        self.assertEqual(message["From"], "sender@example.com")
        self.assertEqual(message["To"], "reader@example.com")
        self.assertEqual(message["Subject"], "Daily digest")
        self.assertTrue(message.is_multipart())
        plain = message.get_body(preferencelist=("plain",))
        html = message.get_body(preferencelist=("html",))
        self.assertIsNotNone(plain)
        self.assertIsNotNone(html)
        self.assertEqual(plain.get_content().strip(), "One interesting paper.")
        self.assertIn("<strong>interesting</strong>", html.get_content())

    def test_email_renderers_include_the_complete_abstract(self) -> None:
        ending = "COMPLETE_ABSTRACT_END"
        abstract = "A detailed result. " * 80 + ending
        ranked = make_ranked_paper(abstract)

        plain = render_digest([ranked], 168, ("cs.LG",), abstract_length=None)
        html = render_html_digest([ranked], 168, ("cs.LG",))

        self.assertIn(ending, plain)
        self.assertIn(ending, html)

    def test_html_renderer_escapes_paper_metadata(self) -> None:
        html = render_html_digest(
            [make_ranked_paper("An abstract with <script>alert('x')</script> text.")],
            48,
            ("cs.LG",),
        )

        self.assertIn("Safe &lt;Reliable&gt; Learning", html)
        self.assertIn("Reliable ML 81%", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
