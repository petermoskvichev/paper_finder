"""Tests for grouped arXiv retrieval and cross-list deduplication."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from arxiv_digest.arxiv_client import ArxivClient
from arxiv_digest.config import CategoryGroup


def atom_feed(arxiv_id: str, categories: tuple[str, ...]) -> bytes:
    published = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    category_xml = "".join(f'<category term="{item}" />' for item in categories)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v1</id>
    <published>{published}</published>
    <title>A cross-listed result</title>
    <summary>A useful abstract.</summary>
    <author><name>Example Author</name></author>
    {category_xml}
  </entry>
</feed>""".encode()


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.headers: dict[str, str] = {}
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def get(self, _url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class ArxivClientTests(unittest.TestCase):
    def test_category_groups_are_queried_separately_and_deduplicated(self) -> None:
        session = FakeSession(
            [
                FakeResponse(atom_feed("2608.00001", ("cs.LG", "math.CT"))),
                FakeResponse(atom_feed("2608.00001", ("cs.LG", "math.CT"))),
            ]
        )
        delays: list[float] = []
        client = ArxivClient(session=session, sleep=delays.append)  # type: ignore[arg-type]
        groups = (
            CategoryGroup("machine_learning", ("cs.LG",), 100),
            CategoryGroup("category_theory", ("math.CT",), 50),
        )

        papers = client.fetch_recent(groups, 48, 3.0)

        self.assertEqual(len(session.calls), 2)
        self.assertEqual(delays, [3.0])
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].arxiv_id, "2608.00001")
        self.assertEqual(session.calls[0]["params"]["max_results"], 100)  # type: ignore[index]
        self.assertEqual(session.calls[1]["params"]["max_results"], 50)  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
