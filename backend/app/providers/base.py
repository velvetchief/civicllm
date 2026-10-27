from collections.abc import AsyncIterator
from typing import Protocol


class LLMProvider(Protocol):
    """Chat-completion provider. Implementations must be swappable so the same
    engine runs against a hosted API (Claude Sonnet — the web demo default) or
    fully closed on local weights (the private on-prem deployment)."""

    name: str

    async def generate(self, system: str, user: str, max_tokens: int = 1024) -> str: ...

    def generate_stream(
        self, system: str, user: str, max_tokens: int = 1024
    ) -> AsyncIterator[str]: ...


class EmbeddingProvider(Protocol):
    name: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...
