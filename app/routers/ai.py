from fastapi import APIRouter, Depends, HTTPException

from app.ai_orchestrator import generate_reply
from app.ai_providers.registry import available_models
from app.dependencies import get_current_user
from app.schemas import AiChatRequest, AiChatResponse, ModelOut, ModelsResponse

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/models", response_model=ModelsResponse)
def list_models(current_user: dict = Depends(get_current_user)) -> ModelsResponse:
    models = available_models()
    return ModelsResponse(
        models=[ModelOut(id=m.id, label=m.label, provider=m.provider) for m in models]
    )


@router.post("/chat", response_model=AiChatResponse)
def chat(
    payload: AiChatRequest,
    current_user: dict = Depends(get_current_user),
) -> AiChatResponse:
    try:
        turns = generate_reply(payload.messages, payload.tools, payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AiChatResponse(turns=turns)
