"""Notes12 package.

V0: locked data contract + Gemini text extraction.
No Discord bot, frontend, database, image input, or retry yet.
"""

from notes12.extractor import DEFAULT_MODEL, GeminiExtractionError, extract_notes
from notes12.schema import MapType, Notes12Document, Notes12Node, Notes12Relationship

__all__ = [
    "DEFAULT_MODEL",
    "GeminiExtractionError",
    "MapType",
    "Notes12Document",
    "Notes12Node",
    "Notes12Relationship",
    "__version__",
    "extract_notes",
]

__version__ = "0.1.0"
