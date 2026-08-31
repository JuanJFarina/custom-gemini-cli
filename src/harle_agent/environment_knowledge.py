from asyncio import Lock
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from time import monotonic
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, ConfigDict

WEATHER_TIMEOUT_SECONDS = 5
WEATHER_CACHE_SECONDS = 600
WEATHER_FAILURE_CACHE_SECONDS = 60
WEATHER_CACHE_MAX_ENTRIES = 128
WEATHER_UNAVAILABLE = "Current weather is unavailable."


@dataclass(frozen=True)
class _WeatherRequest:
    latitude: float
    longitude: float
    timezone_name: str


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


_WEATHER_CACHE: MutableMapping[_WeatherRequest, _WeatherCache] = {}
_WEATHER_CACHE_LOCK = Lock()


def get_current_time_and_date(timezone_name: str) -> str:
    now = datetime.now(ZoneInfo(timezone_name))
    return now.strftime("%A, %Y-%m-%d %I:%M %p %Z")


async def get_current_weather(
    *,
    latitude: float | None,
    longitude: float | None,
    timezone_name: str,
) -> str:
    request = _weather_request(
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
    )
    if request is None:
        return WEATHER_UNAVAILABLE

    cached_weather = _read_cached_weather(request)
    if cached_weather is not None:
        return cached_weather

    async with _WEATHER_CACHE_LOCK:
        cached_weather = _read_cached_weather(request)
        if cached_weather is not None:
            return cached_weather

        weather = await _fetch_current_weather(request)
        _write_cached_weather(request, weather)
        return weather


async def _fetch_current_weather(request: _WeatherRequest) -> str:
    url = f"https://api.open-meteo.com/v1/forecast?{_weather_query(request)}"

    try:
        async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return WEATHER_UNAVAILABLE

    return _weather_from_payload(payload)


def _weather_request(
    *,
    latitude: float | None,
    longitude: float | None,
    timezone_name: str,
) -> _WeatherRequest | None:
    if latitude is None or longitude is None:
        return None
    if (
        not isfinite(latitude)
        or not isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None
    return _WeatherRequest(
        latitude=latitude,
        longitude=longitude,
        timezone_name=timezone_name,
    )


def _read_cached_weather(request: _WeatherRequest) -> str | None:
    cache_entry = _WEATHER_CACHE.get(request)
    if cache_entry is None or not cache_entry.is_valid():
        return None
    return cache_entry.value


def _write_cached_weather(request: _WeatherRequest, weather: str) -> None:
    expired_requests = [
        cached_request
        for cached_request, cache_entry in _WEATHER_CACHE.items()
        if not cache_entry.is_valid()
    ]
    for expired_request in expired_requests:
        _WEATHER_CACHE.pop(expired_request, None)

    if (
        request not in _WEATHER_CACHE
        and len(_WEATHER_CACHE) >= WEATHER_CACHE_MAX_ENTRIES
    ):
        oldest_request = min(
            _WEATHER_CACHE,
            key=lambda cached_request: _WEATHER_CACHE[cached_request].expires_at,
        )
        _WEATHER_CACHE.pop(oldest_request)

    cache_entry = _WeatherCache()
    cache_entry.write(weather)
    _WEATHER_CACHE[request] = cache_entry


def _weather_query(request: _WeatherRequest) -> str:
    return urlencode(
        {
            "latitude": request.latitude,
            "longitude": request.longitude,
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
            "timezone": request.timezone_name,
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
    descriptions: Mapping[int, str] = {
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
