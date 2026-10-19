from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass
class SheetsAdapter:
    spreadsheet_id: str
    service: Any

    @classmethod
    def from_service_account(cls, spreadsheet_id: str, service_account_info: dict) -> "SheetsAdapter":
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES,
        )
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return cls(spreadsheet_id=spreadsheet_id, service=service)

    def metadata(self) -> dict:
        return (
            self.service.spreadsheets()
            .get(spreadsheetId=self.spreadsheet_id, includeGridData=False)
            .execute()
        )

    def read_values(self, a1_range: str) -> list[list[str]]:
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=a1_range)
            .execute()
        )
        return result.get("values", [])

    def write_values_verified(self, a1_range: str, values: list[list[Any]]) -> None:
        (
            self.service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.spreadsheet_id,
                range=a1_range,
                valueInputOption="RAW",
                body={"values": values},
            )
            .execute()
        )

        actual = self.read_values(a1_range)
        expected = [["" if value is None else str(value) for value in row] for row in values]
        actual_normalized = [["" if value is None else str(value) for value in row] for row in actual]

        if actual_normalized != expected:
            raise RuntimeError(
                f"Read-back verification failed for {a1_range}: expected={expected!r}, actual={actual_normalized!r}"
            )
