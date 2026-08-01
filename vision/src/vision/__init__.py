"""OpenWrt AI Copilot — vision abstraction.

Vision is modeled as multimodal chat: `VisionRequest` carries text + image
content parts and is routed through the same provider-agnostic chat path. This
package re-exports the `Visioner` protocol and will host vision-specific
helpers and adapters.
"""

__version__ = "0.1.0"

from ai.core.models import VisionRequest, VisionResponse
from ai.core.protocols import Visioner

__all__ = ["Visioner", "VisionRequest", "VisionResponse"]
