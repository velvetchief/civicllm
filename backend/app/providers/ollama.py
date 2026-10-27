import json
from collections.abc import AsyncIterator

import httpx

from ..config import settings


class OllamaLLM:
    name = "ollama"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.ollama_model

    def _payload(self, system: str, user: str, max_tokens: int, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": stream,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.1,
                "num_ctx": settings.ollama_num_ctx,
            },
        }

    async def generate(self, system: str, user: str, max_tokens: int = 1024) -> str:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=self._payload(system, user, max_tokens, stream=False),
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def generate_stream(
        self, system: str, user: str, max_tokens: int = 1024
    ) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/chat",
                json=self._payload(system, user, max_tokens, stream=True),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():  # NDJSON, one object per line
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if fragment := (data.get("message") or {}).get("content"):
                        yield fragment
                    if data.get("done"):
                        break


class OllamaEmbeddings:
    """nomic-embed-text is trained with task prefixes; omitting them measurably
    degrades retrieval quality. Queries and documents get different prefixes."""

    name = "ollama-embed"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.ollama_embed_model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed([f"search_document: {t}" for t in texts])

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([f"search_query: {text}"]))[0]

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/embed",
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]
