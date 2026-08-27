from unittest.mock import MagicMock, patch

from src.billing.stripe_usage import record_query_usage


def test_record_query_usage_noop_without_api_key(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)

    result = record_query_usage("indigo", "corr-1")

    assert result is False


def test_record_query_usage_sends_meter_event(monkeypatch):
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_fake")
    mock_stripe = MagicMock()

    with patch.dict("sys.modules", {"stripe": mock_stripe}):
        result = record_query_usage("indigo", "corr-2")

    assert result is True
    mock_stripe.billing.MeterEvent.create.assert_called_once()
    _, kwargs = mock_stripe.billing.MeterEvent.create.call_args
    assert kwargs["event_name"] == "isha_query"
    assert kwargs["payload"] == {"stripe_customer_id": "indigo", "value": "1"}
    assert kwargs["identifier"] == "corr-2"


def test_record_query_usage_never_raises_on_stripe_error(monkeypatch):
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_fake")
    mock_stripe = MagicMock()
    mock_stripe.billing.MeterEvent.create.side_effect = RuntimeError("stripe down")

    with patch.dict("sys.modules", {"stripe": mock_stripe}):
        result = record_query_usage("indigo", "corr-3")

    assert result is False
