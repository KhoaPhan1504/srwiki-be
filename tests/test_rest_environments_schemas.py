import pytest
from pydantic import ValidationError

from app.schemas import (
    EnvironmentCreateRequest,
    EnvironmentOut,
    EnvironmentUpdateRequest,
    GlobalVariablesOut,
    GlobalVariablesUpdateRequest,
)


def test_environment_out_serializes_to_camel_case():
    env = EnvironmentOut(
        id="e1",
        name="Dev",
        variables=[
            {"id": "v1", "key": "base_url", "value": "https://dev.api", "enabled": True}
        ],
        created_at="2026-08-21T00:00:00+00:00",
        updated_at="2026-08-21T00:00:00+00:00",
    )
    dumped = env.model_dump(by_alias=True, mode="json")
    assert dumped["createdAt"] == "2026-08-21T00:00:00Z"
    assert dumped["variables"][0]["key"] == "base_url"


def test_environment_create_request_defaults_empty_variables():
    req = EnvironmentCreateRequest(name="Dev")
    assert req.variables == []


def test_environment_create_request_rejects_blank_name():
    with pytest.raises(ValidationError):
        EnvironmentCreateRequest(name="")


def test_environment_update_request_allows_partial_payload():
    payload = EnvironmentUpdateRequest(name="Renamed")
    dumped = payload.model_dump(exclude_unset=True, mode="json")
    assert dumped == {"name": "Renamed"}


def test_global_variables_update_request_requires_variables_field():
    with pytest.raises(ValidationError):
        GlobalVariablesUpdateRequest()


def test_global_variables_out_serializes_variables():
    out = GlobalVariablesOut(
        variables=[{"id": "v1", "key": "token", "value": "abc", "enabled": True}]
    )
    dumped = out.model_dump(by_alias=True, mode="json")
    assert dumped["variables"][0]["value"] == "abc"
