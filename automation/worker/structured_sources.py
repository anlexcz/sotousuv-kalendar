from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin

import requests


USER_AGENT = "SotousuvKalendarBot/0.1 (+https://github.com/anlexcz/sotousuv-kalendar)"


@dataclass(frozen=True)
class StructuredCandidate:
    identity: str
    title: str
    detail_url: str | None
    event_date_from: str | None
    event_date_to: str | None
    published_at: str | None
    raw_kind: str


def fetch_text(url: str, accept: str) -> tuple[str, int, dict[str, str]]:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
        timeout=30,
    )
    response.raise_for_status()
    return response.text, response.status_code, dict(response.headers)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, names: Iterable[str]) -> str | None:
    wanted = {n.lower() for n in names}
    for child in list(element):
        if _local_name(child.tag) in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return None


def _atom_link(element: ET.Element) -> str | None:
    for child in list(element):
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "alternate").strip().lower()
        if href and rel in {"alternate", ""}:
            return href
    return None


def parse_rss_atom(text: str, base_url: str, limit: int = 5) -> list[StructuredCandidate]:
    root = ET.fromstring(text)
    root_name = _local_name(root.tag)

    if root_name == "rss":
        channel = next((c for c in list(root) if _local_name(c.tag) == "channel"), root)
        entries = [c for c in list(channel) if _local_name(c.tag) == "item"]
        kind = "RSS"
    elif root_name == "feed":
        entries = [c for c in list(root) if _local_name(c.tag) == "entry"]
        kind = "ATOM"
    else:
        raise ValueError(f"Unsupported feed root: {root_name}")

    out: list[StructuredCandidate] = []
    for entry in entries[:limit]:
        title = _child_text(entry, ["title"])
        if not title:
            continue

        if kind == "RSS":
            detail = _child_text(entry, ["link"])
            guid = _child_text(entry, ["guid"])
            published = _child_text(entry, ["pubDate", "date", "published", "updated"])
        else:
            detail = _atom_link(entry)
            guid = _child_text(entry, ["id"])
            published = _child_text(entry, ["published", "updated"])

        detail_url = urljoin(base_url, detail) if detail else None
        identity = guid or detail_url or title
        out.append(
            StructuredCandidate(
                identity=identity,
                title=re.sub(r"\s+", " ", title).strip(),
                detail_url=detail_url,
                event_date_from=None,
                event_date_to=None,
                published_at=published,
                raw_kind=kind,
            )
        )
    return out


def _unfold_ics(text: str) -> list[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for line in raw:
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _ics_value(line: str) -> tuple[str, str]:
    left, value = line.split(":", 1)
    key = left.split(";", 1)[0].upper()
    return key, value.strip()


def _ics_date(value: str) -> str | None:
    value = value.strip()
    if re.fullmatch(r"\d{8}", value):
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    if re.fullmatch(r"\d{8}T\d{6}Z?", value):
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    return None


def parse_ical(text: str, base_url: str, limit: int = 5) -> list[StructuredCandidate]:
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = _ics_value(line)
        if key in {"UID", "SUMMARY", "URL", "DTSTART", "DTEND", "LAST-MODIFIED", "DTSTAMP"}:
            current[key] = value

    candidates: list[StructuredCandidate] = []
    for event in events:
        title = event.get("SUMMARY", "").replace("\\,", ",").replace("\\n", " ").strip()
        if not title:
            continue
        start = _ics_date(event.get("DTSTART", ""))
        end = _ics_date(event.get("DTEND", ""))
        # RFC5545 all-day DTEND is exclusive. For safety we do not decrement it here;
        # resolver can interpret exact interval semantics later. Single-day events keep only DTSTART.
        if end == start:
            end = None
        detail = event.get("URL")
        detail_url = urljoin(base_url, detail) if detail else None
        identity = event.get("UID") or detail_url or f"{title}|{start or ''}"
        candidates.append(
            StructuredCandidate(
                identity=identity,
                title=re.sub(r"\s+", " ", title).strip(),
                detail_url=detail_url,
                event_date_from=start,
                event_date_to=end,
                published_at=event.get("LAST-MODIFIED") or event.get("DTSTAMP"),
                raw_kind="ICAL",
            )
        )

    # Prefer upcoming/dated items, then deterministic title order; cap output.
    today = datetime.now(timezone.utc).date().isoformat()
    candidates.sort(key=lambda c: (c.event_date_from is None, c.event_date_from or "9999-99-99", c.title))
    upcoming = [c for c in candidates if c.event_date_from is None or c.event_date_from >= today]
    return (upcoming or candidates)[:limit]


def stable_finding_id(source_id: str, identity: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{identity}".encode("utf-8")).hexdigest()[:16].upper()
    return f"FND-{digest}"


def stable_observation_id(source_id: str, finding_id: str, field_key: str, value: str) -> str:
    digest = hashlib.sha256(
        f"{source_id}|{finding_id}|{field_key}|{value}".encode("utf-8")
    ).hexdigest()[:20].upper()
    return f"OBS-{digest}"
