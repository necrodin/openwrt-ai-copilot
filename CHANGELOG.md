# Changelog

All notable changes to OpenWrt AI Copilot are documented here.

## [1.0.0] — 2026-08-15

### Added

- **Provider-independent AI backend.** Chat, embeddings, vision, and rerank run
  through a capability-based provider abstraction with support for DeepSeek,
  OpenAI, OpenRouter, Ollama, Anthropic, Gemini, Groq, Together, Mistral, xAI,
  Cohere, Perplexity, Fireworks, Cerebras, Azure OpenAI, NVIDIA NIM, LM Studio,
  vLLM, and any custom OpenAI-compatible endpoint.
- **AI Copilot.** Natural-language chat grounded in live router state, with
  streaming replies, router-context disclosure, model selection, and a
  deterministic diagnosis/recommendation engine.
- **OpenWrt router management.** Live dashboard (CPU, memory, storage, network,
  temperature), SSH-based management (system settings, time/NTP, firmware,
  backups, power actions), package management (apk/opkg inventory, upgrades,
  repository search, feed updates), network, firewall, DHCP, DNS, wireless,
  services, VPN, clients, and system log views.
- **Multi-provider support with encrypted credentials.** Provider API keys are
  encrypted at rest in a server-side vault-backed credential store and are
  never written to `providers.yaml`, returned by the API, or exposed to the
  browser. Providers survive backend restarts.
- **Model discovery.** Discover a provider's model list from its endpoint using
  the typed or saved credential, with manual model entry always available.
- **Authentication.** Admin/read-only browser sessions and API-key access with
  role-scoped permissions.
- **Router fleet support.** Multiple saved routers, each with its own live
  connection, dashboard, and management surfaces.

### Fixed

- System page no longer fails on routers whose device-tree model is NUL
  terminated (OpenWrt 25.x); empty sections render as N/A instead of erroring.
- Package repository feeds are read from the OpenWrt 25 `/etc/apk/repositories.d`
  layout; search auto-refreshes a missing index cache before reporting an
  unavailable repository.
- Provider duplicate creation returns HTTP 409; editing preserves or replaces a
  stored credential server-side; deleting a provider removes its credential.
- About page version is sourced from the authoritative backend version.

### Security

- Provider API keys are encrypted (Fernet) in `provider_credentials.json`,
  never stored in `providers.yaml`, never logged, and never returned by the
  API.
- Router credentials are encrypted at rest in the credential vault.
- Every router write is gated by the `RouterActionGuard` policy
  (`allow` / `require_approval` / `deny`).

### License

- Replaced the previous MIT license with the
  **OpenWrt AI Copilot Personal Non-Commercial License** (personal, non-commercial
  use only).
