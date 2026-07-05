import re

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

SIMPLE_FORMULA_PATTERN = re.compile(r"^=-?\d+(?:[+-]\d+)*$")


ADD_NON_CREDIT_TRANSACTION_PROMPT = """
## "add_non_credit_transaction" tool

- Tool for adding a non-credit (one-time pay/refund) transaction to the expenses spreadsheet.
- Args:
  - "amount": Positive integer that represents the amount of the transaction in Argentine pesos.
  - "category": String of one of the valid categories.
  - "month": Integer of the month of the transaction, from 1 to 12. Will default to current month if not provided.
  - "day": Integer of the day of the transaction, from 1 to 31. Will default to current day if not provided.
  - "is_refund": Boolean of whether the transaction is a refund or negative adjustment. Will default to false (not a refund) if not provided.
- Valid category strings:
  - "B": For all fees related to rent and building (spreadsheet column name: "alquileres").
  - "C": For all fees related to essential services like electricity, gas, water, healthcare, etc. (spreadsheet column name: "servicios_esenciales").
  - "D": For all fees related to non-essential services like streaming, gym, subscriptions, etc. (spreadsheet column name: "servicios_no_esenciales").
  - "E": For all fees related to consumable items inside the house like groceries, food, cleaning, etc. (spreadsheet column name: "hogar").
  - "F": For all fees related to transportation like taxi, Uber, buses, fuel, parking, etc. (spreadsheet column name: "transporte").
  - "G": For all fees related to out-of-the-house consumables and entertainment like restaurants, bars, cinema, outings, etc. (spreadsheet column name: "salidas").
  - "H": For all fees related to long-term buys like clothes, electronics, games, books, shopping, etc. (spreadsheet column name: "shopping").
  - "I": For anything that doesn't fit into the other categories. (spreadsheet column name: "otros").
- Example for all args for paying rent on July 5th:
{
  "amount": 500000,
  "category": "B",
  "month": 7,
  "day": 5,
  "is_refund": false
}
"""
