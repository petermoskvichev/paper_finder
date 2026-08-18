"""Render ranked papers as a readable terminal digest."""

from __future__ import annotations

from textwrap import shorten, wrap

from .models import RankedPaper

LINE_WIDTH = 100
ABSTRACT_LENGTH = 600


def _wrapped_lines(label: str, value: str) -> list[str]:
    prefix = f"   {label}: "
    return wrap(
        value,
        width=LINE_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
    ) or [prefix.rstrip()]


def render_digest(
    ranked_papers: list[RankedPaper],
    lookback_hours: int,
    categories: tuple[str, ...],
    abstract_length: int | None = ABSTRACT_LENGTH,
    window_description: str | None = None,
) -> str:
    """Render a digest, optionally limiting each abstract to a character count."""
    window = window_description or f"last {lookback_hours} hours"
    lines = [
        "arXiv research digest",
        f"Window: {window} | Categories: {', '.join(categories)}",
        f"Papers shown: {len(ranked_papers)}",
    ]

    if not ranked_papers:
        lines.extend(["", "No papers were published in the configured window."])
        return "\n".join(lines)

    for index, ranked in enumerate(ranked_papers, start=1):
        paper = ranked.paper
        lines.extend(["", f"{index}. {paper.title}"])
        lines.append(
            f"   Score: {ranked.score:.2f} | Submitted: "
            f"{paper.published_at:%Y-%m-%d %H:%M UTC} | arXiv: {paper.arxiv_id}"
        )
        if ranked.semantic_score:
            lines.append(
                f"   Semantic: {ranked.semantic_score:.2f} | "
                f"Lexical: {ranked.lexical_score:.2f}"
            )
        lines.extend(_wrapped_lines("Authors", ", ".join(paper.authors)))
        lines.extend(_wrapped_lines("Categories", ", ".join(paper.categories)))
        if ranked.positive_matches:
            lines.extend(
                _wrapped_lines("Exact themes", ", ".join(ranked.positive_matches))
            )
        if ranked.semantic_matches:
            semantic_matches = ", ".join(
                f"{match.name} ({match.similarity:.0%})"
                for match in ranked.semantic_matches
            )
            lines.extend(_wrapped_lines("Semantic themes", semantic_matches))
        if ranked.negative_matches:
            lines.extend(_wrapped_lines("Penalties", ", ".join(ranked.negative_matches)))
        lines.extend(_wrapped_lines("URL", paper.url))
        abstract = paper.abstract
        if abstract_length is not None:
            abstract = shorten(abstract, width=abstract_length, placeholder=" ...")
        lines.extend(_wrapped_lines("Abstract", abstract))

    return "\n".join(lines)


def print_digest(
    ranked_papers: list[RankedPaper],
    lookback_hours: int,
    categories: tuple[str, ...],
) -> None:
    """Print a rendered digest to standard output."""
    print(render_digest(ranked_papers, lookback_hours, categories))
