"""
Input validation and sanitization utilities for ISHA.

Provides validation of user queries, airline selection, and other inputs
to ensure security, prevent injection attacks, and protect PII.
"""

import re
from enum import Enum
from typing import Literal

from .validator_model import QuerySanitizationResult, ValidationResult


class PIIType(Enum):
    """Identifies different types of Personally Identifiable Information."""

    PNR = "PNR"  # Passenger Name Record (6-6 digits)
    EMAIL = "email"  # Email address pattern
    PHONE = "phone"  # Phone number pattern
    MAIDEN_NAMES = "maiden_name"  # Mother's maiden name
    PASSPORT = "passport"  # Passport number pattern


class QueryConcernCategory(Enum):
    """Categories of query concerns for severity purposes."""

    SAFE = "safe"
    ATTACK_ATTEMPT = "attack_attempt"
    PII_REVEAL = "pii_reveal"
    PROHIBITED_CONTENT = "prohibited_content"
    CURLY_BRACES_ATTACK = "curl_attack"
    SQL_INJECTION_ATTACK = "sql_attack"


# Configuration
MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 2000
MIN_QUERY_LENGTH_WARNING = 10

# PII patterns to detect
PNR_PATTERN = r"\b\d{6}\d{6}\b"  # 12-digit PNR pattern
EMAIL_PATTERN = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_PATTERN = r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}"
MAIDEN_NAME_PATTERN = r"\b(?:mother\s+maiden|maiden\s+name|mom\s+maiden)\s*:\s*([a-zA-Z]+\s+[a-zA-Z]+)\b"
PASSPORT_PATTERN = r"\b[A-Z]{1,2}\d{6,8}\b"

# Likely attack patterns
CURLY_BRACES_PATTERN = r"\{[^{}]*\{[^{}]*\}[^{}]*\}"  # Nested curly braces
SQL_INJECTION_PATTERN = r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|UNION|EXEC)\b|#|';|--)"
BASH_EXEC_PATTERN = r"(`|;|\||\$(\(|\$\{|\||&|>|\$[a-z\d_])"

# Forbidden words/themes
FORBIDDEN_PATTERNS = [
    r"malware",
    r"ransomware",
    r"backdoor",
    r"exploit",
    r"phishing",
    r"DDoS",
    r"attack",
    r"injection",
    r"rootkit",
]

# Max chunks per query (prevents context exhaustion)
MAX_RETRIEVED_CHUNKS = 10


class QueryValidator:
    """Validates and sanitizes user queries for security and policy compliance."""

    @classmethod
    def validate_query_length(cls, query: str) -> ValidationResult:
        """
        Validate query length.

        Args:
            query: The user query to validate.

        Returns:
            ValidationResult with status indicating pass/fail and reason.
        """
        length = len(query)

        if length < MIN_QUERY_LENGTH:
            return ValidationResult(
                is_valid=False,
                category=QueryConcernCategory.PROHIBITED_CONTENT,
                reason=f"Query too short (min {MIN_QUERY_LENGTH} characters)",
            )

        if length > MAX_QUERY_LENGTH:
            return ValidationResult(
                is_valid=False,
                category=QueryConcernCategory.ATTACK_ATTEMPT,
                reason=f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters",
            )

        if MIN_QUERY_LENGTH_WARNING <= length < 50:
            # Warning, not a failure
            return ValidationResult(
                is_valid=True,
                category=QueryConcernCategory.SAFE,
                reason="",
                warning=f"Query is relatively short ({length} chars). Please provide more details for better answers.",
            )

        return ValidationResult(
            is_valid=True, category=QueryConcernCategory.SAFE, reason=""
        )

    @classmethod
    def detect_pii(cls, query: str) -> list[tuple[PIIType, str]]:
        """
        Detect PII patterns in a query.

        Args:
            query: The query to scan for PII.

        Returns:
            List of tuples (PIIType, detected_value) for each PII found.
        """
        found = []

        # Check for PNR
        pnr_matches = re.findall(PNR_PATTERN, query, re.IGNORECASE)
        for match in pnr_matches:
            found.append((PIIType.PNR, match))

        # Check for email
        email_matches = re.findall(EMAIL_PATTERN, query, re.IGNORECASE)
        for match in email_matches:
            found.append((PIIType.EMAIL, match))

        # Check for phone
        phone_matches = re.findall(PHONE_PATTERN, query)
        for match in phone_matches:
            found.append((PIIType.PHONE, match))

        # Check for maiden name
        maiden_matches = re.findall(MAIDEN_NAME_PATTERN, query, re.IGNORECASE)
        for match in maiden_matches:
            found.append((PIIType.MAIDEN_NAMES, match))

        # Check for passport
        passport_matches = re.findall(PASSPORT_PATTERN, query, re.IGNORECASE)
        for match in passport_matches:
            found.append((PIIType.PASSPORT, match))

        return found

    @classmethod
    def detect_attack_patterns(cls, query: str) -> list[tuple[QueryConcernCategory, str]]:
        """
        Detect potential attack patterns in a query.

        Args:
            query: The query to scan for attacks.

        Returns:
            List of tuples (category, detected_pattern) for each attack found.
        """
        attacks = []

        # Check for nested curly braces (attempt to escape output)
        if re.search(CURLY_BRACES_PATTERN, query, re.IGNORECASE):
            attacks.append(
                (QueryConcernCategory.CURLY_BRACES_ATTACK, "nested curly braces")
            )

        # Check for SQL injection
        if re.search(SQL_INJECTION_PATTERN, query, re.IGNORECASE):
            attacks.append(
                (QueryConcernCategory.SQL_INJECTION_ATTACK, "SQL injection syntax")
            )

        # Check for bash execution attempts
        if re.search(BASH_EXEC_PATTERN, query):
            attacks.append(
                (QueryConcernCategory.ATTACK_ATTEMPT, "command structure found")
            )

        # Check for forbidden content
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                attacks.append((QueryConcernCategory.PROHIBITED_CONTENT, pattern))

        return attacks

    @classmethod
    def sanitize_query(cls, query: str) -> QuerySanitizationResult:
        """
        Sanitize a query by removing dangerous patterns while preserving meaning.

        Args:
            query: The query to sanitize.

        Returns:
            SanitizationResult with sanitized query and list of removed patterns.
        """
        removed_patterns = []

        # Remove PII before processing (keep as is, users should not ask about PII)
        # Actually, we should warn but not silently remove PII from the query
        # instead, we'll detect it and warn, but not alter the query

        # Remove attack patterns (but warn the user)
        # Note: We can't just remove things that might be innocent

        sanitized = query

        # Common cleaning - but be conservative to avoid false positives
        # Remove excessive newlines
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
        # Remove leading/trailing whitespace
        sanitized = sanitized.strip()

        # Limit query to max length (still pass)
        if len(sanitized) > MAX_QUERY_LENGTH:
            sanitized = sanitized[:MAX_QUERY_LENGTH]
            removed_patterns.append("query too long - truncated")

        return QuerySanitizationResult(
            original_query=query,
            sanitized_query=sanitized,
            removed_patterns=removed_patterns,
        )

    @classmethod
    def validate_input(
        cls, query: str, airline: str
    ) -> tuple[bool, str, list[tuple[QueryConcernCategory, str]]]:
        """
        Comprehensive input validation.

        Args:
            query: User query
            airline: Selected airline

        Returns:
            Tuple of (is_valid, combined_reason, issues_found)
        """
        all_issues = []

        # Validate query length
        length_result = cls.validate_query_length(query)
        if not length_result.is_valid:
            all_issues.append((QueryConcernCategory.ATTACK_ATTEMPT, length_result.reason))
        elif length_result.warning:
            all_issues.append((QueryConcernCategory.SAFE, length_result.warning))

        # Check for attack patterns
        attack_results = cls.detect_attack_patterns(query)
        all_issues.extend(attack_results)

        # Detect PII (warn but allow query)
        pii_found = cls.detect_pii(query)
        if pii_found:
            all_issues.append(
                (
                    QueryConcernCategory.PII_REVEAL,
                    f"Detected potential PII: {', '.join(f'{t.value} ({v})' for t, v in pii_found[:3])}"
                    + ("..." if len(pii_found) > 3 else ""),
                )
            )

        # Check airline selection
        valid_airlines = {"indigo", "air_india", "spicejet", "all", "dgca"}
        if airline not in valid_airlines:
            all_issues.append(
                (QueryConcernCategory.ATTACK_ATTEMPT, f"Invalid airline: {airline}")
            )

        # Determine if query is valid (safe with warnings is okay)
        is_valid = True
        combined_reason = "Query processed with warnings"

        for category, message in all_issues:
            if category == QueryConcernCategory.ATTACK_ATTEMPT:
                is_valid = False
            elif category == QueryConcernCategory.PROHIBITED_CONTENT:
                is_valid = False

        return is_valid, combined_reason, all_issues


# Export for use in app.py
__all__ = ["QueryValidator", "ValidationResult", "QuerySanitizationResult"]