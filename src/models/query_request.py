"""
Query request model with strict validation and sanitization.
"""

import re

from pydantic import BaseModel, field_validator


class QueryRequest(BaseModel):
    """Request model for RAG queries."""

    query: str
    session_id: str

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query text."""
        v = v.strip()
        if not v:
            raise ValueError("Query cannot be empty")
        if len(v) > 4000:
            raise ValueError("Query exceeds 4000 character limit")
        # Strip HTML tags to prevent XSS in stored responses
        v = re.sub(r"<[^>]+>", "", v)
        return v

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        """Validate session_id format."""
        v = v.strip()
        if not v or len(v) > 128:
            raise ValueError("Invalid session_id")
        # Only allow alphanumeric, hyphens, underscores
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("session_id contains invalid characters")
        return v