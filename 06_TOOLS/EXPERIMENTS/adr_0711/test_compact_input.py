"""Original delivery, reachable menus, immutable history and wire contracts."""
from copy import deepcopy
import json
import pytest
from jsonschema import Draft202012Validator
from test_law_grouped_navigation import session, enable, decide
from test_unit_fulltext_adaptive_read import tree
from conftest import term_glossary
from semantic_runtime.legal_agent import law_navigation as ln, law_candidates as lc
from semantic_runtime.legal_agent import investigation_chain as trail, evidence_inventory as inventory
from semantic_runtime.legal_agent.source_recall import SourceRecall
from semantic_runtime.legal_agent.gateway import compact_wire_view, compact_empty_arrays
from semantic_runtime.legal_agent.errors import ContractError, ProposalError


def start(native):
    s=native.sources
    enable(s,structure_first=True,selectable_search=True,investigation_control=True,
           completion_contract=True,batch_selected_pages=True,compact_input=True)
    s.entry_search={'mode':'FULLTEXT'}
    rec=SourceRecall(s).prepare()
    return ln.Investigation(s,s.context.request['question'],rec,None,120,None,None),rec


def choice(data,kind,target,queries=()):
    v=decide(data,kind,target)
    v.update(expected_state_version=data['state_version'],law_decisions=[],branch_decisions=[],queries=list(queries))
    return v


def test_unopened_tree_is_lazy_but_direct_original_is_complete(session,monkeypatch):
    inv,_=start(session[0]);calls=[];real=ln.sq.document_structure
    def counted(*args,**kw):calls.append(args[2]);return real(*args,**kw)
    monkeypatch.setattr(ln.sq,'document_structure',counted)
    data,actions=inv.view()
    assert not calls
    assert all(l['document_structure']['deferred'] for l in data['laws'])
    law=data['laws'][0];hit=law['article_matches'][0]
    assert law['more_article_matches_action'] in actions
    v=choice(data,'READ_ARTICLES',hit['read_action'])
    inv.validate(v,data,actions);inv.execute(v,data,actions)
    following,_=inv.view()
    assert calls and following['sources']
    source=inv.s.tools.sources[hit['source_id']]
    expected=inventory.expected(inv.s,source['document_id'],[r['block_id'] for r in source['blocks']])
    delivered=[span for page in following['sources'] for span in page['spans']]
    assert inventory.covers(expected,delivered)
    assert all(g['status']!='ACTIVE' for g in inv.p['groups'].values())


def test_open_search_details_then_return_retains_current_history(session):
    inv,_=start(session[0]);data,actions=inv.view();frame=data['chain_frame_id']
    target=data['laws'][0]['more_article_matches_action']
    v=choice(data,'OPEN_LAW',target);inv.validate(v,data,actions);inv.execute(v,data,actions)
    expanded,actions=inv.view()
    assert expanded['laws'][0]['document_structure'].get('deferred') is not True
    assert expanded['laws'][0]['articles']
    back=next(k for k,a in actions.items() if a['action']=='RETURN_TO' and a['identity']['frame_id']==frame)
    v=choice(expanded,'RETURN_TO',back);inv.validate(v,expanded,actions);inv.execute(v,expanded,actions)
    restored,_=inv.view()
    assert restored['return_context']['frame_id']==frame
    assert [s['action'] for s in restored['investigation_chain']['steps']]==['OPEN_LAW','RETURN_TO']


def test_compact_policy_does_not_bypass_duplicate_search_or_resume_binding(session):
    inv,rec=start(session[0]);data,actions=inv.view()
    target=next(k for k,a in actions.items() if a['action']=='RESEARCH')
    repeated=choice(data,'RESEARCH',target,inv.p['query_surface_history'][0])
    with pytest.raises(ProposalError,match='unchanged|same morphemes'):inv.validate(repeated,data,actions)
    saved=deepcopy(inv.p);inv.s.profile['candidate_navigation']['compact_input']=False
    with pytest.raises(ContractError,match='binding changed'):
        ln.Investigation(inv.s,inv.question,rec,None,120,saved,None)


def wire_view():
    text='제49조 ① 본문을 모두 읽는다.\n1. 필수 조건을 확인한다.\n2. 예외와 단서를 누락하지 않는다.'
    span={'block_id':'1','evidence_id':'E1','text':text,'start_cp':0,'end_cp':len(text)}
    return {'input_projection':'compact-selection-source-v1','sources':[
        {'source_id':'source:a','document_id':'doc:a','text':text,'spans':[deepcopy(span)],'adopted_spans':[deepcopy(span)],'evidence_ids':['E1']}],
        'exact_evidence':[{'evidence':'E1','text':text,'spans':[deepcopy(span)]}],
        'evidence_options':[{'id':'S1','source_id':'source:a','text':text[8:25],'start_cp':8,'end_cp':25}],
        'laws':[{'articles':[{'previews':[{'source_id':'source:a','text':text}]}]}]}


def restore_refs(value,texts):
    if isinstance(value,list):return [restore_refs(v,texts) for v in value]
    if not isinstance(value,dict):return value
    out={k:restore_refs(v,texts) for k,v in value.items() if k not in ('text_id','text_ref')}
    if 'text_ref' in value:
        r=value['text_ref'];out['text']=texts[r['id']][r['start']:r['end']]
    return out


def test_wire_keeps_full_source_and_all_citation_segments_reconstruct_exactly():
    view=wire_view();before=deepcopy(view);wire=compact_wire_view(view,'investigate')
    assert view==before
    texts={s['text_id']:s['text'] for s in wire['sources']}
    assert restore_refs(wire,texts)==before
    assert wire['sources'][0]['text']==before['sources'][0]['text']
    needle=before['sources'][0]['text']
    assert json.dumps(wire,ensure_ascii=False).count(json.dumps(needle,ensure_ascii=False)[1:-1])==1


@pytest.mark.parametrize('change',['other_source','not_delivered','other_evidence'])
def test_undelivered_or_different_original_is_never_replaced(change):
    view=wire_view()
    if change=='other_source':view['evidence_options'][0]['source_id']='source:private'
    elif change=='not_delivered':view['evidence_options'][0]['text']='원문에 없는 추가 내용'
    else:view['exact_evidence'][0]['evidence']='E-other'
    key='exact_evidence' if change=='other_evidence' else 'evidence_options'
    wire=compact_wire_view(view,'investigate');assert wire[key][0]['text']==view[key][0]['text']


def test_multiple_pages_same_source_resolve_against_correct_page():
    view=wire_view();view['sources'].insert(0,{'source_id':'source:a','text':'다른 페이지'})
    wire=compact_wire_view(view,'investigate')
    assert wire['evidence_options'][0]['text_ref']['id']=='TEXT2'


def test_every_action_and_result_survives_brief_history_without_mutation():
    chain={'contract':'test','steps':[{'id':str(i),'number':i,'action':'READ','status':'COMPLETED',
        'reason':'필요한 원문 확인','targets':[{'id':'T'+str(i),'label':'제49조제1항 전체','identity':{'document_id':'d','unit_id':'49-1'}}],
        'outcome':{'delivered_pages':i,'adopted':[]},'queries':[],'notes':'상세 설명'*100,'branch_decisions':[{'reason':'상세'*100}]} for i in range(1,21)],'judgments':[]}
    before=deepcopy(chain);brief=trail.compact(chain,brief=True)
    assert chain==before and len(brief['steps'])==20
    for raw,row in zip(chain['steps'],brief['steps']):
        assert all(row[k]==raw[k] for k in ('id','number','action','status','reason','queries','outcome'))
        assert row['targets'][0]['location']=={'document_id':'d','unit_id':'49-1'}
        assert 'notes' not in row and 'branch_decisions' not in row


@pytest.mark.parametrize('value',[[],[{}],['x'],None,{},[{'status':'ADOPT'}]])
def test_empty_array_projection_preserves_validity_and_original_schema(value):
    schema={'type':'array','maxItems':0,'items':{'type':'object','properties':{'status':{'enum':['ADOPT']}}}}
    before=deepcopy(schema);wire=compact_empty_arrays(schema)
    assert schema==before
    assert Draft202012Validator(schema).is_valid(value)==Draft202012Validator(wire).is_valid(value)


def test_policy_requires_completion_and_defaults_off():
    assert not lc.validate_policy({})['compact_input']
    with pytest.raises(ContractError):lc.validate_policy({'compact_input':True})
