"""Deterministic fixture LLM used before real-adapter authorization."""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from ai_intel.ports.llm import LLMRequest


@dataclass(slots=True)
class FakeLLM:
    responses: Iterable[str | Exception]
    requests: list[LLMRequest] = field(default_factory=list, init=False)
    _queue: deque[str | Exception] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._queue = deque(self.responses)

    def complete(self, request: LLMRequest) -> str:
        self.requests.append(request)
        if not self._queue:
            raise RuntimeError("FakeLLM has no configured response")
        response = self._queue.popleft()
        if isinstance(response, Exception):
            raise response
        return response
