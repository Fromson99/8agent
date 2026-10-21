from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from test_unit_fulltext_adaptive_read import tree,session,hit
from test_structure_reading import setup,value
from semantic_runtime.legal_agent import law_navigation as ln,definition_entry as de,request_repair as rr
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.legal_agent.errors import ContractError,ProposalError
from semantic_runtime.legal_agent.local_gemma import provider_request
from test_navigation_input_compaction import menu,decision


def install(native,count=1):
    s=native.sources;h=hit(native);raw=s.store.source('d','3');txt=raw['text'];key='긴급 승인';start=txt.index(key);source=s.tools.sources[h['source_id']]
    s.tools.definitions={str(i):dict(id=str(i),key=key,document_id='d',source_id=h['source_id'],unit_id='3',block_id='3',source_text=txt,source_text_sha256=text_hash(txt),source_artifact_sha256=source['source_artifact_sha256'],term_start=start,term_end=start+len(key)) for i in range(count)}
    s.tools.definition_summaries=tuple((i,h['source_id'],key,key,'UNRESOLVED') for i in s.tools.definitions)
    class DB:
        def execute(self,sql,*args):
            if sql.startswith('SELECT reference_id FROM definition_reference'):return []
            return original.execute(sql,*args)
        def __getattr__(self,key):return getattr(original,key)
    original=s.tools.db;s.tools.db=DB()
    inv,rec=setup(native,'긴급 승인 기준');inv.policy['definition_entry']=True
    return inv,rec


def test_first_view_proposes_definition_read_and_acquires_original(session):
    native,_=session;inv,rec=install(native);data,actions=inv.view();row=data['definition_entries']['items'][0]
    target=row['definition']['read_action'];assert actions[target]['action']=='READ_ARTICLES'
    assert not inv.active_records()
    inv.execute_tool(value(data,'READ_ARTICLES',target),data,actions)
    assert any(e['document_id']=='d' for r in inv.p['selected'].values() for e in r['evidence'])
    assert not inv.active_records()


def test_page_resume_progress_and_stale_handle(session):
    native,_=session;inv,rec=install(native,18);data,actions=inv.view();target=data['definition_entries']['next_action'];old=deepcopy(inv.p)
    inv.execute_tool(value(data,'NEXT_DEFINITIONS',target),data,actions)
    assert inv.p['definition_offset']==8 and rr.progress_facts(inv.p)-rr.progress_facts(old)
    resumed=ln.Investigation(inv.s,inv.question,rec,None,120,deepcopy(inv.p),None);resumed.policy['definition_entry']=True
    nxt,_=resumed.view();assert nxt['definition_entries']['offset']==8
    with pytest.raises(ContractError):resumed.execute_tool(value(data,'NEXT_DEFINITIONS',target),data,actions)


def test_no_match_adds_no_context_or_actions(session):
    native,_=session;inv,_=install(native);inv.s.context.request['question']='무관한 문의';data,actions=inv.view()
    assert 'definition_entries' not in data and not any(a['action']=='NEXT_DEFINITIONS' for a in actions.values())


def test_wire_shape_removes_action_cross_product_but_original_rejects_wrong_target():
    schema=menu();wire=provider_request({'response_format':{'json_schema':{'schema':schema}}})['response_format']['json_schema']['schema']
    good=decision('global',['규정']);bad=decision('global',[],{'coordinate':'제1조','title':'','coordinate_scope':'body'})
    assert Draft202012Validator(schema).is_valid(good) and Draft202012Validator(wire).is_valid(good)
    assert Draft202012Validator(wire).is_valid(bad) and not Draft202012Validator(schema).is_valid(bad)
    assert 'anyOf' not in wire and 'anyOf' in schema
    from semantic_runtime.legal_agent.navigation_input import NavigationReferences
    with pytest.raises(ProposalError):NavigationReferences({}).decode(bad,schema)

@pytest.mark.parametrize('change',[lambda d:d.update(targets=['unknown']),lambda d:d.update(presentation_id='stale'),lambda d:d.update(extra=True)])
def test_projection_retains_identity_shape_boundaries(change):
    schema=menu();wire=provider_request({'response_format':{'json_schema':{'schema':schema}}})['response_format']['json_schema']['schema'];d=decision('global',['규정']);change(d)
    assert not Draft202012Validator(wire).is_valid(d)
