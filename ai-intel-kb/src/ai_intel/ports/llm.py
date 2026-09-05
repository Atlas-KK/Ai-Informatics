"""LLM boundary: structured text only, with no tool or storage capability."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol


class LLMOperation(StrEnum):
    PROCESS_INTELLIGENCE = "PROCESS_INTELLIGENCE"
    GENERATE_TOPIC_IDEA = "GENERATE_TOPIC_IDEA"


@dataclass(frozen=True, slots=True)
class LLMRequest:
    operation: LLMOperation
    system_instruction: str
    schema: Mapping[str, Any]
    untrusted_content: str
    context: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema", MappingProxyType(dict(self.schema)))
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


class StructuredLLM(Protocol):
    def complete(self, request: LLMRequest) -> str: ...
