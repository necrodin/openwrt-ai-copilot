"""Error hierarchy for provider-agnostic AI operations.

Adapters raise these errors so callers can handle failures uniformly
regardless of which provider produced them.
"""


class ProviderError(Exception):
    """Base class for all AI provider errors."""


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached."""


class AuthenticationError(ProviderError):
    """The provider rejected the credentials."""


class RateLimitError(ProviderError):
    """The provider returned a rate-limit response."""


class ContextLengthExceededError(ProviderError):
    """The request exceeded the model's context window."""


class UnsupportedCapabilityError(ProviderError):
    """The provider does not implement the requested capability."""
