from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from ..config import settings


class AnthropicLLM:
    """Default provider — powers the hosted/web demo (Claude Sonnet). A private
    on-prem deployment swaps to local weights via OllamaLLM (or vLLM behind the
    same interface) to stay fully closed on the city's own hardware."""

    name = "anthropic"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.anthropic_model
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(self, system: str, user: str, max_tokens: int = 1024) -> str:
        msg = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")

    async def generate_stream(
        self, system: str, user: str, max_tokens: int = 1024
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
