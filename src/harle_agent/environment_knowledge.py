from asyncio import Lock
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import cast
from urllib.parse import urlencode

import httpx

ROSARIO_LATITUDE = -32.9468
ROSARIO_LONGITUDE = -60.6393
ROSARIO_TIMEZONE = timezone(timedelta(hours=-3), name="ART")
WEATHER_TIMEOUT_SECONDS = 5
WEATHER_CACHE_SECONDS = 600
WEATHER_FAILURE_CACHE_SECONDS = 60
WEATHER_UNAVAILABLE = "Current weather is unavailable."


@dataclass(frozen=True)
class _WeatherCache:
    value: str
    expires_at: float


_WEATHER_CACHE: _WeatherCache | None = None
_WEATHER_CACHE_LOCK = Lock()


def get_current_time_and_date() -> str:
    now = datetime.now(ROSARIO_TIMEZONE)
    return now.strftime("%A, %Y-%m-%d %H:%M %Z")


async def get_current_weather() -> str:
    global _WEATHER_CACHE  # pylint: disable=global-statement

    cached_weather = _cached_weather()
    if cached_weather is not None:
        return cached_weather

    async with _WEATHER_CACHE_LOCK:
        cached_weather = _cached_weather()
        if cached_weather is not None:
            return cached_weather

        weather = await _fetch_current_weather()
        cache_seconds = (
            WEATHER_FAILURE_CACHE_SECONDS
            if weather == WEATHER_UNAVAILABLE
            else WEATHER_CACHE_SECONDS
        )
        _WEATHER_CACHE = _WeatherCache(
            value=weather,
            expires_at=monotonic() + cache_seconds,
        )
        return weather


def _cached_weather() -> str | None:
    if _WEATHER_CACHE is None or _WEATHER_CACHE.expires_at <= monotonic():
        return None
    return _WEATHER_CACHE.value


async def _fetch_current_weather() -> str:  # pylint: disable=too-many-locals
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
                ],
            ),
            "timezone": "America/Argentina/Cordoba",
        },
    )
    url = f"https://api.open-meteo.com/v1/forecast?{query}"

    try:
        async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return WEATHER_UNAVAILABLE

    if not isinstance(payload, dict):
        return WEATHER_UNAVAILABLE

    current = payload.get("current") or {}
    units = payload.get("current_units") or {}

    temperature = current.get("temperature_2m")
    apparent_temperature = current.get("apparent_temperature")
    humidity = current.get("relative_humidity_2m")
    precipitation = current.get("precipitation")
    wind_speed = current.get("wind_speed_10m")
    weather_code = current.get("weather_code")

    if temperature is None:
        return WEATHER_UNAVAILABLE

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

    summary = _weather_code_summary(cast(int, weather_code))
    values = ", ".join(part for part in parts if part)
    return f"{summary}; {values}"


def _format_value(label: str, value: object, unit: str) -> str:
    if value is None:
        return ""
    return f"{label} {value}{_format_unit(unit)}"


def _format_unit(unit: str) -> str:
    return unit.replace("\N{DEGREE SIGN}C", "C")


def _weather_code_summary(code: int) -> str:
    descriptions: dict[int, str] = {
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
