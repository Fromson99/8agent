from conftest import term_glossary
"""Synthetic structured decisions and real source/API contracts; no live model."""
from copy import deepcopy
from types import SimpleNamespace as S
import json
import sqlite3

import pytest
from jsonschema import validate, ValidationError

from lawrag.core.legal_coordinate import LegalCoordinate
from semantic_runtime.legal_agent import structure_selection as ss, query_scope as qs
from semantic_runtime.legal_agent import structure_query as sq, law_navigation as ln
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from test_unit_fulltext_adaptive_read import tree, session
from test_followup_structure_lookup import investigation, apply
from test_structure_first_search import structured_generation
from test_multiturn_structured_scope import tree as scoped_tree

# The request-entry search field asks_definition exists from the definition-priority change on; older
# code rejects it, so scripted entries carry it only when the loaded schema has it.
from semantic_runtime.legal_agent import request_entry as _asks_entry
import json as _asks_json
ASKS_DEFINITION = {'asks_definition': True} if 'asks_definition' in _asks_json.dumps(_asks_entry.schema(model=True)) else {}


def single(n): return {'kind':'SINGLE','value':{'n':n}}
def interval(start, end, first=True, last=True):
    return {'kind':'RANGE','start':{'n':start} if start else None,
        'end':{'n':end} if end else None,'start_inclusive':first,'end_inclusive':last}
def choose(include=None, exclude=None, *, article=6, dash=3, paragraph=2, unit='호', root=False):
    path=[] if root else [{'unit':'조','n':article,**({'dash':dash} if dash else {})}]
    if paragraph is not None and not root:path.append({'unit':'항','n':paragraph})
    return {'coordinate_scope':'body','groups':[{'parent_path':path,'unit':unit,
        'include':include or [{'kind':'ALL'}], 'exclude':exclude or []}]}


def matcher(count=7):
    coords={};units={};sources={}
    article=LegalCoordinate('조',6,dash=3)
    paragraph=article.append_part(LegalCoordinate('항',2))
    def add(uid,parent,coord,span):
        coords[('d',uid)]=coord
        units[('d',uid)]={'parent':parent,'coordinate_scope':'body','span':span,
            'surface':coord.canonical_surface(),'coordinate_binding':{'mode':'stored'}}
        sources[uid]={'document_id':'d','unit_id':uid}
    add('a',None,article,[0,count+3]);add('p','a',paragraph,[1,count+3])
    for n in range(1,count+1):add(str(n),'p',paragraph.append_part(LegalCoordinate('호',n)),[n+1,n+2])
    return S(documents={'d':'모의규정'},document_context={},document_aliases={},units=units,
        stored_coordinates=coords,sources=sources,_unit_sources=lambda did,uid:[uid])


@pytest.mark.parametrize('selection,expected',[
    (choose([interval(1,3)]),['1','2','3']),
    (choose([interval(1,3),single(7)]),['1','2','3','7']),
    (choose(exclude=[single(5)]),['1','2','3','4','6','7']),
    (choose([interval(1,7)],[interval(3,5)]),['1','2','6','7']),
    (choose([interval(3,None,False)]),['4','5','6','7']),
    (choose([interval(None,3,True,False)]),['1','2']),
    (choose([single(3),single(1),single(3)]),['1','3']),
])
def test_model_set_algebra(selection,expected,monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('structured selection must not parse natural language')
    monkeypatch.setattr(sq,'find_coordinates',forbidden)
    out=ss.resolve(selection,matcher(),'d',['d'])
    assert out['unit_ids']==expected and not out['content_read']


def test_inserted_item_is_selected_in_actual_order_not_integer_expansion():
    m=matcher();parent=m.stored_coordinates[('d','p')]
    m.stored_coordinates[('d','2a')]=parent.append_part(LegalCoordinate('호',2,sub=2))
    m.units[('d','2a')]={'parent':'p','coordinate_scope':'body','span':[3.5,3.8]}
    assert ss.resolve(choose([interval(1,3)]),m,'d',['d'])['unit_ids']==['1','2','2a','3']


@pytest.mark.parametrize('selection,code',[
    (choose([single(99)]),'MISSING_ENDPOINT'),
    (choose([interval(3,1)]),'REVERSED_RANGE'),
    (choose(exclude=[{'kind':'ALL'}]),'EMPTY_SELECTION'),
    (choose(paragraph=9),'MISSING_PARENT'),
    (choose(unit='목'),'MISSING_SELECTION_LEVEL'),
])
def test_missing_or_invalid_set_is_not_partial_success(selection,code):
    m=matcher()
    page=sq.catalogue(m,['d'],document_id='d',structure_filter={'selection':selection})
    assert page['lookup_status']=='MISS' and page['items']==[]
    assert page['failure']['code']==code


def test_multiple_parent_groups_do_not_cross_bind_numbers():
    m=matcher();a=m.stored_coordinates[('d','a')]
    p=a.append_part(LegalCoordinate('항',3))
    m.stored_coordinates[('d','p3')]=p
    m.units[('d','p3')]={'parent':'a','coordinate_scope':'body','span':[10,12]}
    m.stored_coordinates[('d','p3i1')]=p.append_part(LegalCoordinate('호',1))
    m.units[('d','p3i1')]={'parent':'p3','coordinate_scope':'body','span':[11,12]}
    selection=choose([single(1)])
    selection['groups']+=choose([single(1)],paragraph=3)['groups']
    assert ss.resolve(selection,m,'d',['d'])['unit_ids']==['1','p3i1']
    with pytest.raises(ss.SelectionError,match='상위 조·항'):
        ss.resolve(choose([single(1)],paragraph=None),m,'d',['d'])


def test_parent_cannot_reinclude_excluded_descendant():
    selection=choose(exclude=[single(5)])
    selection['groups']+=choose([single(2)],paragraph=None,unit='항')['groups']
    with pytest.raises(ss.SelectionError) as caught:ss.resolve(selection,matcher(),'d',['d'])
    assert caught.value.code=='EXCLUSION_REQUIRES_FINER_SCOPE'


def test_acl_hash_and_excluded_metadata_checked_on_resume():
    m=matcher();selection=choose(exclude=[single(5)])
    with pytest.raises(ContractError,match='authorization'):ss.resolve(selection,m,'d',[])
    record=ss.resolve(selection,m,'d',['d']);ss.verify(record,m,['d'])
    corrupt=deepcopy(record);corrupt['unit_ids'].append('5')
    with pytest.raises(ContractError,match='hash'):ss.verify(corrupt,m,['d'])
    m.units[('d','5')]['title']='changed excluded node'
    with pytest.raises(ContractError,match='metadata'):ss.verify(record,m,['d'])


def scope_change(selection,quote='모의규정 5호는 빼고 전부',operation='REPLACE'):
    return {'operation':operation,'user_quote':quote,'targets':[
        {'document':'모의규정','structure':None,'selection':selection}]}


def test_scope_stores_entire_set_and_exclusions_without_normalized_quote_match():
    m=matcher(20);c=scope_change(choose(exclude=[single(5)]))
    scope=qs.resolve(c,None,m,['d'],c['user_quote'])
    assert len(scope['targets'])==19
    s=S(matcher=m,scope=['d']);qs.attach(s,scope)
    assert qs.direct(s,'d','4') and not qs.direct(s,'d','5') and not qs.direct(s,'d','p')
    assert scope['selections'][0]['excluded_unit_ids']==['5']
    prior=qs.resolve({'operation':'REPLACE','user_quote':'모의규정','targets':[{'document':'모의규정','structure':None}]},None,m,['d'],'모의규정')
    with pytest.raises(qs.UnresolvedScope,match='제외 항목'):
        qs.resolve({**c,'operation':'ADD'},prior,m,['d'],c['user_quote'])
    kept=qs.resolve({'operation':'KEEP','targets':[],'user_quote':''},scope,m,['d'],'다시 설명해')
    assert kept==scope


def test_catalogue_pages_preserve_complete_selection_and_direct_scope_miss():
    m=matcher();f={'selection':choose(exclude=[single(5)])}
    first=sq.catalogue(m,['d'],document_id='d',structure_filter=f,limit=2)
    second=sq.catalogue(m,['d'],document_id='d',structure_filter=f,limit=2,offset=first['next_offset'])
    assert [r['unit_id'] for r in first['items']+second['items']]==['1','2','3','4']
    assert first['selection_resolution']==second['selection_resolution'] and first['total']==6
    miss=sq.catalogue(m,['d'],document_id='d',structure_filter=f,row_filter=lambda r:r['unit_id']=='1')
    assert miss['items']==[] and miss['failure']['code']=='OUTSIDE_DIRECT_SCOPE'


def test_navigation_selects_and_reads_exact_items_without_excluded_sibling(session):
    native,_=session;inv=investigation(native)
    selection=choose(exclude=[single(2)],article=1,dash=None,paragraph=1)
    data,actions=inv.view()
    target=next(l['structure_search_action'] for l in data['laws'] if l['document_id']=='d')
    data,actions=apply(inv,data,actions,'SEARCH_STRUCTURE',target,structure_filter={'selection':selection})
    page=data['structure_catalogue']
    assert [r['unit_id'] for r in page['items']]==['2']
    assert data['selection_progress'][0]['remaining_unit_ids']==['2']
    data,actions=apply(inv,data,actions,'READ_ARTICLES',page['items'][0]['read_action'])
    records=list(inv.p['selected'].values())
    assert any(r['offer']['unit_id']=='2' and set(r['offer']['block_ids'])=={'2','3'} for r in records)
    assert all('4' not in r['offer']['block_ids'] for r in records)
    progress=ss.progress(inv)[0]
    assert progress['acquired_complete']
    assert not progress['delivered_complete']  # receiving a page is not an acknowledged model delivery
    from semantic_runtime.legal_agent.evidence_inventory import acknowledge
    for page in data['sources']:acknowledge(inv.s,inv.p,page,data['presentation_id'])
    # Pagination may leave some original text unpresented; never infer completion.
    progress=ss.progress(inv)[0]
    assert progress['delivered_complete']==(len(progress['remaining_unit_ids'])==0)
    checkpoint=deepcopy(inv.p)
    ss.verify(next(iter(checkpoint['structure_selections'].values())),inv.s.matcher,inv.s.scope)


def test_request_schema_exposes_same_structural_algebra():
    from semantic_runtime.legal_agent import request_entry,source_query_planning
    target_schema=request_entry.schema()['properties']['command']['anyOf'][0]['properties']['search_scope_change']
    validate(scope_change(choose(exclude=[single(5)])),target_schema)
    plan=source_query_planning.catalogue_schema(['모의규정'])
    validate({'document':'모의규정','user_quote':'5호를 제외해','selection':choose(exclude=[single(5)])},
             plan['properties']['structure_selections']['items'])


def test_real_api_model_scope_excludes_article_and_reuses_request(tmp_path,structured_generation):
    from fastapi.testclient import TestClient
    from test_natural_language_routing import EntryTransport,app
    from test_unified_legal_agent import ok
    t=EntryTransport('CASE')
    question='모의승인규정에서 제2조는 빼고 전부 설명해'
    selection=choose(exclude=[single(2)],unit='조',root=True)
    t.command['task']=question
    t.command['search_scope_change']={'operation':'REPLACE','user_quote':question,
        'targets':[{'document':'모의승인규정','structure':None,'selection':selection}]}
    body={'question':question,'document_ids':['d'],'session_id':'s','request_id':'selection'}
    with TestClient(app(tmp_path,structured_generation,t)) as api:
        result=ok(api.post('/v1/rag/ask',json=body))
        calls=len(t.phases)
        again=ok(api.post('/v1/rag/ask',json=body))
        assert len(t.phases)==calls and result['answer']==again['answer']
        assert result['answer']['claims']
    journals=list(tmp_path.rglob('journal.sqlite'))
    found=[]
    for journal in journals:
        with sqlite3.connect(journal) as db:
            found.extend(json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='DIRECT_SEARCH_SCOPE_BOUND'"))
    scopes=[r['scope'] for r in found if r.get('scope')]
    assert scopes and len(scopes[0]['targets'])==1
    assert scopes[0]['selections'][0]['excluded_unit_ids']


@pytest.mark.parametrize('fused',[False,True])
def test_modern_api_keeps_exclusion_through_read_reply_and_restart(tmp_path,scoped_tree,fused):
    from fastapi.testclient import TestClient
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.shortcut_store import selected_store
    from test_assessment_source_reply import EmptyAssessment
    from test_bounded_source_main import settings
    from test_legal_agent_double_harness import ROOT,wire
    from test_memory_runtime_v2 import command
    question='모의승인규정 제1조 1항에서 2호는 빼고 전부 설명해'
    chosen=choose(exclude=[single(2)],article=1,dash=None,paragraph=1)
    change={'operation':'REPLACE','user_quote':question,'targets':[
        {'document':'모의승인규정','structure':None,'selection':chosen}]}
    class Transport(EmptyAssessment):
        def send_once(self,*,body,ticket):
            view=json.loads(body['messages'][1]['content'])['view'];phase=view.get('source_stage',view['phase'])
            if phase.startswith('request-entry'):
                self.phases.append(phase)
                return wire({'routing':{'mode':'CASE','answer':'','reason':'모의 구조 선택'},
                    'command':{'method_id':'CASE_START','source_category':'ALL','facts':[],
                        'queries':['승인'],'format':'prose','reason':'범위 선택'},
                    'intent':{'purpose':'승인 원문 설명','concepts':['승인'],'issues':[
                        {'id':'Q1','question':'승인 원문 설명','subject':'승인','kind':'OTHER','request_quote':question}]},
                    'context_quotes':[],'search':{**ASKS_DEFINITION, 'mode':'STRUCTURE','scope_decision':{'mode':'NAMED_SCOPE','targets':[{**t,'selection':t.get('selection')} for t in change['targets']],'user_quote':change['user_quote'],'reason':'사용자 지정 범위'},'reason':'범위 지정'}})
            if phase.startswith('memory-intent'):
                self.phases.append(phase)
                return wire({'purpose':'승인 원문 설명','concepts':['승인'],'background_quotes':[],
                    'issues':[{'id':'Q1','question':view['current_request'],'request_quote':view['current_request'],
                               'subject':'승인','kind':'OTHER'}]})
            return super().send_once(body=body,ticket=ticket)
    gen,idx=scoped_tree;t=Transport('repaired')
    t.command=command('CASE_START',document_scope_mode='AUTHORIZED',task=question,queries=['승인'],facts=[],search_scope_change=change)
    profile={**settings(),'max_model_attempts':40,'max_read_chars':10000,
        'request_entry_policy':'fused-title-v1' if fused else 'legacy',
        'candidate_navigation':{'mode':'law-first-v1','investigation_control':True,'completion_contract':True,
            'completion_policy_version':'investigation-completion-v8','compact_input':True,
            'structure_first':True,'selectable_search':True,'answer_first':True,'assessment_reentry_limit':0}}
    runtime=tmp_path/'runtime'
    def app():
        value=create_app(tmp_path,gen,contracts_root=ROOT,provider=object(),implementation='legal-agent-unified-v6',
            legal_agent_profile=profile,legal_agent_transport=t,runtime_root=runtime,
            memory_identity=lambda _:{'user_id':'synthetic','team_id':'risk_team','document_ids':['d']})
        value.state.pipeline.term_agent.unit_fulltext=idx
        return value
    body={'question':question,'session_id':'s','request_id':'r'}
    with TestClient(app()) as api:
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==200,response.text
        out=response.json();calls=len(t.phases)
        assert '긴급 승인 예외는 허용한다' in out['answer']['text']
        assert '일반 승인 예외는 허용하지 않는다' not in out['answer']['text']
    with TestClient(app()) as api:
        response=api.post('/v1/rag/ask',json=body)
        assert response.status_code==200,response.text
        assert response.json()['answer']==out['answer'] and len(t.phases)==calls
    with sqlite3.connect(selected_store(runtime)) as db:
        state=json.loads(db.execute('SELECT state FROM goal WHERE id=?',(out['question_id'],)).fetchone()[0])
    assert [r['unit_id'] for r in state['search_scope']['targets']]==['2']
    assert state['search_scope']['selections'][0]['excluded_unit_ids']==['4']


@pytest.mark.parametrize('repair',[False,True])
def test_compact_locate_schema_accepts_selection_without_an_extra_model_judge(session,repair):
    from semantic_runtime.legal_agent import decision_projection as dp,completion_contracts as cc
    native,_=session;inv=investigation(native)
    inv.modern=True;inv.p['completion_contract']=cc.V8
    data,actions=inv.view()
    chosen=choose([interval(1,2)],article=1,dash=None,paragraph=1)
    seen=[]
    def invoke(system,payload,schema,phase,timeout):
        seen.append(phase)
        assert 'parent_path' in system and 'structure_selection_progress' in payload
        option=next(o for o in payload['tool_options'] if o['choice']=='LOCATE' and o['scope']['document_id']=='d')
        value={'choice':'LOCATE','target':option['target'],'issue_id':'Q1','missing_need':'지정 범위',
            'relation':'DIRECT','source_ref':None,'structure_filter':{'selection':chosen}}
        if repair and len(seen)==1:
            value['structure_filter']['selection']=deepcopy(chosen)
            value['structure_filter']['selection']['groups'][0]['include'][0].pop('start')
        return value
    inv.invoke=invoke
    # This is the actual compact consumer used by modern SELECT.
    decision=dp.choose_read(inv,data,actions,'source-law-navigation-1')
    assert len(seen)==(2 if repair else 1) and decision['next_action']=='SEARCH_STRUCTURE'
    assert decision['structure_filter']=={'selection':chosen}
    inv.validate(decision,data,actions)
    inv.execute(decision,data,actions)
    assert [r['unit_id'] for r in inv.p['structure_page']['items']]==['2','4']


def test_missing_middle_is_reported_without_discarding_found_originals():
    m=matcher();del m.units[('d','2')];del m.stored_coordinates[('d','2')]
    out=ss.resolve(choose([interval(1,3)]),m,'d',['d'])
    assert out['unit_ids']==['1','3']
    assert out['membership_gaps']==[{'parent_unit_id':'p','unit':'호','n':2,'reason':'NO_STORED_MEMBER_IN_INTERVAL'}]
    page=sq.catalogue(m,['d'],document_id='d',structure_filter={'selection':out['selection']})
    assert page['lookup_status']=='NEEDS_SELECTION' and len(page['items'])==2
    assert page['failure']['code']=='INCOMPLETE_STRUCTURE_SET'


def test_oracle_children_are_scoped_by_document_and_parent():
    from semantic_runtime.oracle_query_matcher import Units,Coordinates
    m=matcher();calls=[]
    rows=[{'document_id':'d','unit_id':uid,'unit':node,'coordinate':m.stored_coordinates[('d',uid)].as_dict()}
          for (did,uid),node in m.units.items()]
    def page(kind,**filters):
        calls.append((kind,filters))
        assert kind=='native.unit' and filters['document_id']=='d'
        if 'owner_id' in filters:selected=[r for r in rows if r['unit']['parent']==filters['owner_id']]
        else:
            from semantic_runtime.oracle_dp_io import digest
            assert 'lookup_id' in filters,'selection must not fetch the whole remote document'
            selected=[r for r in rows if digest(['d',r['unit_id']])==filters['lookup_id']]
        return {'rows':selected,'next':None}
    request=S(sources=S(allowed={'d'}),records=S(page=page))
    old=ss.resolve(choose(exclude=[single(5)]),m,'d',['d'])
    m.coordinate_index=sq.coordinate_index(m)
    m.units=Units(request);m.stored_coordinates=Coordinates(m.units)
    new=ss.resolve(old['selection'],m,'d',['d'])
    assert new['unit_ids']==old['unit_ids'] and new['metadata_hash']==old['metadata_hash']
    assert any(filters.get('owner_id')=='p' for _,filters in calls)


def test_name_retry_preserves_full_selection_including_exclusions():
    from semantic_runtime.legal_agent import law_name_recovery as nr
    from semantic_runtime.navigation_match import norm
    m=matcher();m.documents['d']='가상 금융투자규정'
    chosen=choose([interval(1,3)],[single(2)],paragraph=99)
    page=sq.catalogue(m,['d'],document_id='d',structure_filter={'selection':chosen})
    recovered=nr.attach(page,m,['d'])['law_name_recovery']
    assert recovered['structure_filter']=={'selection':chosen}
    before=nr.retry_key(recovered,'d')
    altered=deepcopy(recovered);altered['structure_filter']['selection']['groups'][0]['exclude']=[]
    assert nr.retry_key(altered,'d')!=before


def test_coverage_uses_all_requested_blocks_not_ancestor_or_exact_labels(session):
    from semantic_runtime.legal_agent import evidence_inventory as ei
    native,_=session;s=investigation(native).s
    chosen=ss.resolve(choose([single(1)],article=1,dash=None,paragraph=1),s.matcher,'d',s.scope)
    def result(blocks):
        spans=ei.expected(s,'d',blocks)
        return ss.progress_from_spans(s,{chosen['hash']:chosen},[
            {'document_id':'d','acquired_spans':spans,'delivered_spans':spans}])[0]
    assert not result(['0','1'])['acquired_complete']  # ancestor introduction
    assert not result(['2'])['delivered_complete']  # own text omits the child 목
    assert result(['2','3'])['delivered_complete']


def test_old_no_index_path_reads_selected_units_and_reports_unread_children(session):
    from semantic_runtime.legal_agent.source_recall import SourceRecall
    from semantic_runtime.legal_agent import unit_selection as us
    native,_=session;s=investigation(native).s
    chosen=choose(exclude=[single(2)],article=1,dash=None,paragraph=1)
    question='모의승인규정 제1조 1항에서 2호 빼고 전부'
    change={'operation':'REPLACE','user_quote':question,'targets':[
        {'document':'모의승인규정','structure':None,'selection':chosen}]}
    qs.attach(s,qs.resolve(change,None,s.matcher,s.scope,question))
    s.matcher.unit_fulltext=None
    assert s.repo.VERSION!=6
    rec=SourceRecall(s).prepare()
    assert rec['unit_read_contract']=='unit-read-v1'
    assert all('4' not in r['offer']['block_ids'] for r in rec['unit_reads'])
    def invoke(system,data,schema,phase,timeout):
        return {'issues':['승인'],'choices':[{'id':row['id'],'scope':row['read_options'][0][0],
            'status':'ADOPT','reason':'현재 원문 채택'} for row in data['units']],
            'needs_search':False,'evidence_sufficient':True,'sufficiency_reason':'확보 원문으로 제한 설명'}
    out=us.select(question,rec,invoke,session=s,remaining_seconds=120,max_fulltext_chars=80000)
    assert out['selection_progress'][0]['remaining_unit_ids']==['2']
    assert any('원문 전체' in value for value in out['completion_limitations'])


def test_letter_ranges_and_inserted_article_numbers_use_stored_coordinates():
    m=matcher();parent=m.stored_coordinates[('d','1')]
    for n in range(1,4):
        uid='mok'+str(n)
        m.stored_coordinates[('d',uid)]=parent.append_part(LegalCoordinate('목',n))
        m.units[('d',uid)]={'parent':'1','coordinate_scope':'body','span':[2+n/10,2+(n+1)/10]}
    chosen=choose([interval('가','다')],[single('나')],unit='목')
    chosen['groups'][0]['parent_path'].append({'unit':'호','n':1})
    assert ss.resolve(chosen,m,'d',['d'])['unit_ids']==['mok1','mok3']
    chosen=choose([{'kind':'SINGLE','value':{'n':6,'dash':3}}],unit='조',root=True)
    assert ss.resolve(chosen,m,'d',['d'])['unit_ids']==['a']


def test_multiple_document_sets_keep_independent_exclusions():
    m=matcher();m.documents['e']='두번째규정'
    for (did,uid),row in list(m.units.items()):m.units[('e',uid)]=deepcopy(row)
    for (did,uid),row in list(m.stored_coordinates.items()):m.stored_coordinates[('e',uid)]=row
    question='모의규정 1~3호와 두번째규정 5호 빼고 전부'
    change={'operation':'REPLACE','user_quote':question,'targets':[
        {'document':'모의규정','structure':None,'selection':choose([interval(1,3)])},
        {'document':'두번째규정','structure':None,'selection':choose(exclude=[single(5)])}]}
    scope=qs.resolve(change,None,m,['d','e'],question)
    assert [r['unit_id'] for r in scope['targets'] if r['document_id']=='d']==['1','2','3']
    assert [r['unit_id'] for r in scope['targets'] if r['document_id']=='e']==['1','2','3','4','6','7']


def test_invalid_compact_selector_exhausts_one_repair_and_reuses_failure(session):
    from semantic_runtime.legal_agent import decision_projection as dp,completion_contracts as cc,output_contract as oc
    native,_=session;inv=investigation(native);inv.modern=True;inv.p['completion_contract']=cc.V8
    data,actions=inv.view();calls=[]
    def invoke(system,payload,schema,phase,timeout):
        calls.append(phase)
        option=next(o for o in payload['tool_options'] if o['choice']=='LOCATE' and o['scope']['document_id']=='d')
        return {'choice':'LOCATE','target':option['target'],'issue_id':'Q1','missing_need':'범위',
            'relation':'DIRECT','source_ref':None,'structure_filter':{'selection':{'coordinate_scope':'body','groups':[]}}}
    inv.invoke=invoke
    for _ in range(2):
        with pytest.raises((oc.OutputContractError,ValidationError)):
            dp.choose_read(inv,data,actions,'source-law-navigation-1')
    assert len(calls)==2
