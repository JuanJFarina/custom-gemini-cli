from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any

import gspread
from gspread.utils import ValueInputOption, ValueRenderOption
from google.oauth2.service_account import Credentials


GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass(frozen=True)
class GoogleSheetsSettings:
    spreadsheet_id: str
    service_account_info: dict[str, Any]


class GoogleSheetsClient:
    def __init__(self, settings: GoogleSheetsSettings) -> None:
        self._settings = settings
        self._spreadsheet: Any | None = None

    @property
    def spreadsheet(self) -> Any:
        if self._spreadsheet is None:
            self._spreadsheet = self._open_spreadsheet()
        return self._spreadsheet

    def _open_spreadsheet(self) -> Any:
        credentials = Credentials.from_service_account_info(
            self._settings.service_account_info,
            scopes=GOOGLE_SHEETS_SCOPES,
        )
        return gspread.authorize(credentials).open_by_key(self._settings.spreadsheet_id)

    def get_formula(self, *, sheet_name: str, cell: str) -> str:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        value = worksheet.acell(
            cell,
            value_render_option=ValueRenderOption.formula,
        ).value
        return str(value or "")

    def update_formula(self, *, sheet_name: str, cell: str, formula: str) -> None:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        worksheet.update(
            [[formula]],
            range_name=cell,
            value_input_option=ValueInputOption.user_entered,
        )


def load_google_sheets_settings_from_env() -> GoogleSheetsSettings | None:
    spreadsheet_id = os.environ.get("EXPENSES_SPREADSHEET_ID")
    encoded_credentials = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")
    if not spreadsheet_id or not encoded_credentials:
        return None

    return GoogleSheetsSettings(
        spreadsheet_id=spreadsheet_id,
        service_account_info=_decode_service_account_info(encoded_credentials),
    )


def _decode_service_account_info(encoded_credentials: str) -> dict[str, Any]:
    decoded = base64.b64decode(encoded_credentials).decode("utf-8")
    payload = json.loads(decoded)
    if not isinstance(payload, dict):
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 must decode to a JSON object.")
    return payload

