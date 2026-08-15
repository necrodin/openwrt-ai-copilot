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

    # API-key authentication for programmatic clients (Security Fix #1). Both
    # keys load from the environment and are never logged or returned by the
    # API. Leave a key empty to disable that role; with both empty the API
    # fails closed and rejects every protected request until a key is
    # configured. Programmatic clients authenticate with
    # ``Authorization: Bearer <AUTH_*_API_KEY>``.
    #   AUTH_ADMIN_API_KEY    — full access (reads + management/write actions).
    #   AUTH_READONLY_API_KEY — read-only access (status/dashboard/chat only).
    auth_admin_api_key: str = ""
    auth_readonly_api_key: str = ""

    # Browser login accounts. On first startup the web UI runs a setup wizard
    # that creates the initial administrator; its bcrypt-hashed password is
    # stored in the application-users table and the plaintext is never kept.
    # These environment fields are retained strictly for the ONE-TIME migration
    # of installations previously configured with environment credentials: on
    # the first boot while the users table is empty, AUTH_ADMIN_USERNAME/
    # AUTH_ADMIN_PASSWORD (and the readonly pair, when set) are hashed and
    # stored once. Afterwards the stored accounts are authoritative and these
    # values are ignored — no AUTH_ADMIN_PASSWORD is required for a fresh
    # installation. Credentials are never logged or returned by the API.
    #   AUTH_ADMIN_USERNAME / AUTH_ADMIN_PASSWORD       — legacy full-access bootstrap.
    #   AUTH_READONLY_USERNAME / AUTH_READONLY_PASSWORD — legacy read-only bootstrap.
    auth_admin_username: str = ""
    auth_admin_password: str = ""
    auth_readonly_username: str = ""
    auth_readonly_password: str = ""

    # Lifetime of a browser session issued by /auth/login, in seconds.
    # Sessions are held in a server-side store so logout can revoke them.
    auth_session_ttl: int = 28_800  # 8 hours

    # Fernet key used to encrypt router credentials (password / private key) at
    # rest. Optional: on first startup a cryptographically random key is
    # generated and persisted owner-only to ``vault.key`` in the application
    # data directory, and later restarts reuse it automatically. Set
    # AUTH_VAULT_KEY to override the generated/derived key explicitly. When
    # unset, SECRET_KEY (only if it differs from the placeholder below) is used
    # as a derivation source; with neither configured the key is generated.
    auth_vault_key: str = ""

    # Internet speed test (read-only measurement of the management host's link,
    # stdlib only — never router commands). Latency/jitter use TCP connect
    # timings to a public host; download/upload use bounded HTTPS transfers to
    # public, credential-free endpoints. Both URLs are fully operator
    # configurable; leave one empty to skip that measurement.
    speed_test_latency_host: str = "1.1.1.1"
    speed_test_latency_port: int = 443
    speed_test_download_url: str = "https://speed.cloudflare.com/__down?bytes=20000000"
    speed_test_upload_url: str = "https://speed.cloudflare.com/__up"
    # Path to a PEM CA bundle used to verify the speed-test endpoints' TLS
    # certificates. Empty = the platform's default trust store (always
    # verified; TLS verification is never disabled).
    speed_test_ca_bundle: str = ""
    # Hard bounds that cap the cost of one test (bytes and/or wall-clock).
    speed_test_max_bytes: int = 20_000_000
    speed_test_upload_bytes: int = 8_000_000
    speed_test_max_duration_seconds: float = 15.0
    speed_test_latency_samples: int = 10
    speed_test_latency_timeout_seconds: float = 3.0
    # Minimum gap between manual tests; prevents repeated/concurrent abuse.
    speed_test_cooldown_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
