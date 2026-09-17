from src.observability.redaction import redact_pii


def test_redacts_email_address():
    assert redact_pii("email me at passenger@example.com please") == \
        "email me at [REDACTED-EMAIL] please"


def test_redacts_phone_number_with_country_code():
    assert redact_pii("call me at +91 98765 43210") == "call me at [REDACTED-PHONE]"


def test_redacts_phone_number_with_hyphens():
    assert redact_pii("my number is 0124-6173838") == "my number is [REDACTED-PHONE]"


def test_redacts_plain_10_digit_number():
    assert redact_pii("reach me on 9876543210 anytime") == "reach me on [REDACTED-PHONE] anytime"


def test_redacts_multiple_occurrences():
    text = "email a@b.com or call 9876543210"
    assert redact_pii(text) == "email [REDACTED-EMAIL] or call [REDACTED-PHONE]"


def test_does_not_redact_short_numeric_sequences():
    """Fare amounts, flight numbers, weights, etc. must survive intact —
    only 10+ digit sequences are treated as phone-shaped."""
    assert redact_pii("baggage fee is 500 rupees, flight 6E123") == \
        "baggage fee is 500 rupees, flight 6E123"


def test_does_not_redact_ordinary_text():
    text = "what is the baggage allowance for a domestic flight?"
    assert redact_pii(text) == text


def test_empty_string_is_noop():
    assert redact_pii("") == ""


def test_none_like_falsy_is_returned_unchanged():
    assert redact_pii("") == ""
