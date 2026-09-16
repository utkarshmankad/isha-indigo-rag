from unittest.mock import MagicMock,patch
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import src.api.main as api
import src.tenancy.registry as registry


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(registry,'TENANTS',{
        'indigo':registry.TenantConfig('indigo','indigo','IndiGo','chat-key','admin-key'),
        'spicejet':registry.TenantConfig('spicejet','spicejet','SpiceJet','other-chat','other-admin')})
    monkeypatch.setattr(api,'_pipeline',{'graph':MagicMock()})
    api._query_times.clear()


def test_chat_key_cannot_access_admin_even_in_admin_header():
    client=TestClient(api.app)
    for headers in ({'X-API-Key':'chat-key'},{'X-Admin-Key':'chat-key'},{}):
        assert client.get('/v1/admin/metrics',headers=headers).status_code == 401
    with patch('src.observability.admin_metrics.read_logs',return_value=[]):
        response=client.get('/v1/admin/metrics',headers={'X-Admin-Key':'admin-key'})
    assert response.status_code==200
    assert response.json()['airline']=='indigo'


def test_public_request_cannot_select_private_tenant_scope():
    client=TestClient(api.app)
    with patch.object(api,'run_agent',return_value={'answer':'public','confidence':0.7,'retrieved_chunks':[]}) as run:
        response=client.post('/v1/public/query',json={'query':'baggage allowance?', 'airline':'spicejet'},headers={'X-API-Key':'chat-key'})
    assert response.status_code==200
    assert run.call_args.kwargs['airline']=='all'


def test_public_aggregate_limit_is_enforced():
    client=TestClient(api.app)
    with patch.object(api,'run_agent',return_value={'answer':'ok','confidence':0.7,'retrieved_chunks':[]}):
        for _ in range(api._QPM_LIMIT):
            assert client.post('/v1/public/query',json={'query':'baggage allowance?'}).status_code==200
        assert client.post('/v1/public/query',json={'query':'baggage allowance?'}).status_code==429


def test_registry_rejects_role_key_reuse(monkeypatch):
    monkeypatch.setenv('TENANT_APIKEY_INDIGO','duplicate')
    monkeypatch.setenv('TENANT_ADMIN_APIKEY_INDIGO','duplicate')
    with pytest.raises(ValueError,match='distinct'):
        registry._load_registry()


def test_admin_scope_cannot_cross_airlines():
    assert registry.authenticate_admin('spicejet','admin-key') is None
    assert registry.authenticate_admin('indigo','chat-key') is None


def test_widget_contains_no_privileged_key():
    widget=(Path(__file__).resolve().parents[1]/'static/widget.html').read_text()
    assert 'X-API-Key' not in widget
    assert 'REPLACE_WITH_TENANT_API_KEY' not in widget
    assert '/v1/public/query' in widget


def test_widget_sends_history_and_renders_clickable_citations():
    widget=(Path(__file__).resolve().parents[1]/'static/widget.html').read_text()
    assert 'history' in widget
    assert 'sessionStorage' in widget  # per-tab only, never localStorage/cross-session
    assert 'source_url' in widget
    assert 'target = "_blank"' in widget or "target = '_blank'" in widget


def test_widget_offers_contact_capture_on_refusal():
    widget=(Path(__file__).resolve().parents[1]/'static/widget.html').read_text()
    assert '/v1/public/escalations/' in widget
    assert 'data.refused' in widget
    assert 'renderContactForm' in widget


def test_widget_offers_feedback_buttons_on_every_answer():
    widget=(Path(__file__).resolve().parents[1]/'static/widget.html').read_text()
    assert '/v1/public/feedback/' in widget
    assert 'renderFeedbackButtons' in widget
    # feedback call, unlike the contact form, must not be gated on
    # data.refused — every answer gets a rating opportunity.
    feedback_call_line = next(l for l in widget.splitlines() if 'renderFeedbackButtons(placeholder' in l)
    assert 'data.refused' not in feedback_call_line


def test_widget_never_sets_href_without_scheme_check():
    """Regression: source_url is tenant-controlled and rendered as <a href>
    — the widget must re-validate the scheme itself (defense in depth),
    never trust the API response alone, or a javascript:/data: URL that
    somehow reaches it executes on click."""
    widget=(Path(__file__).resolve().parents[1]/'static/widget.html').read_text()
    assert 'isSafeUrl' in widget
    assert 'https?:' in widget
    href_line = next(l for l in widget.splitlines() if 'a.href' in l)
    # a.href must be inside the isSafeUrl-guarded branch, not unconditional
    assert widget.index('isSafeUrl') < widget.index(href_line)


@pytest.mark.parametrize('next_scope',[('all',None),('indigo',None),('spicejet','spicejet')])
def test_private_chat_is_cleared_when_view_or_auth_changes(next_scope):
    from src.security.session_scope import reset_chat_scope
    state={'chat_scope':('indigo','indigo'),'messages':[{'content':'private policy'}],
           'pending_query':'private followup','session_query_count':3,'session_confidences':[0.8]}
    reset_chat_scope(state,next_scope)
    assert state['messages']==[]
    assert 'pending_query' not in state
    assert state['session_query_count']==0


def test_same_scope_keeps_conversation():
    from src.security.session_scope import reset_chat_scope
    state={'chat_scope':('indigo','indigo'),'messages':[{'content':'earlier turn'}]}
    reset_chat_scope(state,('indigo','indigo'))
    assert state['messages']
