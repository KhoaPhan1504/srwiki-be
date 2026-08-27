from dataclasses import dataclass
from typing import Protocol

from app.schemas import AssistantTurn, ChatMessage, ToolDescriptor


@dataclass(frozen=True)
class ModelDescriptor:
    id: str
    label: str
    provider: str


class Provider(Protocol):
    id: str
    env_attr: str
    models: list[ModelDescriptor]

    def generate_reply(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDescriptor],
        model_id: str,
    ) -> list[AssistantTurn]: ...
