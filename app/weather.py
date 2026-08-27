"""Weather lookup service for the AI Assistant's get_weather tool.

Calls OpenWeatherMap's Current Weather Data API and 5 Day / 3 Hour Forecast
API. The forecast API returns 40 three-hour data points; _group_by_day
collapses them into at most 5 daily summaries so the response stays small
enough for an LLM to read as tool output.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.config import get_settings

BASE_URL = "https://api.openweathermap.org/data/2.5"
REQUEST_TIMEOUT_SECONDS = 10.0


class WeatherError(Exception):
    """Base class for errors the router maps to an HTTP error response."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class CityNotFoundError(WeatherError):
    pass


class WeatherServiceError(WeatherError):
    """Upstream OpenWeatherMap failure: timeout, 5xx, or a bad/missing API key."""


@dataclass(frozen=True)
class CurrentWeather:
    city: str
    country: str
    temperature_c: float
    feels_like_c: float
    description: str
    humidity_percent: int
    wind_speed_ms: float


@dataclass(frozen=True)
class DailyForecast:
    date: str
    min_temperature_c: float
    max_temperature_c: float
    description: str


@dataclass(frozen=True)
class Forecast:
    city: str
    country: str
    days: list[DailyForecast]


def _get(path: str, city: str) -> dict:
    settings = get_settings()
    try:
        response = httpx.get(
            f"{BASE_URL}/{path}",
            params={
                "q": city,
                "appid": settings.openweather_api_key,
                "units": "metric",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise WeatherServiceError("The weather service timed out.") from exc
    except httpx.HTTPError as exc:
        raise WeatherServiceError("Could not reach the weather service.") from exc

    if response.status_code == 404:
        raise CityNotFoundError(f"City not found: {city}")
    if response.status_code != 200:
        raise WeatherServiceError(
            f"The weather service returned an unexpected error (HTTP {response.status_code})."
        )
    return response.json()


def get_current_weather(city: str) -> CurrentWeather:
    data = _get("weather", city)
    return CurrentWeather(
        city=data["name"],
        country=data["sys"]["country"],
        temperature_c=data["main"]["temp"],
        feels_like_c=data["main"]["feels_like"],
        description=data["weather"][0]["description"],
        humidity_percent=data["main"]["humidity"],
        wind_speed_ms=data["wind"]["speed"],
    )


def _group_by_day(entries: list[dict]) -> list[DailyForecast]:
    days: dict[str, list[dict]] = {}
    for entry in entries:
        date = entry["dt_txt"].split(" ")[0]
        days.setdefault(date, []).append(entry)

    result = []
    for date, day_entries in list(days.items())[:5]:
        temps = [e["main"]["temp"] for e in day_entries]
        midday = min(day_entries, key=lambda e: abs(int(e["dt_txt"][11:13]) - 12))
        result.append(
            DailyForecast(
                date=date,
                min_temperature_c=min(temps),
                max_temperature_c=max(temps),
                description=midday["weather"][0]["description"],
            )
        )
    return result


def get_forecast(city: str) -> Forecast:
    data = _get("forecast", city)
    return Forecast(
        city=data["city"]["name"],
        country=data["city"]["country"],
        days=_group_by_day(data["list"]),
    )
