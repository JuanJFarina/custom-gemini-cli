import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from harle_utils import Settings, ToolAccessDeniedError


@dataclass(frozen=True, slots=True)
class GoogleSheetsConnectionSettings:
    current_year_spreadsheet_id: str
    next_year_spreadsheet_id: str
    service_account_json_base64: str

    def service_account_info(self) -> Mapping[str, object]:
        decoded = base64.b64decode(
            self.service_account_json_base64,
            validate=True,
        ).decode("utf-8")
        value = json.loads(decoded)
        if not isinstance(value, Mapping):
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 must decode to an object.",
            )
        return value


class LegacyGoogleSheetsSettings(Settings):
    LEGACY_GOOGLE_SHEETS_USER_ID: UUID | None = None
    EXPENSES_SPREADSHEET_ID: str | None = None
    EXPENSES_NEXT_YEAR_SPREADSHEET_ID: str | None = None
    GOOGLE_SERVICE_ACCOUNT_JSON_BASE64: str | None = None

    def connection_for(
        self,
        user_id: UUID,
    ) -> GoogleSheetsConnectionSettings:
        if (
            self.LEGACY_GOOGLE_SHEETS_USER_ID is None
            or user_id != self.LEGACY_GOOGLE_SHEETS_USER_ID
        ):
            raise ToolAccessDeniedError("Google Sheets access is not authorized.")

        values = (
            self.EXPENSES_SPREADSHEET_ID,
            self.EXPENSES_NEXT_YEAR_SPREADSHEET_ID,
            self.GOOGLE_SERVICE_ACCOUNT_JSON_BASE64,
        )
        if any(not value for value in values):
            raise ValueError(
                "Juan's legacy Google Sheets integration is not fully configured.",
            )

        current_year_id, next_year_id, credentials = values
        assert current_year_id is not None
        assert next_year_id is not None
        assert credentials is not None
        return GoogleSheetsConnectionSettings(
            current_year_spreadsheet_id=current_year_id,
            next_year_spreadsheet_id=next_year_id,
            service_account_json_base64=credentials,
        )
