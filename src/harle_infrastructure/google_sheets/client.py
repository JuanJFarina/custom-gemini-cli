import asyncio
import re
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, TypeAlias
from uuid import UUID

import gspread
from google.oauth2.service_account import Credentials
from gspread.spreadsheet import Spreadsheet
from gspread.utils import ValueInputOption, ValueRenderOption
from pydantic import BaseModel, Field

from harle_domain.tools import ToolExecutionContext, ToolFamily
from harle_utils import ToolAccessDeniedError

from .mappings import (
    FORMULA_AMOUNT_TERM,
    GOOGLE_SHEETS_SCOPES,
    SIMPLE_FORMULA_PATTERN,
)
from .settings import GoogleSheetsConnectionSettings, LegacyGoogleSheetsSettings

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


@dataclass(frozen=True, slots=True)
class FormulaTerm:
    amount_term: str
    signed_amount: Decimal


FormulaTerms: TypeAlias = list[FormulaTerm]


@dataclass(frozen=True, slots=True)
class FormulaRemovalResult:
    formula: FormulaText
    removed: bool
    duplicate_matches: int


class BatchValueRange(BaseModel):
    values: SheetValueRows = Field(default_factory=list)


class BatchValuesResponse(BaseModel):
    value_ranges: list[BatchValueRange] = Field(
        default_factory=list,
        alias="valueRanges",
    )


@dataclass(slots=True)
class GoogleSheetsClient:
    settings: GoogleSheetsConnectionSettings
    execution_user_id: UUID
    authorized_user_id: UUID
    _spreadsheets: MutableMapping[TargetYear, Spreadsheet] = field(
        default_factory=dict,
        init=False,
    )

    @property
    def spreadsheet(self) -> Spreadsheet:
        return self.get_spreadsheet()

    def get_spreadsheet(
        self,
        *,
        target_spreadsheet: TargetYear = "current_year",
    ) -> Spreadsheet:
        self._require_authorized()
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
            self.settings.service_account_info(),
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
            return self.settings.current_year_spreadsheet_id
        return self.settings.next_year_spreadsheet_id

    async def get_formula(
        self,
        *,
        sheet_name: SheetName,
        cell: CellReference,
        target_spreadsheet: TargetYear = "current_year",
    ) -> FormulaText:
        self._require_authorized()
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
        self._require_authorized()
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
        self._require_authorized()
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

    async def get_values_for_ranges(
        self,
        *,
        ranges: list[RangeName],
        render_option: ValueRenderOption,
        target_spreadsheet: TargetYear = "current_year",
    ) -> list[SheetValueRows]:
        self._require_authorized()
        return await asyncio.to_thread(
            self._get_values_for_ranges_sync,
            ranges=ranges,
            render_option=render_option,
            target_spreadsheet=target_spreadsheet,
        )

    def _get_values_for_ranges_sync(
        self,
        *,
        ranges: list[RangeName],
        render_option: ValueRenderOption,
        target_spreadsheet: TargetYear,
    ) -> list[SheetValueRows]:
        response = self.get_spreadsheet(
            target_spreadsheet=target_spreadsheet,
        ).values_batch_get(
            ranges,
            params={"valueRenderOption": render_option},
        )
        validated_response = BatchValuesResponse.model_validate(response)
        return [value_range.values for value_range in validated_response.value_ranges]

    async def update_formula(
        self,
        *,
        sheet_name: SheetName,
        cell: CellReference,
        formula: FormulaText,
        target_spreadsheet: TargetYear = "current_year",
    ) -> None:
        self._require_authorized()
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
        self._require_authorized()
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

    def _require_authorized(self) -> None:
        if self.execution_user_id != self.authorized_user_id:
            raise ToolAccessDeniedError("Google Sheets access is not authorized.")


@dataclass(frozen=True, slots=True)
class GoogleSheetsClientFactory:
    settings: LegacyGoogleSheetsSettings

    def create(self, context: ToolExecutionContext) -> GoogleSheetsClient:
        context.require_family(ToolFamily.LEGACY_GOOGLE_SHEETS_EXPENSES)
        connection = self.settings.connection_for(context.user_id)
        legacy_user_id = self.settings.LEGACY_GOOGLE_SHEETS_USER_ID
        assert legacy_user_id is not None
        return GoogleSheetsClient(
            settings=connection,
            execution_user_id=context.user_id,
            authorized_user_id=legacy_user_id,
        )


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
