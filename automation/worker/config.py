from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    cloudflare_account_id: str | None
    cloudflare_d1_database_id: str | None
    cloudflare_api_token: str | None
    spreadsheet_id: str | None
    service_account_info: dict | None
    timezone: str = "Europe/Prague"
    public_export_path: str = "data/events.json"

    @property
    def d1_configured(self) -> bool:
        return bool(
            self.cloudflare_account_id
            and self.cloudflare_d1_database_id
            and self.cloudflare_api_token
        )

    @property
    def sheets_configured(self) -> bool:
        return bool(self.spreadsheet_id and self.service_account_info)


def _load_google_credentials() -> dict | None:
    raw_credentials = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw_credentials:
        return None
    try:
        return json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc


def load_settings() -> Settings:
    return Settings(
        cloudflare_account_id=os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip() or None,
        cloudflare_d1_database_id=os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip() or None,
        cloudflare_api_token=os.environ.get("CLOUDFLARE_API_TOKEN", "").strip() or None,
        spreadsheet_id=os.environ.get("GOOGLE_SHEET_ID", "").strip() or None,
        service_account_info=_load_google_credentials(),
        timezone=os.environ.get("CALENDAR_TIMEZONE", "Europe/Prague"),
        public_export_path=os.environ.get("PUBLIC_EXPORT_PATH", "data/events.json"),
    )
