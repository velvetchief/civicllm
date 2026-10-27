from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://civicllm:civicllm-dev@localhost:5433/civicllm"

    # Browser origins allowed to call the API (comma-separated). Dev serves the
    # CivicLLM frontend on :3000 and a city site on :3100; prod sets the
    # deployed origin, e.g. https://your-frontend.example.com.
    cors_origins: str = "http://localhost:3000,http://localhost:3100"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Default provider. The hosted/web demo runs Claude Sonnet ("anthropic") for
    # answer quality without shipping GPUs; a private on-prem deployment sets
    # LLM_PROVIDER=ollama to stay fully closed on the city's own hardware.
    llm_provider: str = "anthropic"  # "anthropic" | "ollama"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    # Ollama defaults to a 4096-token context and SILENTLY truncates longer prompts —
    # with 8 retrieved excerpts that cuts out the evidence. qwen2.5 supports 32k.
    ollama_num_ctx: int = 16384
    ollama_embed_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Retrieval
    retrieve_k_per_arm: int = 24  # candidates per retrieval arm before fusion
    rerank_candidates: int = 20  # fused candidates handed to the LLM reranker
    retrieve_k_final: int = 8  # chunks handed to the LLM for generation
    min_grounding_score: float = 0.015  # RRF floor below which we refuse to answer


settings = Settings()
