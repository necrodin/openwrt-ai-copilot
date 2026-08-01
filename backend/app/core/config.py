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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
