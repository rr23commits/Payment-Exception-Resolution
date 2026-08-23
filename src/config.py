"""Local configuration kept separate from domain code."""

import os
from urllib.parse import urlparse


DEFAULT_DATABASE_URL = "postgresql://payment_engine:payment_engine@localhost:5432/payment_engine"


def database_url() -> str:
    """Return a valid local PostgreSQL URL without opening a connection."""
    value = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    parsed = urlparse(value)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname or not parsed.path:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL with host and database name")
    return value
