import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.schemas import (
    EnvironmentCreateRequest,
    EnvironmentOut,
    EnvironmentUpdateRequest,
    GlobalVariablesOut,
    GlobalVariablesUpdateRequest,
)
from app.supabase_client import user_client

router = APIRouter(prefix="/rest-client", tags=["rest-environments"])


@router.get("/environments", response_model=list[EnvironmentOut])
def list_environments(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    result = (
        client.table("rest_environments")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at")
        .execute()
    )
    return [EnvironmentOut(**row) for row in result.data]


@router.post(
    "/environments", status_code=status.HTTP_201_CREATED, response_model=EnvironmentOut
)
def create_environment(
    payload: EnvironmentCreateRequest, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("rest_environments")
        .insert(
            {
                "user_id": current_user["id"],
                "name": payload.name,
                "variables": payload.variables,
            }
        )
        .execute()
    )
    return EnvironmentOut(**result.data[0])


@router.patch("/environments/{environment_id}", response_model=EnvironmentOut)
def update_environment(
    environment_id: uuid.UUID,
    payload: EnvironmentUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    changes = payload.model_dump(exclude_unset=True, mode="json")
    result = (
        client.table("rest_environments")
        .update(changes)
        .eq("id", str(environment_id))
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Environment not found")
    return EnvironmentOut(**result.data[0])


@router.delete("/environments/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment(
    environment_id: uuid.UUID, current_user: dict = Depends(get_current_user)
):
    client = user_client(current_user["access_token"])
    result = (
        client.table("rest_environments")
        .delete()
        .eq("id", str(environment_id))
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Environment not found")


def _fetch_global_variables(client, user_id: str) -> list[dict]:
    result = (
        client.table("rest_global_variables")
        .select("variables")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if result is None or not result.data:
        return []
    return result.data["variables"]


@router.get("/global-variables", response_model=GlobalVariablesOut)
def get_global_variables(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    variables = _fetch_global_variables(client, current_user["id"])
    return GlobalVariablesOut(variables=variables)


@router.patch("/global-variables", response_model=GlobalVariablesOut)
def update_global_variables(
    payload: GlobalVariablesUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    now = datetime.now(timezone.utc).isoformat()
    client.table("rest_global_variables").upsert(
        {
            "user_id": current_user["id"],
            "variables": payload.variables,
            "updated_at": now,
        },
        on_conflict="user_id",
    ).execute()
    return GlobalVariablesOut(variables=payload.variables)
