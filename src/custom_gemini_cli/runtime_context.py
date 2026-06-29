from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


ROSARIO_LATITUDE = -32.9468
ROSARIO_LONGITUDE = -60.6393
ROSARIO_TIMEZONE = timezone(timedelta(hours=-3), name="ART")
WEATHER_TIMEOUT_SECONDS = 5


def get_current_time_and_date() -> str:
    now = datetime.now(ROSARIO_TIMEZONE)
    return now.strftime("%A, %Y-%m-%d %H:%M %Z")


def get_current_weather() -> str:
    query = urlencode(
        {
            "latitude": ROSARIO_LATITUDE,
            "longitude": ROSARIO_LONGITUDE,
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                    "wind_speed_10m",
                ]
            ),
            "timezone": "America/Argentina/Cordoba",
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{query}"

    try:
        with urlopen(url, timeout=WEATHER_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return "Current weather is unavailable."

    current = payload.get("current") or {}
    units = payload.get("current_units") or {}

    temperature = current.get("temperature_2m")
    apparent_temperature = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    precipitation = current.get("precipitation")
    wind_speed = current.get("wind_speed_10m")
    weather_code = current.get("weather_code")

    if temperature is None:
        return "Current weather is unavailable."

    parts = [
        _format_value(
            "temperature",
            temperature,
            units.get("temperature_2m", "C"),
        ),
        _format_value(
            "feels like",
            apparent_temperature,
            units.get("apparent_temperature", "C"),
        ),
        _format_value("humidity", humidity, units.get("relative_humidity_2m", "%")),
        _format_value("precipitation", precipitation, units.get("precipitation", "mm")),
        _format_value("wind", wind_speed, units.get("wind_speed_10m", "km/h")),
    ]

    summary = _weather_code_summary(weather_code)
    values = ", ".join(part for part in parts if part)
    return f"{summary}; {values} in Rosario, Argentina."


def _format_value(label: str, value: object, unit: str) -> str:
    if value is None:
        return ""
    return f"{label} {value}{_format_unit(unit)}"


def _format_unit(unit: str) -> str:
    return unit.replace("\N{DEGREE SIGN}C", "C")


def _weather_code_summary(code: object) -> str:
    descriptions = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        71: "slight snow",
        73: "moderate snow",
        75: "heavy snow",
        80: "slight rain showers",
        81: "moderate rain showers",
        82: "violent rain showers",
        95: "thunderstorm",
        96: "thunderstorm with slight hail",
        99: "thunderstorm with heavy hail",
    }
    return descriptions.get(code, "current conditions")
