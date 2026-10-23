from conftest import term_glossary
"""Required scope omission uses the existing single durable repair owner."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.corrected_memory import Memory
from semantic_runtime.legal_agent import request_entry as entry
from semantic_runtime.legal_agent.output_contract import OutputContractError
from test_bounded_source_main import settings
from test_legal_agent_double_harness import ROOT,BINDING
from test_structure_first_search import structured_generation

@pytest.mark.parametrize('always_missing',[False,True])
def test_omitted_scope_is_repaired_once_and_failure_budget_survives_restart(tmp_path,structured_generation,always_missing):
    question='모의승인규정 원문을 확인해 줘'
    profile={**settings(),'request_entry_policy':'fused-title-v1','candidate_navigation':{
        'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
        'completion_policy_version':'investigation-completion-v8'}}
    app=create_app(tmp_path,structured_generation,contracts_root=ROOT,provider=object(),
        implementation='legal-agent-unified-v6',legal_agent_profile=profile,
        legal_agent_transport=S(binding=BINDING,validate_model=lambda:{'verified':True,'synthetic':True}))
    p=app.state.pipeline;calls=[]
    value={'routing':{'mode':'CASE','answer':'','reason':'원문 조사'},
        'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
            'queries':['모의승인규정'],'format':'prose','reason':'요청한 문서 확인',
            'search_scope_change':{'operation':'REPLACE','targets':[{'document':'모의승인규정','structure':None,'selection':None}],'user_quote':question}},
        'intent':{'purpose':'모의승인규정 원문 확인','concepts':['승인'],
            'issues':[{'id':'Q1','question':'모의승인규정 원문 확인','subject':'승인','kind':'OTHER','request_quote':question}]},
        'context_quotes':[],'search':{'mode':'STRUCTURE','title_hint_ids':[],'reason':'문서 원문 조사'}}
    scope=value['command'].pop('search_scope_change')
    value['search'].pop('title_hint_ids')
    value['search']['scope_decision']={'mode':'NAMED_SCOPE', 'targets':scope['targets'],
        'user_quote':scope['user_quote'], 'reason':'요청에 명시된 문서 전체'}
    def invoke(system,data,schema,phase,*args):
        calls.append(phase);out=deepcopy(value)
        if always_missing or len(calls)==1:out['search'].pop('scope_decision')
        return out
    request={'question':question,'document_ids':['d'],'use_llm':False}
    with p.term_agent.open_session(request,query=p.plan(question,['d']),runtime=tmp_path/'native') as native:
        executor=S(binding={'synthetic':'required-scope'},model=S(ensure=lambda:native,pipeline=p),shortcut_flags={})
        context={'utterance':question,'goals':[],'knowledge':[],'wiki_links':{},'allowed_documents':[{'id':'d','name':'모의승인규정'}]}
        for attempt in range(2 if always_missing else 1):
            repo=Memory(tmp_path/'entry.sqlite',executor,invoke)
            repo._entry_body={**request,'session_id':'s','request_id':'same-request'}
            repo._entry_principal={'user_id':'u','team_id':'risk_team','document_ids':['d']}
            try:
                if always_missing:
                    with pytest.raises(OutputContractError) as caught:entry.run(repo,context)
                    assert caught.value.repairable is False
                    assert all(row['repairable'] is False for row in caught.value.issues)
                else:
                    entry.run(repo,context)
                    assert executor.request_entry['command']['search_scope_change']['operation']=='REPLACE'
                assert calls==['request-entry','request-entry-repair']
            finally:repo.close()
    p.store.close()
