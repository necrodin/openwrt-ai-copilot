"""OpenWrt AI Copilot — provider-agnostic AI core.

This package MUST NOT import or depend on any concrete AI provider. It defines
the contracts (protocols), the unified data model, and the capability registry
that concrete adapters (see `providers`) implement.
"""

__version__ = "1.0.0"
