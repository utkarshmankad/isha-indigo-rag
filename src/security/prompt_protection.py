"""
Prompt injection defense utilities.

Provides mechanisms to protect LLM prompts from injection attacks,
ensuring system instructions remain intact and user cannot manipulate responses.
"""

import re
from typing import Literal

from pydantic import BaseConfig, BaseModel

# System prompt constants
SYSTEM_TEMPLATE = """You are a virtual customer support agent specialising in {airline_name} airline policies.

CRITICAL INSTRUCTIONS:
1. You MUST use ONLY the context passages provided below for your answer.
2. You MUST NOT use outside knowledge.
3. You MUST cite documents by name when using their content.
4. You MUST state all amounts in INR (₹) for Indian routes.
5. If multiple airlines' policies are in the context, clearly attribute each point to the relevant airline.
6. If the answer cannot be found in the provided context, say: "I could not find this in the policy documents. Please contact {contact_info}."

USER QUESTION: {user_question}"""

# Forbidden words that indicate prompt injection attempts
FORBIDDEN_LEADERS = [
    "ignore previous instructions",
    "forget what I said",
    "completely remove",
    "override previous",
    "do not include",
    "do not cite",
    "do not use",
    "attack",
    "bypass",
    "escape",
    "break character",
    "roleplay",
    "treat as",
    "pretend",
    "simulate",
]

# Delimiters to prevent content injection
 DELIMITERS = [
    ["### USER CONTEXT ###", "### END USER CONTEXT ###"],
    ["RETRIEVED CONTEXT:", "### END RETRIEVED CONTEXT ###"],
    ["CITATIONS:", "### END CITATIONS ###"],
]
# Force these separators between system prompt sections
REQUIRED_SEPARATORS = ["\n\n", "---\n\n", "\n###\n"]


class PromptAnalysisResult(BaseModel):
    """Result of prompt security analysis."""

    is_safe: bool
    concerns: list[str]
    removed_patterns: list[str]


class PredeterminedOutput(BaseModel):
    """Result if prompt injection detected."""

    definition = "the provided context"
    response = "I could not find this in the policy documents. Please contact {contact_info}."


class PromptGuard:
    """Protects LLM prompts from injection and unwanted completions."""

    @classmethod
    def check_prompt_injection(cls, user_question: str) -> PromptAnalysisResult:
        """
        Scan user question for potential prompt injection attempts.

        Args:
            user_question: The user's question text.

        Returns:
            PromptAnalysisResult with security status and concerns.
        """
        concerns = []
        removed_patterns = []

        # Normalize to lowercase for checking
        normalized = user_question.lower()

        # Check for forbidden leader patterns
        for leader in FORBIDDEN_LEADERS:
            if leader in normalized:
                concerns.append(f"Potential prompt injection attempt detected: '{leader}'")
                removed_patterns.append(leader)

        # Check for attempt to manipulate SO / SYSTEM instruction boundaries
        system_keywords = [
            "you are not",
            "you are no longer",
            "change your instructions",
            "ignore the instructions",
            "override",
            "break",
            "attack",
        ]
        for keyword in system_keywords:
            if keyword in normalized:
                concerns.append(f"Potential system instruction manipulation: '{keyword}'")

        # Check for attempt to escape context boundaries
        if any(
            boundary in normalized
            for boundary in ["break out of", "break free", "execute as", "run as"]
        ):
            concerns.append("Attempt detected to escape context boundaries")

        # Check for potential JDBC/SQL injection disguised as questions
        sql_patterns = [
            r"SELECT\s+\*",
            r"INSERT\s+INTO",
            r"UPDATE\s+\w+\s+SET",
            r"DELETE\s+FROM",
            r"CREATE\s+TABLE",
            r"DROP\s+TABLE",
        ]
        for pattern in sql_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                concerns.append(f"SQL injection pattern detected: '{pattern}'")

        is_safe = len(concerns) == 0

        return PromptAnalysisResult(
            is_safe=is_safe, concerns=concerns, removed_patterns=removed_patterns
        )

    @classmethod
    def sanitize_user_query(cls, user_query: str) -> str:
        """
        Sanitize user query to remove potential injection characters.

        Args:
            user_query: The original user query.

        Returns:
            Sanitized query safe for injection into prompts.
        """
        sanitized = user_query

        # Remove potential attack characters from beginning/end
        sanitized = sanitized.strip()

        # Truncate if too long (prevents prompt injection via long inputs)
        MAX_QUESTION_LENGTH = 2000
        if len(sanitized) > MAX_QUESTION_LENGTH:
            sanitized = sanitized[:MAX_QUESTION_LENGTH]

        # Additional sanitization: don't allow newlines to create deceptive structure
        # This is conservative - we keep it minor but effective
        sanitized = re.sub(r"\n{5,}", "\n\n", sanitized)

        return sanitized

    @classmethod
    def wrap_system_prompt(
        cls, context: str, user_question: str, airline: str = "all", contact: str = "the airline"
    ) -> str:
        """
        Build a robust system prompt with injection defenses.

        Args:
            context: Retrieved context paragraphs.
            user_question: The sanitized user question.
            airline: The airline name.
            contact: Contact information string.

        Returns:
            Complete prompt with system instructions and user question.
        """
        airline_display = {
            "indigo": "IndiGo",
            "air_india": "Air India",
            "spicejet": "SpiceJet",
            "all": "Indian Airlines",
            "dgca": "DGCA",
        }.get(airline, "the airline")

        # Ensure context has some structure
        if not context or context.strip() == "":
            context = "No relevant policy documents were retrieved."

        # Double-check the user question has been sanitized
        safe_question = cls.sanitize_user_query(user_question)

        # Build prompt with enforced structure
        prompt = SYSTEM_TEMPLATE.format(
            airline_name=airline_display, contact_info=contact, user_question=safe_question
        )

        return prompt

    @classmethod
    def is_extraction_attempt(cls, query: str) -> bool:
        """
        Detect attempts to extract system prompt or hidden information.

        Args:
            query: The user query.

        Returns:
            True if likely extraction attempt, False otherwise.
        """
        extraction_patterns = [
            r"role\s*[=:]\s*",
            r"Prompt:\s*",
            r"Instructions:\s*",
            r"System:\s*",
            r"DESIGNATION:\s*",
            r"INSTRUCTIONS:\s*",
        ]
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in extraction_patterns)

    @classmethod
    def check_in_context_hiding(cls, context: str) -> bool:
        """
        Check if context contains hidden instructions or directives.

        Args:
            context: Retrieved context text.

        Returns:
            True if hidden content detected, False otherwise.
        """
        # Patterns that could hide instructions within context
        suspicious_patterns = [
            r"ignore\s+previous",
            r"override\s+system",
            r"forget\s+instructions",
            r"do\s+not\s+cite",
            r"attack\s+instructions",
        ]
        return any(re.search(pattern, context, re.IGNORECASE) for pattern in suspicious_patterns)


__all__ = ["PromptGuard", "PromptAnalysisResult", "PredeterminedOutput"]