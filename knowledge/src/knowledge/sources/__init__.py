"""Knowledge sources."""

from knowledge.sources.filesystem import FileSystemSource, StaticSource
from knowledge.sources.openwrt import OPENWRT_TOPICS, OpenWrtKnowledgeSource

__all__ = [
    "FileSystemSource",
    "OPENWRT_TOPICS",
    "OpenWrtKnowledgeSource",
    "StaticSource",
]
