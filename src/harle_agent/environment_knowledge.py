from asyncio import Lock
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from time import monotonic
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict

ROSARIO_LATITUDE = -32.9468
ROSARIO_LONGITUDE = -60.6393
ROSARIO_TIMEZONE = timezone(timedelta(hours=-3), name="ART")
WEATHER_TIMEOUT_SECONDS = 5
WEATHER_CACHE_SECONDS = 600
WEATHER_FAILURE_CACHE_SECONDS = 60
WEATHER_UNAVAILABLE = "Current weather is unavailable."


class _WeatherCache(BaseModel):
    value: str = ""
    expires_at: float = 0.0

    model_config = ConfigDict(validate_assignment=True)

    def is_valid(self) -> bool:
        return self.expires_at > monotonic()

    def write(self, value: str) -> None:
        cache_seconds = (
            WEATHER_FAILURE_CACHE_SECONDS
            if value == WEATHER_UNAVAILABLE
            else WEATHER_CACHE_SECONDS
        )
        self.value = value
        self.expires_at = monotonic() + cache_seconds


_WEATHER_CACHE = _WeatherCache()
_WEATHER_CACHE_LOCK = Lock()


def get_current_time_and_date() -> str:
    now = datetime.now(ROSARIO_TIMEZONE)
    return now.strftime("%A, %Y-%m-%d %H:%M %Z")


async def get_current_weather() -> str:
    if _WEATHER_CACHE.is_valid():
        return _WEATHER_CACHE.value

    async with _WEATHER_CACHE_LOCK:
        if _WEATHER_CACHE.is_valid():
            return _WEATHER_CACHE.value

        weather = await _fetch_current_weather()
        _WEATHER_CACHE.write(weather)
        return weather


async def _fetch_current_weather() -> str:
    url = f"https://api.open-meteo.com/v1/forecast?{_weather_query()}"

    try:
        async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return WEATHER_UNAVAILABLE

    return _weather_from_payload(payload)


def _weather_query() -> str:
    return urlencode(
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


def _weather_from_payload(payload: object) -> str:
    if not isinstance(payload, Mapping):
        return WEATHER_UNAVAILABLE

    current = _mapping_from_value(payload.get("current"))
    units = _mapping_from_value(payload.get("current_units"))

    temperature = current.get("temperature_2m")
    if temperature is None:
        return WEATHER_UNAVAILABLE

    parts = _weather_parts(
        current=current,
        units=units,
    )
    summary = _weather_code_summary(_weather_code(current.get("weather_code")))
    values = ", ".join(part for part in parts if part)
    return f"{summary}; {values}"


def _mapping_from_value(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _weather_parts(
    *,
    current: Mapping[str, object],
    units: Mapping[str, object],
) -> list[str]:
    return [
        _format_value(
            "temperature",
            current.get("temperature_2m"),
            _unit(units, "temperature_2m", "C"),
        ),
        _format_value(
            "feels like",
            current.get("apparent_temperature"),
            _unit(units, "apparent_temperature", "C"),
        ),
        _format_value(
            "humidity",
            current.get("relative_humidity_2m"),
            _unit(units, "relative_humidity_2m", "%"),
        ),
        _format_value(
            "precipitation",
            current.get("precipitation"),
            _unit(units, "precipitation", "mm"),
        ),
        _format_value(
            "wind",
            current.get("wind_speed_10m"),
            _unit(units, "wind_speed_10m", "km/h"),
        ),
    ]


def _unit(units: Mapping[str, object], key: str, default: str) -> str:
    value = units.get(key)
    if isinstance(value, str):
        return value
    return default


def _weather_code(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return -1


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
