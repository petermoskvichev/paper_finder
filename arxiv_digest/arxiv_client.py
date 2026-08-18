"""Minimal client for the official arXiv Atom API."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from .config import CategoryGroup
from .models import Paper

API_URL = "https://export.arxiv.org/api/query"
ATOM = "http://www.w3.org/2005/Atom"
NAMESPACES = {"atom": ATOM}
VERSION_SUFFIX = re.compile(r"v\d+$")
ARXIV_TIMEZONE = ZoneInfo("America/New_York")
ANNOUNCEMENT_DAYS = {0, 1, 2, 3, 6}  # Monday-Thursday and Sunday.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


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
        now: Callable[[], datetime] | None = None,
        max_attempts: int = 4,
        retry_backoff_seconds: float = 30.0,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.sleep = sleep
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.session.headers.update(
            {"User-Agent": "paper-finder/0.2 (personal research digest)"}
        )

    def fetch_recent(
        self,
        category_groups: tuple[CategoryGroup, ...],
        lookback_hours: int,
        request_delay_seconds: float,
        use_announcement_window: bool = False,
    ) -> list[Paper]:
        """Query each category group, then filter and deduplicate the results."""
        reference_time = self.now()
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        reference_time = reference_time.astimezone(timezone.utc)

        if use_announcement_window:
            window_start, window_end = latest_announcement_submission_window(
                reference_time
            )
        else:
            window_start = reference_time - timedelta(hours=lookback_hours)
            window_end = reference_time

        papers: list[Paper] = []
        for index, group in enumerate(category_groups):
            if index:
                self.sleep(request_delay_seconds)
            papers.extend(self._fetch_group(group, window_start, window_end))

        requested_categories = {
            category for group in category_groups for category in group.categories
        }

        deduplicated: dict[str, Paper] = {}
        for paper in papers:
            if not window_start <= paper.published_at < window_end:
                continue
            if requested_categories.isdisjoint(paper.categories):
                continue
            deduplicated.setdefault(paper.arxiv_id, paper)

        return sorted(
            deduplicated.values(),
            key=lambda paper: paper.published_at,
            reverse=True,
        )

    def _fetch_group(
        self,
        group: CategoryGroup,
        window_start: datetime,
        window_end: datetime,
    ) -> list[Paper]:
        """Fetch one bounded page for a related group of categories."""
        category_query = " OR ".join(
            f"cat:{category}" for category in group.categories
        )
        date_query = (
            f"submittedDate:[{window_start:%Y%m%d%H%M} TO "
            f"{window_end:%Y%m%d%H%M}]"
        )
        params = {
            "search_query": f"({category_query}) AND {date_query}",
            "start": 0,
            "max_results": group.fetch_limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        response = self._get_with_retries(group, params)

        return self._parse_feed(response.content)

    def _get_with_retries(
        self, group: CategoryGroup, params: dict[str, object]
    ) -> requests.Response:
        """Fetch a feed, backing off when arXiv is busy or temporarily unavailable."""
        last_error: requests.RequestException | None = None
        attempts_made = 0
        for attempt in range(1, self.max_attempts + 1):
            attempts_made = attempt
            try:
                response = self.session.get(
                    API_URL,
                    params=params,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                status_code = getattr(exc.response, "status_code", None)
                retryable = status_code in RETRYABLE_STATUS_CODES or status_code is None
                if not retryable or attempt == self.max_attempts:
                    break
                retry_after = _retry_after_seconds(
                    getattr(exc.response, "headers", {}).get("Retry-After"),
                    reference_time=self.now(),
                )
                delay = (
                    retry_after
                    if retry_after is not None
                    else self.retry_backoff_seconds * (2 ** (attempt - 1))
                )
                self.sleep(delay)

        attempts = f" after {attempts_made} attempts" if attempts_made > 1 else ""
        raise ArxivAPIError(
            f"arXiv API request failed for category group '{group.name}'{attempts}: "
            f"{last_error}"
        ) from last_error

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


def latest_announcement_submission_window(
    reference_time: datetime,
) -> tuple[datetime, datetime]:
    """Return the submission interval belonging to arXiv's latest announcement."""
    if reference_time.tzinfo is None:
        raise ValueError("reference_time must include a timezone")

    eastern_time = reference_time.astimezone(ARXIV_TIMEZONE)
    announcement_date: date | None = None
    for days_ago in range(8):
        candidate_date = eastern_time.date() - timedelta(days=days_ago)
        if candidate_date.weekday() not in ANNOUNCEMENT_DAYS:
            continue
        candidate = datetime.combine(
            candidate_date,
            datetime_time(hour=20),
            tzinfo=ARXIV_TIMEZONE,
        )
        if candidate <= eastern_time:
            announcement_date = candidate_date
            break

    if announcement_date is None:  # Defensive; a valid day always exists in 8 days.
        raise ArxivAPIError("Could not determine the latest arXiv announcement window.")

    weekday = announcement_date.weekday()
    if weekday == 6:  # Sunday's announcement contains Thursday-Friday submissions.
        start_date = announcement_date - timedelta(days=3)
        end_date = announcement_date - timedelta(days=2)
    elif weekday == 0:  # Monday contains submissions received over the weekend.
        start_date = announcement_date - timedelta(days=3)
        end_date = announcement_date
    else:
        start_date = announcement_date - timedelta(days=1)
        end_date = announcement_date

    start = datetime.combine(
        start_date,
        datetime_time(hour=14),
        tzinfo=ARXIV_TIMEZONE,
    )
    end = datetime.combine(
        end_date,
        datetime_time(hour=14),
        tzinfo=ARXIV_TIMEZONE,
    )
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _retry_after_seconds(
    value: str | None,
    *,
    reference_time: datetime,
) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - reference_time).total_seconds())
