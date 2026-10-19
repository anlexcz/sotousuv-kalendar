from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    spreadsheet_id: str
    service_account_info: dict
    timezone: str = "Europe/Prague"
    public_export_path: str = "data/events.json"


def load_settings() -> Settings:
    spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    raw_credentials = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if not spreadsheet_id:
        raise RuntimeError("Missing GOOGLE_SHEET_ID")
    if not raw_credentials:
        raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON")

    try:
        service_account_info = json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    return Settings(
        spreadsheet_id=spreadsheet_id,
        service_account_info=service_account_info,
        timezone=os.environ.get("CALENDAR_TIMEZONE", "Europe/Prague"),
        public_export_path=os.environ.get("PUBLIC_EXPORT_PATH", "data/events.json"),
    )
