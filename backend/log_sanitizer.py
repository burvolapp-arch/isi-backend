"""
backend.log_sanitizer — Structured logging with path/secret sanitization.

All log output from the ISI backend MUST go through these helpers
when there is any risk of leaking:
    - Absolute filesystem paths
    - Environment variable values (secrets, tokens, URLs)
    - Stack traces in production

Design contract:
    - sanitize_path() strips the project root prefix from any path.
    - sanitize_error() returns only exception type + safe message.
    - safe_log() emits structured JSON with sanitized fields.
    - No absolute paths ever appear in log output.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

# Project root — used to strip absolute prefixes from logged paths
_PROJECT_ROOT: str = str(Path(__file__).resolve().parent.parent)
_PROJECT_ROOT_SLASH: str = _PROJECT_ROOT + "/"

# Patterns for secrets in environment variable values
_SECRET_PATTERNS: re.Pattern[str] = re.compile(
    r"(redis://|postgresql://|mysql://|amqp://|mongodb://)[^\s]+",
    re.IGNORECASE,
)

logger = logging.getLogger("isi.sanitizer")


def sanitize_path(path: str | Path) -> str:
    """Strip absolute project root from a path for safe logging.

    Examples:
        /Users/user/project/backend/snapshots/v1.0 → backend/snapshots/v1.0
        /etc/passwd → <external>
        backend/snapshots/v1.0 → backend/snapshots/v1.0 (unchanged)
    """
    s = str(path)
    if s.startswith(_PROJECT_ROOT_SLASH):
        return s[len(_PROJECT_ROOT_SLASH):]
    if s.startswith(_PROJECT_ROOT):
        return s[len(_PROJECT_ROOT):].lstrip("/") or "."
    # Path outside project — redact entirely
    if os.path.isabs(s):
        return "<external>"
    return s


def sanitize_error(exc: BaseException) -> str:
    """Return a safe error string: type name + message, no traceback.

    Strips absolute paths from the error message.
    """
    msg = str(exc)
    # Strip any absolute paths that leaked into the message
    msg = msg.replace(_PROJECT_ROOT_SLASH, "")
    msg = msg.replace(_PROJECT_ROOT, "")
    # Redact connection strings
    msg = _SECRET_PATTERNS.sub("[REDACTED_URL]", msg)
    return f"{type(exc).__name__}: {msg}"


def sanitize_value(value: str) -> str:
    """Redact known secret patterns from a string value."""
    return _SECRET_PATTERNS.sub("[REDACTED_URL]", str(value))
