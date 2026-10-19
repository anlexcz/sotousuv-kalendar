from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag


_DATE_PREFIX = re.compile(
    r"^\s*(?P<day>\d{1,2})\.\s*(?P<month>\d{1,2})\.\s*(?P<year>\d{4})\s*:\s*(?P<title>.+?)\s*$"
)


@dataclass(frozen=True)
class Candidate:
    title: str
    detail_url: str | None
    date_from: str | None
    raw_heading: str


def _next_detail_url(heading: Tag, base_url: str) -> str | None:
    for node in heading.find_all_next(["a", "h2", "h3"]):
        if node.name in {"h2", "h3"}:
            return None
        href = node.get("href")
        if href:
            return urljoin(base_url, href)
    return None


def _parse_heading(text: str) -> tuple[str, str | None]:
    normalized = " ".join(text.split())
    match = _DATE_PREFIX.match(normalized)
    if not match:
        return normalized, None

    try:
        parsed = date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return normalized, None

    return match.group("title").strip(), parsed.isoformat()


def parse_current_events(html: str, base_url: str) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")

    start = None
    for heading in soup.find_all("h2"):
        if "aktuální akce" in heading.get_text(" ", strip=True).casefold():
            start = heading
            break

    if start is None:
        raise ValueError("Section 'Aktuální akce' not found")

    candidates: list[Candidate] = []
    for heading in start.find_all_next(["h2", "h3"]):
        if heading is start:
            continue
        if heading.name == "h2":
            break

        raw_heading = heading.get_text(" ", strip=True)
        title, date_from = _parse_heading(raw_heading)
        candidates.append(
            Candidate(
                title=title,
                detail_url=_next_detail_url(heading, base_url),
                date_from=date_from,
                raw_heading=raw_heading,
            )
        )

    return candidates
