from ..config import settings
from .anthropic_llm import AnthropicLLM
from .base import EmbeddingProvider, LLMProvider
from .ollama import OllamaEmbeddings, OllamaLLM


def get_llm(provider: str | None = None) -> LLMProvider:
    match provider or settings.llm_provider:
        case "ollama":
            return OllamaLLM()
        case "anthropic":
            return AnthropicLLM()
        case unknown:
            raise ValueError(f"Unknown LLM provider: {unknown}")


def get_embedder() -> EmbeddingProvider:
    # Embeddings always run locally — they touch the full corpus and must stay private.
    return OllamaEmbeddings()
