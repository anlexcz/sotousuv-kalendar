from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse

DISCOVERY_NAMES = {
    "Parní vlak – kalendář železničních akcí",
    "Týburcovo – nostalgické jízdy",
    "M131 Zážitky",
    "Vlakové zážitky",
    "Busportal – Veteráni",
    "Busportal – Akce",
    "Hravé stroje – kalendář dopravních akcí",
    "MotoMagazín – kalendář a muzea",
    "Sdružení dopravních podniků ČR – novinky",
    "Akce Plzeň",
    "Kraj blanických rytířů – kalendář akcí",
    "Město Černošice – kalendář akcí",
    "Plzeňský kraj – doprava / nostalgie",
    "Olomoucký kraj – doprava a nostalgie",
    "IDOL – aktuality",
    "Doprava Ústeckého kraje – turistické linky",
    "Prague City Tourism – historická doprava",
    "IDPK – Nostalgie",
    "Správa železnic – akce pro veřejnost",
}

PILOT_URL = "https://muzeum.dpp.cz/kalendar-akci"

TYPE_BY_STRATEGY = {
    "RSS_ATOM_FIRST": "RSS_ATOM",
    "ICAL_FIRST": "ICAL",
    "WORDPRESS_REST_OR_HTML": "WORDPRESS",
    "HTML_PARSER": "WEB",
    "SOCIAL_FALLBACK": "SOCIAL",
    "BLOCKED_OR_RATE_LIMITED": "WEB_BLOCKED",
    "RETRY_BACKOFF": "WEB_UNSTABLE",
}


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def same_host(a: str, b: str) -> bool:
    return bool(a and b and host(a) == host(b))


def role_for(name: str, url: str) -> str:
    h = host(url)
    if h in {"facebook.com", "instagram.com"}:
        return "SOCIAL"
    if name in DISCOVERY_NAMES:
        return "DISCOVERY"
    return "PRIMARY"


def parser_key(strategy: str, canonical_url: str) -> str:
    if canonical_url.rstrip("/") == PILOT_URL.rstrip("/"):
        return "DPP_MUSEUM_CALENDAR"
    return {
        "RSS_ATOM_FIRST": "GENERIC_FEED",
        "ICAL_FIRST": "GENERIC_ICAL",
        "WORDPRESS_REST_OR_HTML": "WORDPRESS_GENERIC",
        "SOCIAL_FALLBACK": "SOCIAL_FALLBACK",
    }.get(strategy, "")


def canonical_url(row: dict[str, str]) -> str:
    original = row["url"].strip()
    final = (row.get("final_url") or "").strip()
    status = int(float(row["status_code"])) if row.get("status_code") else None
    if final and status and 200 <= status < 400 and same_host(original, final):
        return final
    return original


def migration_status(row: dict[str, str], role: str, canonical: str) -> str:
    original = row["url"].strip()
    final = (row.get("final_url") or "").strip()
    status = int(float(row["status_code"])) if row.get("status_code") else None
    strategy = row.get("recommendation") or ""

    if canonical.rstrip("/") == PILOT_URL.rstrip("/"):
        return "ALREADY_PILOT"
    if role == "SOCIAL":
        return "FALLBACK_ONLY"
    if status == 404:
        return "REPLACE_URL"
    if final and status and 200 <= status < 400 and not same_host(original, final):
        return "REJECT_REDIRECT"
    if strategy in {"BLOCKED_OR_RATE_LIMITED", "RETRY_BACKOFF"}:
        return "MIGRATE_INACTIVE"
    if (row.get("ok") or "").strip().lower() in {"true", "1", "ano"}:
        return "MIGRATE"
    return "REVIEW"


def priority_for(role: str, status: str) -> int:
    priority = 1 if role == "PRIMARY" else 2 if role == "DISCOVERY" else 3
    if status in {"REPLACE_URL", "REJECT_REDIRECT", "MIGRATE_INACTIVE", "FALLBACK_ONLY", "REVIEW"}:
        priority = max(priority, 3)
    return priority


def check_policy(role: str, status: str, strategy: str) -> str:
    if status in {"REPLACE_URL", "REJECT_REDIRECT", "REVIEW"}:
        return "MANUAL_REVIEW"
    if strategy == "SOCIAL_FALLBACK":
        return "FALLBACK_7D"
    if strategy in {"BLOCKED_OR_RATE_LIMITED", "RETRY_BACKOFF"}:
        return "BACKOFF_72H"
    if role == "DISCOVERY":
        return "DISCOVERY_72H"
    return "ADAPTIVE"


def build_row(row: dict[str, str]) -> dict[str, str | int]:
    canonical = canonical_url(row)
    role = role_for(row["name"], canonical)
    status = migration_status(row, role, canonical)
    strategy = row.get("recommendation") or "HTML_PARSER"
    legacy_row = int(row["legacy_row"])
    status_code = row.get("status_code") or ""

    if status == "ALREADY_PILOT":
        source_id = "SRC-PILOT-DPP-MUSEUM"
    else:
        source_id = f"SRC-LEGACY-{legacy_row:03d}"

    source_type = TYPE_BY_STRATEGY.get(strategy, "WEB")
    scope = "DISCOVERY" if role in {"DISCOVERY", "SOCIAL"} else "BOTH"
    source_group = host(canonical).replace(".", "_").replace("-", "_").upper()

    note_bits = [f"legacy_row={legacy_row}", f"audit={strategy}"]
    if status_code:
        note_bits.append(f"http={int(float(status_code))}")
    if status == "REPLACE_URL":
        note_bits.append("legacy URL returned 404; locate replacement before activation")
    if status == "REJECT_REDIRECT":
        note_bits.append(f"unexpected cross-domain redirect to {row.get('final_url')}")

    return {
        "source_id": source_id,
        "label": row["name"],
        "url": canonical,
        "role": role,
        "source_scope": scope,
        "source_type": source_type,
        "fetch_strategy": strategy,
        "parser_key": parser_key(strategy, canonical),
        "check_policy": check_policy(role, status, strategy),
        "priority": priority_for(role, status),
        "active": "NE",
        "migration_status": status,
        "source_group": source_group,
        "platform": row.get("platform") or "",
        "status_code": status_code,
        "area": row.get("area") or "",
        "feed_url": ((row.get("feed_links") or "").split(" | ")[0]),
        "calendar_url": ((row.get("calendar_links") or "").split(" | ")[0]),
        "note": "; ".join(note_bits),
    }


def main() -> int:
    audit_path = Path("audit_output/source-audit.csv")
    if not audit_path.exists():
        raise RuntimeError("Run source audit first; source-audit.csv is missing")

    with audit_path.open("r", encoding="utf-8-sig", newline="") as handle:
        audited = list(csv.DictReader(handle))

    registry = [build_row(row) for row in audited]
    registry.sort(key=lambda row: int(str(row["note"]).split("legacy_row=")[1].split(";")[0]))

    output_path = Path("audit_output/migration-registry.csv")
    fields = list(registry[0].keys())
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(registry)

    counts: dict[str, int] = {}
    for row in registry:
        status = str(row["migration_status"])
        counts[status] = counts.get(status, 0) + 1

    print("Migration registry:")
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")
    print(f"  TOTAL: {len(registry)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
