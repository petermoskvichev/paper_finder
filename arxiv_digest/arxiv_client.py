"""Minimal client for the official arXiv Atom API."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from .config import CategoryGroup
from .models import Paper

API_URL = "https://export.arxiv.org/api/query"
ATOM = "http://www.w3.org/2005/Atom"
NAMESPACES = {"atom": ATOM}
VERSION_SUFFIX = re.compile(r"v\d+$")


class ArxivAPIError(RuntimeError):
    """Raised when arXiv cannot be reached or returns invalid data."""


class ArxivClient:
    """Fetch recent paper metadata from the official arXiv API."""

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.sleep = sleep
        self.session.headers.update(
            {"User-Agent": "paper-finder/0.2 (personal research digest)"}
        )

    def fetch_recent(
        self,
        category_groups: tuple[CategoryGroup, ...],
        lookback_hours: int,
        request_delay_seconds: float,
    ) -> list[Paper]:
        """Query each category group, then filter and deduplicate the results."""
        papers: list[Paper] = []
        for index, group in enumerate(category_groups):
            if index:
                self.sleep(request_delay_seconds)
            papers.extend(self._fetch_group(group))

        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        requested_categories = {
            category for group in category_groups for category in group.categories
        }

        deduplicated: dict[str, Paper] = {}
        for paper in papers:
            if paper.published_at < cutoff:
                continue
            if requested_categories.isdisjoint(paper.categories):
                continue
            deduplicated.setdefault(paper.arxiv_id, paper)

        return sorted(
            deduplicated.values(),
            key=lambda paper: paper.published_at,
            reverse=True,
        )

    def _fetch_group(self, group: CategoryGroup) -> list[Paper]:
        """Fetch one bounded page for a related group of categories."""
        category_query = " OR ".join(
            f"cat:{category}" for category in group.categories
        )
        params = {
            "search_query": category_query,
            "start": 0,
            "max_results": group.fetch_limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = self.session.get(
                API_URL,
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ArxivAPIError(
                f"arXiv API request failed for category group '{group.name}': {exc}"
            ) from exc

        return self._parse_feed(response.content)

    @staticmethod
    def _parse_feed(content: bytes) -> list[Paper]:
        """Parse an arXiv Atom response into paper models."""
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ArxivAPIError("arXiv returned an invalid Atom response.") from exc

        papers: list[Paper] = []
        for entry in root.findall("atom:entry", NAMESPACES):
            raw_id = _required_text(entry, "atom:id")
            arxiv_id = _base_arxiv_id(raw_id)
            published_at = _parse_datetime(_required_text(entry, "atom:published"))
            authors = tuple(
                _clean_text(author.findtext("atom:name", default="", namespaces=NAMESPACES))
                for author in entry.findall("atom:author", NAMESPACES)
            )
            categories = tuple(
                category.attrib["term"]
                for category in entry.findall("atom:category", NAMESPACES)
                if category.attrib.get("term")
            )

            papers.append(
                Paper(
                    arxiv_id=arxiv_id,
                    title=_clean_text(_required_text(entry, "atom:title")),
                    authors=tuple(author for author in authors if author),
                    abstract=_clean_text(_required_text(entry, "atom:summary")),
                    categories=categories,
                    published_at=published_at,
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                )
            )
        return papers


def _required_text(entry: ET.Element, path: str) -> str:
    value = entry.findtext(path, default="", namespaces=NAMESPACES).strip()
    if not value:
        raise ArxivAPIError(f"arXiv response entry is missing '{path}'.")
    return value


def _base_arxiv_id(raw_id: str) -> str:
    path = urlparse(raw_id).path
    identifier = path.split("/abs/", maxsplit=1)[-1].strip("/")
    if not identifier:
        raise ArxivAPIError("arXiv response contained an invalid paper ID.")
    return VERSION_SUFFIX.sub("", identifier)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArxivAPIError(f"arXiv returned an invalid date: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
