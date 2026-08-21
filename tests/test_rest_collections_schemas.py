from app.schemas import (
    CollectionCreateRequest,
    CollectionOut,
    SavedRequestCreateRequest,
    SavedRequestOut,
    SavedRequestUpdateRequest,
)


def test_saved_request_out_serializes_to_camel_case():
    row = SavedRequestOut(
        id="r1",
        collection_id="c1",
        name="Get profile",
        method="GET",
        url="https://api.example.com/profile",
        query_params=[],
        headers=[],
        body="",
        body_type="raw",
        body_fields=[],
        auth={"type": "none"},
        created_at="2026-08-21T00:00:00+00:00",
        updated_at="2026-08-21T00:00:00+00:00",
    )
    dumped = row.model_dump(by_alias=True, mode="json")
    assert dumped["collectionId"] == "c1"
    assert dumped["bodyType"] == "raw"
    assert dumped["bodyFields"] == []
    assert "collection_id" not in dumped


def test_collection_out_nests_saved_requests():
    collection = CollectionOut(
        id="c1",
        name="My Collection",
        created_at="2026-08-21T00:00:00+00:00",
        requests=[
            SavedRequestOut(
                id="r1",
                collection_id="c1",
                name="Get profile",
                method="GET",
                url="https://api.example.com/profile",
                query_params=[],
                headers=[],
                body="",
                body_type="raw",
                body_fields=[],
                auth={"type": "none"},
                created_at="2026-08-21T00:00:00+00:00",
                updated_at="2026-08-21T00:00:00+00:00",
            )
        ],
    )
    dumped = collection.model_dump(by_alias=True, mode="json")
    assert len(dumped["requests"]) == 1
    assert dumped["requests"][0]["method"] == "GET"


def test_collection_create_request_rejects_unknown_fields():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CollectionCreateRequest(name="ok", extra_field="nope")


def test_saved_request_create_request_rejects_invalid_method():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SavedRequestCreateRequest(name="ok", method="TRACE", url="https://x.com")


def test_saved_request_update_request_allows_partial_payload():
    payload = SavedRequestUpdateRequest(name="Renamed only")
    dumped = payload.model_dump(exclude_unset=True, mode="json")
    assert dumped == {"name": "Renamed only"}
