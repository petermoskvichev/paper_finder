"""Tests for grouped arXiv retrieval and cross-list deduplication."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

import requests

from arxiv_digest.arxiv_client import (
    ArxivAPIError,
    ArxivClient,
    latest_announcement_submission_window,
)
from arxiv_digest.config import CategoryGroup


def atom_feed(
    arxiv_id: str,
    categories: tuple[str, ...],
    published_at: datetime | None = None,
) -> bytes:
    published = (published_at or datetime.now(timezone.utc)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
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
    def __init__(
        self,
        content: bytes,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} Client Error")
            error.response = self  # type: ignore[assignment]
            raise error


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
        self.assertIn(
            "submittedDate:[",
            session.calls[0]["params"]["search_query"],  # type: ignore[index]
        )

    def test_429_is_retried_with_retry_after_delay(self) -> None:
        reference_time = datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc)
        session = FakeSession(
            [
                FakeResponse(b"Rate exceeded", 429, {"Retry-After": "7"}),
                FakeResponse(
                    atom_feed(
                        "2608.00002",
                        ("stat.ML",),
                        datetime(2026, 8, 18, 1, 0, tzinfo=timezone.utc),
                    )
                ),
            ]
        )
        delays: list[float] = []
        client = ArxivClient(
            session=session,  # type: ignore[arg-type]
            sleep=delays.append,
            now=lambda: reference_time,
        )

        papers = client.fetch_recent(
            (CategoryGroup("statistics", ("stat.ML",), 100),),
            48,
            3.0,
        )

        self.assertEqual(len(papers), 1)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(delays, [7.0])

    def test_non_retryable_client_error_fails_immediately(self) -> None:
        session = FakeSession([FakeResponse(b"Bad request", 400)])
        delays: list[float] = []
        client = ArxivClient(
            session=session,  # type: ignore[arg-type]
            sleep=delays.append,
        )

        with self.assertRaises(ArxivAPIError):
            client.fetch_recent(
                (CategoryGroup("statistics", ("stat.ML",), 100),),
                48,
                3.0,
            )

        self.assertEqual(len(session.calls), 1)
        self.assertEqual(delays, [])

    def test_singapore_monday_uses_sunday_announcement_window(self) -> None:
        # 08:15 Monday in Singapore is 20:15 Sunday in US Eastern during DST.
        start, end = latest_announcement_submission_window(
            datetime(2026, 8, 10, 0, 15, tzinfo=timezone.utc)
        )

        self.assertEqual(start, datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc))

    def test_monday_us_announcement_includes_weekend_submissions(self) -> None:
        start, end = latest_announcement_submission_window(
            datetime(2026, 8, 11, 0, 15, tzinfo=timezone.utc)
        )

        self.assertEqual(start, datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc))

    def test_fixed_singapore_time_uses_latest_available_winter_batch(self) -> None:
        # At 08:15 Singapore in January it is still 19:15 Sunday Eastern, so the
        # latest available announcement is Thursday's rather than Sunday's.
        start, end = latest_announcement_submission_window(
            datetime(2026, 1, 12, 0, 15, tzinfo=timezone.utc)
        )

        self.assertEqual(start, datetime(2026, 1, 7, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 1, 8, 19, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
