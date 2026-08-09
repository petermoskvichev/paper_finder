"""Render a polished, email-safe HTML research digest."""

from __future__ import annotations

from html import escape

from .models import RankedPaper


def _badge(text: str, background: str, foreground: str) -> str:
    return (
        '<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 9px;'
        f'border-radius:999px;background:{background};color:{foreground};'
        'font-size:12px;line-height:16px;font-weight:600;">'
        f"{escape(text)}</span>"
    )


def _paper_card(index: int, ranked: RankedPaper) -> str:
    paper = ranked.paper
    category_badges = "".join(
        _badge(category, "#eef2ff", "#4338ca") for category in paper.categories
    )
    match_badges = "".join(
        _badge(keyword, "#ecfdf5", "#047857")
        for keyword in ranked.positive_matches
    )
    semantic_badges = "".join(
        _badge(
            f"{match.name} {match.similarity:.0%}",
            "#f5f3ff",
            "#6d28d9",
        )
        for match in ranked.semantic_matches
    )
    penalty_badges = "".join(
        _badge(keyword, "#fff7ed", "#c2410c")
        for keyword in ranked.negative_matches
    )
    matches = ""
    if semantic_badges:
        matches += (
            '<div style="margin-top:13px;"><span style="font-size:12px;'
            'font-weight:700;color:#64748b;margin-right:8px;">SEMANTIC</span>'
            f"{semantic_badges}</div>"
        )
    if match_badges:
        matches += (
            '<div style="margin-top:7px;"><span style="font-size:12px;'
            'font-weight:700;color:#64748b;margin-right:8px;">EXACT THEMES</span>'
            f"{match_badges}</div>"
        )
    if penalty_badges:
        matches += (
            '<div style="margin-top:7px;"><span style="font-size:12px;'
            'font-weight:700;color:#64748b;margin-right:8px;">PENALTIES</span>'
            f"{penalty_badges}</div>"
        )

    return f"""
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="margin:0 0 18px 0;background:#ffffff;border:1px solid #e2e8f0;
                    border-radius:14px;border-collapse:separate;overflow:hidden;">
        <tr>
          <td style="padding:24px 26px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
              <tr>
                <td style="vertical-align:top;padding-right:14px;">
                  <div style="font-size:12px;line-height:18px;font-weight:700;
                              letter-spacing:.08em;color:#64748b;">PAPER {index}</div>
                </td>
                <td style="vertical-align:top;text-align:right;white-space:nowrap;">
                  <span style="display:inline-block;padding:6px 11px;border-radius:999px;
                               background:#dbeafe;color:#1d4ed8;font-size:13px;
                               line-height:18px;font-weight:700;">Score {ranked.score:.2f}</span>
                </td>
              </tr>
            </table>
            <h2 style="margin:10px 0 8px 0;font-family:Arial,Helvetica,sans-serif;
                       font-size:21px;line-height:29px;font-weight:700;color:#0f172a;">
              <a href="{escape(paper.url, quote=True)}"
                 style="color:#0f172a;text-decoration:none;">{escape(paper.title)}</a>
            </h2>
            <div style="font-size:14px;line-height:22px;color:#475569;">
              {escape(', '.join(paper.authors))}
            </div>
            <div style="margin-top:9px;font-size:13px;line-height:20px;color:#64748b;">
              Submitted {paper.published_at:%d %b %Y, %H:%M UTC}
              &nbsp;&bull;&nbsp; arXiv:{escape(paper.arxiv_id)}
            </div>
            <div style="margin-top:5px;font-size:12px;line-height:18px;color:#94a3b8;">
              Semantic {ranked.semantic_score:.2f}
              &nbsp;&bull;&nbsp; Exact-match signal {ranked.lexical_score:.2f}
            </div>
            <div style="margin-top:13px;">{category_badges}</div>
            {matches}
            <div style="height:1px;background:#e2e8f0;margin:17px 0 16px 0;"></div>
            <div style="font-size:12px;line-height:18px;font-weight:700;
                        letter-spacing:.08em;color:#64748b;margin-bottom:6px;">ABSTRACT</div>
            <div style="font-size:15px;line-height:24px;color:#334155;">
              {escape(paper.abstract)}
            </div>
            <div style="margin-top:19px;">
              <a href="{escape(paper.url, quote=True)}"
                 style="display:inline-block;padding:10px 16px;border-radius:8px;
                        background:#2563eb;color:#ffffff;text-decoration:none;
                        font-size:14px;line-height:20px;font-weight:700;">
                View on arXiv &rarr;
              </a>
            </div>
          </td>
        </tr>
      </table>"""


def render_html_digest(
    ranked_papers: list[RankedPaper],
    lookback_hours: int,
    categories: tuple[str, ...],
) -> str:
    """Render ranked papers as responsive HTML with complete abstracts."""
    category_summary = " &nbsp;&bull;&nbsp; ".join(
        escape(category) for category in categories
    )
    cards = "".join(
        _paper_card(index, ranked)
        for index, ranked in enumerate(ranked_papers, start=1)
    )
    if not cards:
        cards = """
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;
                    border-collapse:separate;">
        <tr><td style="padding:36px 26px;text-align:center;color:#64748b;
                       font-size:15px;line-height:24px;">
          No papers were published in the configured window.
        </td></tr>
      </table>"""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>arXiv research digest</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
    {len(ranked_papers)} ranked research papers selected for you.
  </div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="width:100%;background:#f1f5f9;">
    <tr>
      <td align="center" style="padding:28px 12px 42px 12px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="width:100%;max-width:760px;">
          <tr>
            <td style="padding:30px 30px 28px 30px;background:#0f172a;
                       border-radius:16px 16px 0 0;border-bottom:4px solid #3b82f6;">
              <div style="font-size:13px;line-height:20px;font-weight:700;
                          letter-spacing:.12em;color:#93c5fd;">PERSONAL RESEARCH RADAR</div>
              <h1 style="margin:7px 0 8px 0;font-size:30px;line-height:38px;
                         color:#ffffff;font-weight:700;">Your arXiv digest</h1>
              <div style="font-size:14px;line-height:22px;color:#cbd5e1;">
                {len(ranked_papers)} papers from the last {lookback_hours} hours
              </div>
              <div style="margin-top:6px;font-size:13px;line-height:21px;color:#94a3b8;">
                {category_summary}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:22px 0 0 0;">
              {cards}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 20px 0 20px;text-align:center;color:#94a3b8;
                       font-size:12px;line-height:19px;">
              Ranked with your research themes using local semantic and exact-alias signals.
              Scores are relevance signals, not quality ratings.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
