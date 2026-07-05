import asyncio
from typing import Any, Literal

import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import ValueInputOption, ValueRenderOption
from pydantic import BaseModel, Field, PrivateAttr

from harle_agent.settings import AgentSettings, get_agent_settings

from .constants import GOOGLE_SHEETS_SCOPES, SIMPLE_FORMULA_PATTERN

TargetYear = Literal["current_year", "next_year"]


class GoogleSheetsClient(BaseModel):
    settings: AgentSettings = Field(default_factory=get_agent_settings)
    _spreadsheets: dict[TargetYear, Any] = PrivateAttr(
        default_factory=dict,
    )

    @property
    def spreadsheet(self) -> Any:
        return self.get_spreadsheet()

    def get_spreadsheet(
        self,
        *,
        target_spreadsheet: TargetYear = "current_year",
    ) -> Any:
        if target_spreadsheet not in self._spreadsheets:
            self._spreadsheets[target_spreadsheet] = self._open_spreadsheet(
                target_spreadsheet=target_spreadsheet,
            )
        return self._spreadsheets[target_spreadsheet]

    def _open_spreadsheet(
        self,
        *,
        target_spreadsheet: TargetYear,
    ) -> Any:
        credentials = Credentials.from_service_account_info(
            self.settings.GOOGLE_SERVICE_ACCOUNT,
            scopes=GOOGLE_SHEETS_SCOPES,
        )
        return gspread.authorize(credentials).open_by_key(
            self._spreadsheet_id(target_spreadsheet=target_spreadsheet),
        )

    def _spreadsheet_id(
        self,
        *,
        target_spreadsheet: TargetYear,
    ) -> str:
        if target_spreadsheet == "current_year":
            return self.settings.EXPENSES_SPREADSHEET_ID
        if not self.settings.EXPENSES_NEXT_YEAR_SPREADSHEET_ID:
            raise ValueError(
                "EXPENSES_NEXT_YEAR_SPREADSHEET_ID must be configured before "
                "updating next year's expenses spreadsheet.",
            )
        return self.settings.EXPENSES_NEXT_YEAR_SPREADSHEET_ID

    async def get_formula(
        self,
        *,
        sheet_name: str,
        cell: str,
        target_spreadsheet: TargetYear = "current_year",
    ) -> str:
        return await asyncio.to_thread(
            self._get_formula_sync,
            sheet_name=sheet_name,
            cell=cell,
            target_spreadsheet=target_spreadsheet,
        )

    def _get_formula_sync(
        self,
        *,
        sheet_name: str,
        cell: str,
        target_spreadsheet: TargetYear,
    ) -> str:
        worksheet = self.get_spreadsheet(
            target_spreadsheet=target_spreadsheet,
        ).worksheet(sheet_name)
        value = worksheet.acell(
            cell,
            value_render_option=ValueRenderOption.formula,
        ).value
        return str(value or "")

    async def update_formula(
        self,
        *,
        sheet_name: str,
        cell: str,
        formula: str,
        target_spreadsheet: TargetYear = "current_year",
    ) -> None:
        await asyncio.to_thread(
            self._update_formula_sync,
            sheet_name=sheet_name,
            cell=cell,
            formula=formula,
            target_spreadsheet=target_spreadsheet,
        )

    def _update_formula_sync(
        self,
        *,
        sheet_name: str,
        cell: str,
        formula: str,
        target_spreadsheet: TargetYear,
    ) -> None:
        worksheet = self.get_spreadsheet(
            target_spreadsheet=target_spreadsheet,
        ).worksheet(sheet_name)
        worksheet.update(
            [[formula]],
            range_name=cell,
            value_input_option=ValueInputOption.user_entered,
        )

    def build_updated_formula(
        self,
        *,
        old_formula: str,
        amount: int | str,
        refund: bool,
    ) -> str:
        formula = old_formula.strip()
        if formula == "":
            formula = "=0"

        if not SIMPLE_FORMULA_PATTERN.fullmatch(formula):
            raise ValueError(f"Cell formula is not a simple expense formula: {formula}")

        amount_term = str(amount)

        if formula == "=0":
            return f"=-{amount_term}" if refund else f"={amount_term}"

        operator = "-" if refund else "+"
        return f"{formula}{operator}{amount_term}"
