"""Vision protocol.

Re-exported here so vision-specific code depends on the `vision` package rather
than reaching into `ai.core` directly. The contract itself lives in
`ai.core.protocols` to keep a single source of truth.
"""

from ai.core.models import VisionRequest, VisionResponse
from ai.core.protocols import VisionProvider

__all__ = ["VisionProvider", "VisionRequest", "VisionResponse"]
