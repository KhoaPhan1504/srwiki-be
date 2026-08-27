from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.schemas import CurrentWeatherOut, DailyForecastOut, ForecastOut, WeatherRequest
from app.weather import (
    CityNotFoundError,
    WeatherError,
    WeatherServiceError,
    get_current_weather,
    get_forecast,
)

router = APIRouter(prefix="/weather", tags=["weather"])

_ERROR_STATUS_CODES: dict[type[WeatherError], int] = {
    CityNotFoundError: status.HTTP_404_NOT_FOUND,
    WeatherServiceError: status.HTTP_502_BAD_GATEWAY,
}


@router.post("", response_model=CurrentWeatherOut | ForecastOut)
def get_weather(
    payload: WeatherRequest, current_user: dict = Depends(get_current_user)
):
    try:
        if payload.mode == "current":
            result = get_current_weather(payload.city)
            return CurrentWeatherOut(
                city=result.city,
                country=result.country,
                temperature_c=result.temperature_c,
                feels_like_c=result.feels_like_c,
                description=result.description,
                humidity_percent=result.humidity_percent,
                wind_speed_ms=result.wind_speed_ms,
            )
        result = get_forecast(payload.city)
        return ForecastOut(
            city=result.city,
            country=result.country,
            days=[
                DailyForecastOut(
                    date=d.date,
                    min_temperature_c=d.min_temperature_c,
                    max_temperature_c=d.max_temperature_c,
                    description=d.description,
                )
                for d in result.days
            ],
        )
    except WeatherError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS_CODES.get(type(exc), status.HTTP_502_BAD_GATEWAY),
            detail=exc.message,
        ) from exc
