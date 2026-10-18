"""Application configuration via environment variables (prefix NOESIS_)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOESIS_", env_file=".env", extra="ignore")

    app_name: str = "NOESIS AI"
    environment: str = "development"
    serverless: bool = False
    artifact_storage: str = "disk"
    api_prefix: str = "/api"

    # Persistence. SQLite by default for zero-dependency local runs;
    # PostgreSQL + pgvector in production via NOESIS_DATABASE_URL.
    database_url: str = "sqlite:///./noesis.db"
    redis_url: str = ""  # empty -> in-process cache/coordination fallback

    # Auth
    jwt_secret: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # Artifacts (scientific outputs: trajectories, plots, reports, FITS)
    artifact_root: str = "../artifacts"

    # Workers / job queue
    workers_enabled: bool = True
    sqlite_busy_timeout_ms: int = 10000
    worker_count: int = 2
    worker_poll_interval_s: float = 0.4
    job_default_timeout_s: int = 600
    job_max_attempts: int = 3
    stale_job_heartbeat_s: int = 60

    # Simulations run in a subprocess with a hard wall-clock deadline
    simulation_subprocess_timeout_s: int = 300

    # Rate limiting (per user per minute) for outbound archive queries
    rate_limit_per_minute: int = 120

    # Context layer: FalkorDB graph (openCypher over the Redis protocol).
    # Empty -> disabled; all graph reads/writes degrade to no-ops.
    graphdb_url: str = ""                 # e.g. "localhost:6379" or "graphdb:6379"
    graphdb_graph: str = "noesis"         # graph key name on the server
    graphdb_password: str = ""            # set if the server runs with --requirepass
    graphdb_timeout_s: float = 2.0        # connect timeout; keeps the API responsive

    # Optional LLM provider (OpenAI-compatible). When unset, agents run in
    # deterministic offline mode with rule-based planners.
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_provider: str = "local"  # local | openai

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
