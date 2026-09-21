from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from .permissions import ToolPermission


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments: Type[BaseModel]
    permission: ToolPermission
    status_text: str
    handler: str

    def provider_schema(self):
        return {"type": "function", "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.arguments.model_json_schema(),
        }}


class ToolRegistry:
    def __init__(self):
        self.definitions: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition):
        if definition.name in self.definitions:
            raise ValueError(f"Duplicate tool: {definition.name}")
        self.definitions[definition.name] = definition

    def schemas(self):
        return [definition.provider_schema() for definition in self.definitions.values()]

    def require(self, name: str):
        definition = self.definitions.get(name)
        if not definition:
            raise ValueError("未知工具")
        return definition
