"""Format parsers for the knowledge platform.

Each parser turns raw bytes of one format into a normalized
:class:`KnowledgeDocument`. Registered by format name ("markdown", "html",
"pdf", "txt", "json", "yaml", "xml") in the :class:`KnowledgeRegistry`.
"""

from knowledge.parsers.html import HtmlParser
from knowledge.parsers.json import JsonParser
from knowledge.parsers.markdown import MarkdownParser
from knowledge.parsers.pdf import PdfParser
from knowledge.parsers.txt import TextParser
from knowledge.parsers.xml import XmlParser
from knowledge.parsers.yaml import YamlParser

__all__ = [
    "HtmlParser",
    "JsonParser",
    "MarkdownParser",
    "PdfParser",
    "TextParser",
    "XmlParser",
    "YamlParser",
]
