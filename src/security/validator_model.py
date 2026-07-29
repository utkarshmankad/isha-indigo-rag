"""
Pydantic models for query validation results.

Defines validation result structures for type safety and serialization.
"""

from typing import Literal

from pydantic import BaseModel


class ValidationResult(BaseModel):
    """Result of query validation."""

    is_valid: bool
    category: Literal["safe", "attack_attempt", "pii_reveal", "prohibited_content"]
    reason: str  # Human-readable explanation
    warning: str = ""  # Additional non-fatal warning


class QuerySanitizationResult(BaseModel):
    """Result of query sanitization."""

    original_query: str
    sanitized_query: str
    removed_patterns: list[str]

    @property
    def is_modified(self) -> bool:
        """Check if query was modified."""
        return len(self.removed_patterns) > 0

    @property
    def clean_ratio(self) -> float:
        """Percentage of original query remaining."""
        if not self.original_query:
            return 0.0
        return len(self.sanitized_query) / len(self.original_query)

    class Config:
        """Pydantic configuration for partial serialization."""

        # Allow extra fields if needed
        extra = "ignore"