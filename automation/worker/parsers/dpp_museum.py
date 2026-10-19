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
    node = heading.next_sibling
    while node is not None:
        if isinstance(node, Tag):
            if node.name in {"h2", "h3"}:
                return None
            if node.name == "a" and node.get("href"):
                return urljoin(base_url, node["href"])
            link = node.find("a", href=True)
            if link is not None:
                return urljoin(base_url, link["href"])
        node = node.next_sibling
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
    node = start.find_next()
    while node is not None:
        if isinstance(node, Tag) and node.name == "h2":
            break
        if isinstance(node, Tag) and node.name == "h3":
            raw_heading = node.get_text(" ", strip=True)
            title, date_from = _parse_heading(raw_heading)
            candidates.append(
                Candidate(
                    title=title,
                    detail_url=_next_detail_url(node, base_url),
                    date_from=date_from,
                    raw_heading=raw_heading,
                )
            )
        node = node.find_next()

    return candidates
