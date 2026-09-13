from unittest.mock import MagicMock,patch
import pytest
from src.agent.graph import build_graph,run_agent
from src.retrieval.hybrid_search import reciprocal_rank_fusion
from tests.test_refusal import SAMPLE_CHUNKS


def run_with(results):
    store=MagicMock()
    # This formerly bypassed the evidence gate even when hybrid search was empty.
    store.query.return_value=[{'score':0.99}]
    with patch('src.agent.graph.embed_batch',return_value=[[0.1]*8]), \
         patch('src.agent.graph.hybrid_search',return_value=results), \
         patch('src.agent.graph.generate_answer',return_value='generated') as generate:
        state=run_agent('What is the baggage allowance?',build_graph(SAMPLE_CHUNKS,store),airline='indigo')
        prompts=[c.args[0] for c in generate.call_args_list]
    return state,prompts


def candidate(text='Baggage allowance is 7kg.',vector_score=0.8):
    return {**SAMPLE_CHUNKS[0], 'text':text,'score':vector_score,'vector_score':vector_score,'fusion_score':0.03}


def test_empty_evidence_never_generates_an_answer_from_unrelated_high_score():
    state,prompts=run_with([])
    assert state['confidence']==0
    assert 'could not find this' in state['answer']
    assert all('policy document answering' in prompt for prompt in prompts) # HyDE only


@pytest.mark.parametrize('text',['   ','X'*4000])
def test_blank_or_oversized_evidence_cannot_support_confidence(text):
    state,_=run_with([candidate(text)])
    assert state['retrieved_chunks']==[]
    assert state['confidence']==0


def test_selected_vector_score_controls_confidence():
    state,prompts=run_with([candidate(vector_score=0.72)])
    assert state['confidence']==0.72
    assert state['answer']=='generated'
    assert len(prompts)==1


def test_lexical_normalization_is_not_treated_as_cosine_confidence():
    lexical={**candidate(), 'score':1.0}
    lexical.pop('vector_score')
    state,_=run_with([lexical])
    assert state['confidence']==0
    assert 'could not find this' in state['answer']


def test_fusion_preserves_vector_similarity_separately():
    bm=[{**candidate(), 'score':1.0}]
    bm[0].pop('vector_score')
    result=reciprocal_rank_fusion(bm,[{**candidate(), 'score':0.52}],top_k=1)
    assert result[0]['vector_score']==0.52


def test_nonfinite_similarity_cannot_bypass_refusal():
    state,_=run_with([candidate(vector_score=float('nan'))])
    assert state['confidence']==0
