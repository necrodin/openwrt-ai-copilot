"""Application settings loaded from environment variables / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "OpenWrt AI Copilot"
    app_version: str = "0.1.0"
    environment: str = "development"

    api_prefix: str = "/api"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./data/openwrt_ai.db"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Path to the provider configuration file (YAML or TOML). Missing file =
    # no providers configured; the app still boots.
    provider_config_file: str = "providers.yaml"

    # Path to the RAG configuration file. Missing file = RAG chat is disabled;
    # the existing router-state chat path is used unchanged.
    rag_config_file: str = "rag.yaml"

    # SQLite vector store backing RAG retrieval (created on first use).
    rag_vector_store_path: str = "./data/rag_vectors.sqlite3"

    # Router being monitored by the live dashboard. An empty transport/device
    # falls back to a simulated source so the dashboard works out of the box.
    router_device_transport: str = ""  # "", "ssh", "local", or "simulated"
    router_device_host: str = ""
    router_device_port: int = 22
    router_username: str = "root"
    router_ssh_key: str = ""  # path to an SSH private key
    router_password: str = ""  # optional; prefer keys
    router_poll_interval: float = 5.0  # seconds between dashboard polls

    # TODO(Sprint 2+): move to a proper secrets manager; never log this value.
    secret_key: str = "change-me-in-production"

    # Application API-key authentication (Security Fix #1). Both keys load from
    # the environment and are never logged or returned by the API. Leave a key
    # empty to disable that role; with both empty the API fails closed and
    # rejects every protected request until a key is configured.
    #   AUTH_ADMIN_API_KEY    — full access (reads + management/write actions).
    #   AUTH_READONLY_API_KEY — read-only access (status/dashboard/chat only).
    #
    # The keys are operator credentials. The browser never receives them: the
    # frontend exchanges a key (typed or injected server-side) for a short-lived
    # server-side session through POST /auth/login, then sends the session token.
    auth_admin_api_key: str = ""
    auth_readonly_api_key: str = ""

    # Lifetime of a browser session issued by /auth/login, in seconds.
    # Sessions are held in a server-side store so logout can revoke them.
    auth_session_ttl: int = 28_800  # 8 hours


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
