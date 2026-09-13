"""Discard chat context when the authenticated viewing scope changes."""

def reset_chat_scope(state, scope: tuple[str, str | None]) -> None:
    if state.get('chat_scope') != scope:
        state['messages'] = []
        state['session_query_count'] = 0
        state['session_confidences'] = []
        state.pop('pending_query', None)
        state['chat_scope'] = scope
