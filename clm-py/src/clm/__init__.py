"""tunc-clm — parser and v3.0 trim-aware validator for the Claude Memory Format.

Mirrors the API of the Rust reference implementation (`clm-rs`):

  >>> from clm import Document, validate_v3
  >>> doc = Document.parse(open("MANIFESTO.clm").read())
  >>> report = validate_v3(doc)
  >>> assert report.is_valid()

Canonical spec lives at:
  https://raw.githubusercontent.com/TUNC-AI/tunc-clm/main/SPEC.clm

The format itself documents itself in CLM. Read MANIFESTO.clm to bootstrap.
"""

from clm.document import (
    Document,
    Section,
    ParseError,
    MutationError,
)
from clm.validate import (
    ArchiveMode,
    DEFAULT_DECISIONS_LIVE_KEEP,
    DEFAULT_DREAM_LOG_KEEP,
    DEFAULT_ROLL_CALL_KEEP,
    HeaderDeclarations,
    TrimConfig,
    TrimMode,
    ValidationError,
    ValidationReport,
    ValidationWarning,
    validate_v3,
    validate_v3_with_filesystem,
)

__all__ = [
    "Document",
    "Section",
    "ParseError",
    "MutationError",
    "ArchiveMode",
    "HeaderDeclarations",
    "TrimConfig",
    "TrimMode",
    "ValidationError",
    "ValidationReport",
    "ValidationWarning",
    "validate_v3",
    "validate_v3_with_filesystem",
    "DEFAULT_ROLL_CALL_KEEP",
    "DEFAULT_DREAM_LOG_KEEP",
    "DEFAULT_DECISIONS_LIVE_KEEP",
]

__version__ = "0.2.0"
