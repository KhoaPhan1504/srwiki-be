import httpx
import pytest

from app.weather import (
    CityNotFoundError,
    WeatherServiceError,
    get_current_weather,
    get_forecast,
)


def _current_weather_response(**overrides):
    body = {
        "name": "Ho Chi Minh City",
        "sys": {"country": "VN"},
        "main": {"temp": 30.5, "feels_like": 34.0, "humidity": 70},
        "weather": [{"description": "scattered clouds"}],
        "wind": {"speed": 3.2},
    }
    body.update(overrides)
    return httpx.Response(200, json=body)


def _forecast_response(list_entries):
    return httpx.Response(
        200,
        json={
            "city": {"name": "Ho Chi Minh City", "country": "VN"},
            "list": list_entries,
        },
    )


def _forecast_entry(dt_txt, temp):
    return {
        "dt_txt": dt_txt,
        "main": {"temp": temp},
        "weather": [{"description": f"desc at {dt_txt[11:16]}"}],
    }


class TestGetCurrentWeather:
    def test_returns_mapped_fields_on_success(self, mocker):
        mocker.patch("app.weather.httpx.get", return_value=_current_weather_response())

        result = get_current_weather("Ho Chi Minh City")

        assert result.city == "Ho Chi Minh City"
        assert result.country == "VN"
        assert result.temperature_c == 30.5
        assert result.feels_like_c == 34.0
        assert result.description == "scattered clouds"
        assert result.humidity_percent == 70
        assert result.wind_speed_ms == 3.2

    def test_raises_city_not_found_on_a_404(self, mocker):
        mocker.patch(
            "app.weather.httpx.get",
            return_value=httpx.Response(
                404, json={"cod": "404", "message": "city not found"}
            ),
        )

        with pytest.raises(CityNotFoundError):
            get_current_weather("asdkjaskjd")

    def test_raises_weather_service_error_on_a_timeout(self, mocker):
        mocker.patch(
            "app.weather.httpx.get",
            side_effect=httpx.TimeoutException("timed out"),
        )

        with pytest.raises(WeatherServiceError):
            get_current_weather("Ho Chi Minh City")

    def test_raises_weather_service_error_on_an_unexpected_status(self, mocker):
        mocker.patch(
            "app.weather.httpx.get",
            return_value=httpx.Response(401, json={"message": "Invalid API key"}),
        )

        with pytest.raises(WeatherServiceError):
            get_current_weather("Ho Chi Minh City")

    def test_raises_weather_service_error_on_a_connection_failure(self, mocker):
        mocker.patch(
            "app.weather.httpx.get",
            side_effect=httpx.ConnectError("connection refused"),
        )

        with pytest.raises(WeatherServiceError):
            get_current_weather("Ho Chi Minh City")


class TestGetForecast:
    def test_groups_entries_into_at_most_5_days_by_date(self, mocker):
        entries = [
            _forecast_entry("2026-08-28 00:00:00", 24.0),
            _forecast_entry("2026-08-28 12:00:00", 33.0),
            _forecast_entry("2026-08-29 00:00:00", 23.0),
            _forecast_entry("2026-08-29 12:00:00", 31.0),
        ]
        mocker.patch("app.weather.httpx.get", return_value=_forecast_response(entries))

        result = get_forecast("Ho Chi Minh City")

        assert result.city == "Ho Chi Minh City"
        assert result.country == "VN"
        assert [d.date for d in result.days] == ["2026-08-28", "2026-08-29"]

    def test_computes_min_and_max_temperature_across_the_whole_day(self, mocker):
        entries = [
            _forecast_entry("2026-08-28 00:00:00", 24.0),
            _forecast_entry("2026-08-28 12:00:00", 33.0),
            _forecast_entry("2026-08-28 21:00:00", 26.0),
        ]
        mocker.patch("app.weather.httpx.get", return_value=_forecast_response(entries))

        result = get_forecast("Ho Chi Minh City")

        assert result.days[0].min_temperature_c == 24.0
        assert result.days[0].max_temperature_c == 33.0

    def test_uses_the_entry_closest_to_noon_for_the_days_description(self, mocker):
        entries = [
            _forecast_entry("2026-08-28 00:00:00", 24.0),
            _forecast_entry("2026-08-28 12:00:00", 33.0),
            _forecast_entry("2026-08-28 21:00:00", 26.0),
        ]
        mocker.patch("app.weather.httpx.get", return_value=_forecast_response(entries))

        result = get_forecast("Ho Chi Minh City")

        assert result.days[0].description == "desc at 12:00"

    def test_caps_at_5_days_even_with_more_distinct_dates(self, mocker):
        entries = [
            _forecast_entry(f"2026-08-{28 + i:02d} 12:00:00", 25.0) for i in range(7)
        ]
        mocker.patch("app.weather.httpx.get", return_value=_forecast_response(entries))

        result = get_forecast("Ho Chi Minh City")

        assert len(result.days) == 5

    def test_raises_city_not_found_on_a_404(self, mocker):
        mocker.patch(
            "app.weather.httpx.get",
            return_value=httpx.Response(
                404, json={"cod": "404", "message": "city not found"}
            ),
        )

        with pytest.raises(CityNotFoundError):
            get_forecast("asdkjaskjd")
