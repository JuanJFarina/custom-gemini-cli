import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, TypeAlias

import gspread
from google.oauth2.service_account import Credentials
from gspread.spreadsheet import Spreadsheet
from gspread.utils import ValueInputOption, ValueRenderOption
from pydantic import BaseModel, Field, PrivateAttr

from harle_agent.settings import AgentSettings, get_agent_settings

from .constants import (
    FORMULA_AMOUNT_TERM,
    GOOGLE_SHEETS_SCOPES,
    SIMPLE_FORMULA_PATTERN,
)

TargetYear = Literal["current_year", "next_year"]
SheetName: TypeAlias = str
CellReference: TypeAlias = str
RangeName: TypeAlias = str
FormulaText: TypeAlias = str
FormulaRows: TypeAlias = list[list[FormulaText]]
SheetValueRows: TypeAlias = list[list[object]]
JsonAmount: TypeAlias = int | float
FORMULA_TERM_PATTERN = re.compile(
    rf"(?P<operator>[+-]?)(?P<amount>{FORMULA_AMOUNT_TERM})",
)


@dataclass(frozen=True)
class FormulaTerm:
    amount_term: str
    signed_amount: Decimal


FormulaTerms: TypeAlias = list[FormulaTerm]


@dataclass(frozen=True)
class FormulaRemovalResult:
    formula: FormulaText
    removed: bool
    duplicate_matches: int


class GoogleSheetsClient(BaseModel):
    settings: AgentSettings = Field(default_factory=get_agent_settings)
    _spreadsheets: dict[TargetYear, Spreadsheet] = PrivateAttr(
        default_factory=dict,
    )

    @property
    def spreadsheet(self) -> Spreadsheet:
        return self.get_spreadsheet()

    def get_spreadsheet(
        self,
        *,
        target_spreadsheet: TargetYear = "current_year",
    ) -> Spreadsheet:
        if target_spreadsheet not in self._spreadsheets:
            self._spreadsheets[target_spreadsheet] = self._open_spreadsheet(
                target_spreadsheet=target_spreadsheet,
            )
        return self._spreadsheets[target_spreadsheet]

    def _open_spreadsheet(
        self,
        *,
        target_spreadsheet: TargetYear,
    ) -> Spreadsheet:
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
        sheet_name: SheetName,
        cell: CellReference,
        target_spreadsheet: TargetYear = "current_year",
    ) -> FormulaText:
        return await asyncio.to_thread(
            self._get_formula_sync,
            sheet_name=sheet_name,
            cell=cell,
            target_spreadsheet=target_spreadsheet,
        )

    def _get_formula_sync(
        self,
        *,
        sheet_name: SheetName,
        cell: CellReference,
        target_spreadsheet: TargetYear,
    ) -> FormulaText:
        worksheet = self.get_spreadsheet(
            target_spreadsheet=target_spreadsheet,
        ).worksheet(sheet_name)
        value = worksheet.acell(
            cell,
            value_render_option=ValueRenderOption.formula,
        ).value
        return str(value or "")

    async def get_formulas(
        self,
        *,
        sheet_name: SheetName,
        range_name: RangeName,
        target_spreadsheet: TargetYear = "current_year",
    ) -> FormulaRows:
        return await asyncio.to_thread(
            self._get_formulas_sync,
            sheet_name=sheet_name,
            range_name=range_name,
            target_spreadsheet=target_spreadsheet,
        )

    def _get_formulas_sync(
        self,
        *,
        sheet_name: SheetName,
        range_name: RangeName,
        target_spreadsheet: TargetYear,
    ) -> FormulaRows:
        worksheet = self.get_spreadsheet(
            target_spreadsheet=target_spreadsheet,
        ).worksheet(sheet_name)
        values = worksheet.get(
            range_name,
            value_render_option=ValueRenderOption.formula,
        )
        return [[str(value or "") for value in row] for row in values]

    async def get_values(
        self,
        *,
        sheet_name: SheetName,
        range_name: RangeName,
        target_spreadsheet: TargetYear = "current_year",
    ) -> SheetValueRows:
        return await asyncio.to_thread(
            self._get_values_sync,
            sheet_name=sheet_name,
            range_name=range_name,
            target_spreadsheet=target_spreadsheet,
        )

    def _get_values_sync(
        self,
        *,
        sheet_name: SheetName,
        range_name: RangeName,
        target_spreadsheet: TargetYear,
    ) -> SheetValueRows:
        worksheet = self.get_spreadsheet(
            target_spreadsheet=target_spreadsheet,
        ).worksheet(sheet_name)
        values = worksheet.get(
            range_name,
            value_render_option=ValueRenderOption.unformatted,
        )
        return [list(row) for row in values]

    async def update_formula(
        self,
        *,
        sheet_name: SheetName,
        cell: CellReference,
        formula: FormulaText,
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
        sheet_name: SheetName,
        cell: CellReference,
        formula: FormulaText,
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
        old_formula: FormulaText,
        amount: int | str,
        refund: bool,
    ) -> FormulaText:
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

    def parse_formula_terms(self, formula: FormulaText) -> FormulaTerms:
        normalized_formula = self._normalize_formula(formula)
        if normalized_formula == "=0":
            return []

        terms: FormulaTerms = []
        expression = normalized_formula.removeprefix("=")
        for match in FORMULA_TERM_PATTERN.finditer(expression):
            operator = match.group("operator") or "+"
            amount_term = match.group("amount")
            amount = _amount_term_value(amount_term)
            if operator == "-":
                amount = -amount
            terms.append(FormulaTerm(amount_term=amount_term, signed_amount=amount))
        return terms

    def formula_total(self, formula: FormulaText) -> JsonAmount:
        terms = self.parse_formula_terms(formula)
        return _json_amount(sum((term.signed_amount for term in terms), Decimal("0")))

    def build_formula_without_amount(
        self,
        *,
        old_formula: FormulaText,
        amount: int,
    ) -> FormulaRemovalResult:
        terms = self.parse_formula_terms(old_formula)
        amount_to_remove = Decimal(amount)
        matching_indexes = [
            index
            for index, term in enumerate(terms)
            if term.signed_amount == amount_to_remove
        ]
        if not matching_indexes:
            return FormulaRemovalResult(
                formula=self._normalize_formula(old_formula),
                removed=False,
                duplicate_matches=0,
            )

        removed_index = matching_indexes[0]
        remaining_terms = [
            term for index, term in enumerate(terms) if index != removed_index
        ]
        return FormulaRemovalResult(
            formula=_build_formula_from_terms(remaining_terms),
            removed=True,
            duplicate_matches=len(matching_indexes),
        )

    def _normalize_formula(self, formula: FormulaText) -> FormulaText:
        normalized_formula = formula.strip() or "=0"
        if not SIMPLE_FORMULA_PATTERN.fullmatch(normalized_formula):
            raise ValueError(
                f"Cell formula is not a simple expense formula: {normalized_formula}",
            )
        return normalized_formula


def _amount_term_value(amount_term: str) -> Decimal:
    if not amount_term.startswith("("):
        return Decimal(amount_term)

    terms = re.fullmatch(
        r"\((?P<amount>\d+(?:\.\d+)?)\s*\*\s*(?P<numerator>\d+)\s*/\s*(?P<denominator>\d+)\)",
        amount_term,
    )
    if terms is None:
        raise ValueError(f"Formula amount term is not supported: {amount_term}")

    numerator = Decimal(terms.group("numerator"))
    denominator = Decimal(terms.group("denominator"))
    return Decimal(terms.group("amount")) * numerator / denominator


def _build_formula_from_terms(terms: FormulaTerms) -> FormulaText:
    if not terms:
        return "=0"

    formula_terms: list[str] = []
    for index, term in enumerate(terms):
        operator = "-" if term.signed_amount < 0 else "+"
        prefix = "-" if index == 0 and operator == "-" else ""
        if index > 0:
            prefix = operator
        formula_terms.append(f"{prefix}{term.amount_term}")
    return "=" + "".join(formula_terms)


def _json_amount(amount: Decimal) -> JsonAmount:
    if amount == amount.to_integral_value():
        return int(amount)
    return float(amount)
