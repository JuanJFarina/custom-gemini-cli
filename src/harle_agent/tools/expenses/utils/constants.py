import re

CATEGORY_COLUMNS = ("B", "C", "D", "E", "F", "G", "H", "I")

MONTH_SHEET_MAPPING = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

FORMULA_AMOUNT_TERM = r"(?:\d+(?:\.\d+)?|\(\d+(?:\.\d+)? \* \d+ / \d+\))"
SIMPLE_FORMULA_PATTERN = re.compile(
    rf"^=-?{FORMULA_AMOUNT_TERM}(?:[+-]{FORMULA_AMOUNT_TERM})*$",
)

GOOGLE_SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
