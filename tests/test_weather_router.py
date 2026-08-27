from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_user
from app.routers import weather
from app.weather import (
    CityNotFoundError,
    CurrentWeather,
    DailyForecast,
    Forecast,
    WeatherServiceError,
)

app = FastAPI()
app.include_router(weather.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def _current_weather(**overrides):
    defaults = {
        "city": "Ho Chi Minh City",
        "country": "VN",
        "temperature_c": 30.5,
        "feels_like_c": 34.0,
        "description": "scattered clouds",
        "humidity_percent": 70,
        "wind_speed_ms": 3.2,
    }
    defaults.update(overrides)
    return CurrentWeather(**defaults)


def _forecast(**overrides):
    defaults = {
        "city": "Ho Chi Minh City",
        "country": "VN",
        "days": [
            DailyForecast(
                date="2026-08-28",
                min_temperature_c=24.0,
                max_temperature_c=33.0,
                description="clear sky",
            )
        ],
    }
    defaults.update(overrides)
    return Forecast(**defaults)


class TestWeatherCurrentMode:
    def test_returns_camel_case_current_weather(self, mocker):
        mocker.patch(
            "app.routers.weather.get_current_weather", return_value=_current_weather()
        )

        response = client.post(
            "/weather", json={"mode": "current", "city": "Ho Chi Minh City"}
        )

        assert response.status_code == 200
        assert response.json() == {
            "mode": "current",
            "city": "Ho Chi Minh City",
            "country": "VN",
            "temperatureC": 30.5,
            "feelsLikeC": 34.0,
            "description": "scattered clouds",
            "humidityPercent": 70,
            "windSpeedMs": 3.2,
        }

    def test_forwards_the_city_argument(self, mocker):
        mock_get_current = mocker.patch(
            "app.routers.weather.get_current_weather", return_value=_current_weather()
        )

        client.post("/weather", json={"mode": "current", "city": "Hanoi"})

        mock_get_current.assert_called_once_with("Hanoi")


class TestWeatherForecastMode:
    def test_returns_camel_case_forecast(self, mocker):
        mocker.patch("app.routers.weather.get_forecast", return_value=_forecast())

        response = client.post(
            "/weather", json={"mode": "forecast", "city": "Ho Chi Minh City"}
        )

        assert response.status_code == 200
        assert response.json() == {
            "mode": "forecast",
            "city": "Ho Chi Minh City",
            "country": "VN",
            "days": [
                {
                    "date": "2026-08-28",
                    "minTemperatureC": 24.0,
                    "maxTemperatureC": 33.0,
                    "description": "clear sky",
                }
            ],
        }


class TestWeatherErrors:
    def test_city_not_found_returns_404(self, mocker):
        mocker.patch(
            "app.routers.weather.get_current_weather",
            side_effect=CityNotFoundError("City not found: asdkjaskjd"),
        )

        response = client.post(
            "/weather", json={"mode": "current", "city": "asdkjaskjd"}
        )

        assert response.status_code == 404
        assert response.json() == {"detail": "City not found: asdkjaskjd"}

    def test_upstream_failure_returns_502(self, mocker):
        mocker.patch(
            "app.routers.weather.get_forecast",
            side_effect=WeatherServiceError("The weather service timed out."),
        )

        response = client.post(
            "/weather", json={"mode": "forecast", "city": "Ho Chi Minh City"}
        )

        assert response.status_code == 502
        assert response.json() == {"detail": "The weather service timed out."}

    def test_rejects_a_request_missing_city(self):
        response = client.post("/weather", json={"mode": "current", "city": ""})

        assert response.status_code == 422

    def test_rejects_an_invalid_mode(self):
        response = client.post("/weather", json={"mode": "hourly", "city": "Hanoi"})

        assert response.status_code == 422


class TestWeatherAuth:
    def test_requires_bearer_token(self):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            response = client.post(
                "/weather", json={"mode": "current", "city": "Hanoi"}
            )
            assert response.status_code == 401
        finally:
            app.dependency_overrides[get_current_user] = override_current_user
