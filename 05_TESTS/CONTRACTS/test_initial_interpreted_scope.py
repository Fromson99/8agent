"""One initial request: model interpretation, exact quote, stored ACL binding."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import query_scope as qs
from semantic_runtime.legal_agent.unified_rag import UnifiedRag
from semantic_runtime.legal_agent.errors import ContractError

QUESTION = '모의자료법과 그 시행령에서 보관 규칙을 찾아줘'

def metadata():
    return S(documents={'a':'모의자료법','b':'모의자료법 시행령'}, document_context={},
             document_aliases={},units={},stored_coordinates={})

def change():
    return {'operation':'REPLACE','user_quote':'모의자료법과 그 시행령',
        'targets':[{'document':name,'structure':None,'selection':None}
                   for name in ('모의자료법','모의자료법 시행령')]}

def test_initial_scope_resolves_ellipsis_to_authorized_documents():
    out=qs.resolve(change(),None,metadata(),['a','b'],QUESTION,model_resolved=True)
    assert {t['document_id'] for t in out['targets']}=={'a','b'}
    s=S(matcher=metadata(),scope=['a','b']);qs.attach(s,out)
    assert qs.documents(s)==['a','b']

@pytest.mark.parametrize('failure',['quote','unauthorized','missing','ambiguous'])
def test_interpreted_name_does_not_bypass_quote_or_unique_acl_binding(failure):
    c=change();m=metadata();allowed=['a','b']
    if failure=='quote':c['user_quote']='질문에 없는 인용'
    elif failure=='unauthorized':allowed=['a']
    elif failure=='missing':c['targets'][1]['document']='없는 시행령'
    else:m.documents['c']=m.documents['b'];allowed.append('c')
    with pytest.raises(qs.UnresolvedScope):
        qs.resolve(c,None,m,allowed,QUESTION,model_resolved=True)

def test_same_native_scope_consumer_enables_only_initial_command():
    host=S(model=S(ensure=lambda:S(sources=S(matcher=metadata()))))
    state={'document_ids':['a','b']}
    command={'method_id':'CASE_START','search_scope_change':change()}
    out=UnifiedRag.scope_state(host,state,command,QUESTION)
    assert {t['document_id'] for t in out['search_scope']['targets']}=={'a','b'}
    command['method_id']='RESEARCH_REPLAN'
    with pytest.raises(qs.UnresolvedScope):UnifiedRag.scope_state(host,state,command,QUESTION)

def test_interpreted_scope_hash_and_current_permission_are_rechecked():
    out=qs.resolve(change(),None,metadata(),['a','b'],QUESTION,model_resolved=True)
    bad=deepcopy(out);bad['targets'][1]['document_id']='a'
    with pytest.raises(ContractError,match='hash'):qs.attach(S(matcher=metadata(),scope=['a','b']),bad)
    with pytest.raises(ContractError,match='authorization'):qs.attach(S(matcher=metadata(),scope=['a']),out)
