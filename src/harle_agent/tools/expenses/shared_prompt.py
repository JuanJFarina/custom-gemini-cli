from harle_agent.models import HarleTool

SHARED_EXPENSES_TOOLS_PROMPT = """(for all expenses-related tools, follow these guidelines)

- If a transaction happened in between 12:00 AM and 04:00 AM (as an example, on the day 12), it should be added to the previous day (on the day 11). Always inform of this decision to the user.
- Valid category strings:
  - "B": For all fees related to rent and building (spreadsheet column name: "alquileres").
  - "C": For all fees related to essential services like electricity, gas, water, healthcare, etc. (spreadsheet column name: "servicios_esenciales").
  - "D": For all fees related to non-essential services like streaming, gym, subscriptions, etc. (spreadsheet column name: "servicios_no_esenciales").
  - "E": For all fees related to consumable items inside the house like groceries, food, cleaning, etc. (spreadsheet column name: "hogar").
  - "F": For all fees related to transportation like taxi, Uber, buses, fuel, parking, etc. (spreadsheet column name: "transporte").
  - "G": For all fees related to out-of-the-house consumables and entertainment like restaurants, bars, cinema, outings, etc. (spreadsheet column name: "salidas").
  - "H": For all fees related to long-term buys like clothes, electronics, games, books, shopping, etc. (spreadsheet column name: "shopping").
  - "I": For anything that doesn't fit into the other categories. (spreadsheet column name: "otros")."""

SHARED_PROMPT_TOOL = HarleTool(
    name="shared_prompt",
    func=lambda: "",
    prompt=SHARED_EXPENSES_TOOLS_PROMPT,
)
