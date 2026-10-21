from pathlib import Path
from copy import deepcopy
import json,gzip,itertools
import pytest
from jsonschema import Draft202012Validator as V
from semantic_runtime.legal_agent import decision_projection as dp
from semantic_runtime.legal_agent.law_navigation import decision_schema
from semantic_runtime.legal_agent.minimal_output import Projection
from semantic_runtime.legal_agent.navigation_input import NavigationReferences
from semantic_runtime.legal_agent.local_gemma import provider_request
from semantic_runtime.legal_agent.errors import ProposalError
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0855-fulltext-schema-live-audit-v2/artifacts'
def saved(run,n):return json.load(gzip.open(A/run/'canonical'/f'{n:03d}.json.gz','rt'))
def regenerate(record):
    view=record['view']; old=record['schema']
    typed=set()
    for b in old.get('anyOf',[]):
        if 'structure_filter' in b.get('required',[]):typed.update(b['properties']['targets']['items'].get('enum',[]))
    actions={a['id']:{**a,'identity':{'document_id':'recorded-scope'} if a['id'] in typed else {}} for a in view['actions']}
    canonical=decision_schema(view,actions,{b['id'] for b in view['branches']})
    wire,expand,receipt=dp.prepare(canonical,view)
    refs=NavigationReferences(view)
    return canonical,wire,expand,refs,Projection(refs.schema(wire)),receipt

rows=[]
for run in ('run-001','run-002'):
    calls=json.loads((A/run/'calls.json').read_text())
    for c in calls:
        if c.get('http_status')!=200:continue
        rec=saved(run,c['canonical_generation'])
        if not rec['view'].get('source_stage','').startswith('source-law-navigation-'):continue
        p=next((A/run/'provider').glob(f"call-{c['call']:03d}-*/response.json"))
        body=json.loads(p.read_text())
        if body['choices'][0]['finish_reason']!='stop':continue
        rows.append((run,c['call'],rec,json.loads(body['choices'][0]['message']['content'])))

@pytest.mark.parametrize('run,call,record,raw',rows,ids=[f'{r}-{c}' for r,c,_,_ in rows])
def test_recorded_navigation_boundary(run,call,record,raw):
    canonical,wire,expand,refs,p,receipt=regenerate(record)
    if run=='run-001' and call==6:
        assert not V(p.wire).is_valid(raw)
        with pytest.raises(ProposalError):p.expand(raw)
        return
    result=expand(refs.decode(p.expand(raw),refs.schema(wire)))
    V(canonical).validate(result)
    assert result['reason']==raw['reason']
    if result['next_action'] not in ('RESEARCH','SEARCH_BODY','SEARCH_STRUCTURE'):assert result['queries']==[]
    # A freshly emitted generation omits inactive fields and preserves choices.
    projected=p.project(refs.view({k:v for k,v in result.items() if k in wire['properties']}))
    # readOnly is a generation omission; full legacy values remain decodable.
    assert expand(refs.decode(p.expand(projected),refs.schema(wire)))==result

@pytest.mark.parametrize('kind',['RESEARCH','SEARCH_BODY','READ_ARTICLES','READ_PARENT','READ_SCOPE','OPEN_LAW','NEXT_LAWS','NEXT_ARTICLES','NEXT_HITS','SEARCH_STRUCTURE','OPEN_STRUCTURE','BROWSE_STRUCTURE','NEXT_STRUCTURE','FOLLOW_CONNECTION','NEXT_DEFINITIONS','RETURN_TO','VIEW_SAVED_SOURCE','PENDING'])
@pytest.mark.parametrize('variant',['valid','wrong-target','missing-reason','missing-query'])
def test_all_action_requirements(kind,variant):
    from semantic_runtime.legal_agent import completion_contracts as cc
    view={'presentation_id':'v1','laws':[],'basis':[],'branches':[], 'issues':[{'id':'Q1','request_quote':'공개 규정'}],
          'completion_contract':cc.V8,'control_contract':'v1','state_version':2,'investigation_scope':{'request':'공개 규정'},'sources':[]}
    kinds=['RESEARCH','SEARCH_BODY','READ_ARTICLES','READ_PARENT','READ_SCOPE','OPEN_LAW','NEXT_LAWS','NEXT_ARTICLES','NEXT_HITS','SEARCH_STRUCTURE','OPEN_STRUCTURE','BROWSE_STRUCTURE','NEXT_STRUCTURE','FOLLOW_CONNECTION','NEXT_DEFINITIONS','RETURN_TO','VIEW_SAVED_SOURCE']
    actions={k:{'id':k,'action':k,'identity':{},'label':'허용 행동'} for k in kinds}
    original=decision_schema(view,actions,set());wire,expand,receipt=dp.prepare(original,view);p=Projection(wire)
    raw={'next_action':kind,'targets':[] if kind=='PENDING' else [kind], 'reason':'원문 확인',
         'evidence_sufficient':False,'sufficiency_reason':'조사 중','exploration':[] if kind=='PENDING' else [{'target':kind,'issue_id':'Q1','missing_need':'원문','relation':'DIRECT'}]}
    if kind in ('RESEARCH','SEARCH_BODY','SEARCH_STRUCTURE'):raw['queries']=['공개 규정']
    expected=True
    if kind=='PENDING':raw.pop('targets');raw.pop('exploration')
    if variant=='wrong-target':raw['targets']=['not-offered'];expected=False
    if variant=='missing-reason':raw.pop('reason');expected=False
    if variant=='missing-query' and 'queries' in raw:raw.pop('queries');expected=False
    request=provider_request({'response_format':{'type':'json_schema','json_schema':{'name':'test','schema':p.wire}}})
    for s in (p.wire,request['response_format']['json_schema']['schema']):
        V.check_schema(s);assert V(s).is_valid(raw)==expected
    if expected:
        value=expand(p.expand(raw));V(original).validate(value)
        assert value['presentation_id']=='v1' and value['expected_state_version']==2
    else:
        with pytest.raises(ProposalError):p.expand(raw)

def test_no_provider_loss_of_branch_constraints():
    from semantic_runtime.legal_agent.wire_schema import navigation_shape
    s={'type':'object','properties':{k:{} for k in ['next_action','targets','reason']},'anyOf':[{'required':['queries']}]}
    assert navigation_shape(s)==s
