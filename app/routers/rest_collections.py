import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.schemas import (
    CollectionCreateRequest,
    CollectionOut,
    CollectionUpdateRequest,
    SavedRequestCreateRequest,
    SavedRequestOut,
    SavedRequestUpdateRequest,
)
from app.supabase_client import user_client

router = APIRouter(prefix="/rest-client", tags=["rest-collections"])


@router.get("/collections", response_model=list[CollectionOut])
def list_collections(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    collections_result = (
        client.table("rest_collections")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at")
        .execute()
    )
    requests_result = (
        client.table("rest_saved_requests")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at")
        .execute()
    )
    requests_by_collection: dict[str, list[dict]] = {}
    for row in requests_result.data:
        requests_by_collection.setdefault(row["collection_id"], []).append(row)

    return [
        CollectionOut(
            **row,
            requests=[
                SavedRequestOut(**r) for r in requests_by_collection.get(row["id"], [])
            ],
        )
        for row in collections_result.data
    ]


@router.post(
    "/collections", status_code=status.HTTP_201_CREATED, response_model=CollectionOut
)
def create_collection(
    payload: CollectionCreateRequest, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("rest_collections")
        .insert({"user_id": current_user["id"], "name": payload.name})
        .execute()
    )
    return CollectionOut(**result.data[0], requests=[])


@router.patch("/collections/{collection_id}", response_model=CollectionOut)
def rename_collection(
    collection_id: uuid.UUID,
    payload: CollectionUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("rest_collections")
        .update({"name": payload.name})
        .eq("id", str(collection_id))
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Collection not found")
    # requests omitted here — the frontend refetches the full collections list
    # on mutation success and doesn't read this response body's `requests`.
    return CollectionOut(**result.data[0], requests=[])


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: uuid.UUID, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("rest_collections")
        .delete()
        .eq("id", str(collection_id))
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Collection not found")


@router.post(
    "/collections/{collection_id}/requests",
    status_code=status.HTTP_201_CREATED,
    response_model=SavedRequestOut,
)
def create_saved_request(
    collection_id: uuid.UUID,
    payload: SavedRequestCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    collection = (
        client.table("rest_collections")
        .select("id")
        .eq("id", str(collection_id))
        .eq("user_id", current_user["id"])
        .maybe_single()
        .execute()
    )
    if not collection or not collection.data:
        raise HTTPException(status_code=404, detail="Collection not found")

    now = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("rest_saved_requests")
        .insert(
            {
                "collection_id": str(collection_id),
                "user_id": current_user["id"],
                "name": payload.name,
                "method": payload.method,
                "url": payload.url,
                "query_params": payload.query_params,
                "headers": payload.headers,
                "body": payload.body,
                "body_type": payload.body_type,
                "body_fields": payload.body_fields,
                "auth": payload.auth,
                "updated_at": now,
            }
        )
        .execute()
    )
    return SavedRequestOut(**result.data[0])


@router.patch("/requests/{request_id}", response_model=SavedRequestOut)
def update_saved_request(
    request_id: uuid.UUID,
    payload: SavedRequestUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    changes = payload.model_dump(exclude_unset=True, mode="json")
    result = (
        client.table("rest_saved_requests")
        .update(changes)
        .eq("id", str(request_id))
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Saved request not found")
    return SavedRequestOut(**result.data[0])


@router.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_request(
    request_id: uuid.UUID, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("rest_saved_requests")
        .delete()
        .eq("id", str(request_id))
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Saved request not found")
