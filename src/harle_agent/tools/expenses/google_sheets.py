import asyncio
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import ValueInputOption, ValueRenderOption
from pydantic import BaseModel, Field

from harle_agent.settings import AgentSettings, get_agent_settings

GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetsClient(BaseModel):
    settings: AgentSettings = Field(default_factory=get_agent_settings)
    _spreadsheet: Any | None = None

    @property
    def spreadsheet(self) -> Any:
        if self._spreadsheet is None:
            self._spreadsheet = self._open_spreadsheet()
        return self._spreadsheet

    def _open_spreadsheet(self) -> Any:
        credentials = Credentials.from_service_account_info(
            self.settings.GOOGLE_SERVICE_ACCOUNT,
            scopes=GOOGLE_SHEETS_SCOPES,
        )
        return gspread.authorize(credentials).open_by_key(
            self.settings.EXPENSES_SPREADSHEET_ID,
        )

    async def get_formula(self, *, sheet_name: str, cell: str) -> str:
        return await asyncio.to_thread(
            self._get_formula_sync,
            sheet_name=sheet_name,
            cell=cell,
        )

    def _get_formula_sync(self, *, sheet_name: str, cell: str) -> str:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        value = worksheet.acell(
            cell,
            value_render_option=ValueRenderOption.formula,
        ).value
        return str(value or "")

    async def update_formula(self, *, sheet_name: str, cell: str, formula: str) -> None:
        await asyncio.to_thread(
            self._update_formula_sync,
            sheet_name=sheet_name,
            cell=cell,
            formula=formula,
        )

    def _update_formula_sync(self, *, sheet_name: str, cell: str, formula: str) -> None:
        worksheet = self.spreadsheet.worksheet(sheet_name)
        worksheet.update(
            [[formula]],
            range_name=cell,
            value_input_option=ValueInputOption.user_entered,
        )
