"""General non-body original lookup and resumable full definition acquisition."""
from copy import deepcopy
from types import SimpleNamespace as NS
import sqlite3

import pytest
from lawrag.core.legal_coordinate import find_coordinates
from semantic_runtime.navigation_match import SurfaceIndex, norm
from semantic_runtime.legal_agent import structure_query as sq, definition_entry as de, request_repair as rr
from semantic_runtime.legal_agent.errors import ContractError, BudgetExhausted
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.contracts import digest


def sample_matcher():
    names=SurfaceIndex();names.add('가상규정','law')
    m=NS(document_names=names,title_keys={norm('가상규정')},documents={'law':'가상규정'},
         document_context={'law':{'document_title':'가상규정','document_role':'body'}},
         document_aliases={},structures=SurfaceIndex(),units={},stored_coordinates={},sources={})
    m._unit_sources=lambda did,uid:[sid for sid,s in m.sources.items() if s['document_id']==did and s['unit_id']==uid]
    return m


def node(m,did,uid,surface,*,parent=None,scope='annex',title='기준'):
    m.units[(did,uid)]={'surface':surface,'title':title,'parent':parent,
        'coordinate_scope':scope,'coordinate_binding':{'mode':'stored'}}
    parsed=find_coordinates(surface)
    if parsed:m.stored_coordinates[(did,uid)]=parsed[0].coordinate
    m.sources[did+':'+uid]={'document_id':did,'unit_id':uid}


@pytest.mark.parametrize('surface,query',[('별표 3','별표3'),('별지 7','별지 제7호'),('별표 10의2','별표10의2')])
def test_stored_non_body_coordinates_are_directly_readable(surface,query):
    m=sample_matcher();node(m,'law','annex',surface)
    route=sq.resolve('가상규정 '+query,m,{'law'})
    assert route['status']=='MATCH' and route['source_ids']==['law:annex']
    page=sq.catalogue(m,{'law'},queries=['가상규정 '+query])
    assert page['items'][0]['source_id']=='law:annex' and not page['citation_eligible']


def test_annex_branch_number_is_not_shortened():
    m=sample_matcher();node(m,'law','branch','별표 10의2')
    assert sq.resolve('가상규정 별표10',m,{'law'})['status']=='MISS'


@pytest.mark.parametrize('fault',['duplicate_coordinate','duplicate_original','denied','unresolved'])
def test_non_body_ambiguity_and_scope_fail_closed(fault):
    m=sample_matcher();node(m,'law','a','별표 3');scope={'law'}
    if fault=='duplicate_coordinate':node(m,'law','b','별표 3')
    if fault=='duplicate_original':m.sources['duplicate']={'document_id':'law','unit_id':'a'}
    if fault=='denied':scope=set()
    if fault=='unresolved':m.units[('law','a')]['coordinate_binding']['mode']='unresolved'
    result=sq.resolve('가상규정 별표3',m,scope)
    assert result['status']=='MISS' and not result['source_ids']


def attachment(m,ident='attachment',parent='가상규정'):
    title='[별표 3] 일반 기준';m.documents[ident]=title
    m.document_context[ident]={'document_title':title,'document_role':'annex','folder_names':[parent,'별표서식']}
    m.document_names.add(title,ident);m.title_keys.add(norm(title))
    node(m,ident,'prefix','원문',scope='unknown',title='서문')
    node(m,ident,'body','1.',scope='unknown',title='기준')


def test_detached_attachment_uses_parent_metadata_and_all_original_roots():
    m=sample_matcher();attachment(m)
    result=sq.resolve('가상규정 별표3',m,{'law','attachment'})
    assert result['status']=='MATCH'
    assert set(result['source_ids'])=={'attachment:prefix','attachment:body'}
    assert sq.resolve('가상규정 별표3',m,{'law'})['failure']['code']=='OUTSIDE_SCOPE'


def test_coordinates_inside_an_exact_attachment_title_are_not_separate_requests():
    m=sample_matcher();attachment(m)
    title='[별표 3] 일반 기준(제2조 및 제5조 관련)'
    m.document_context['attachment']['document_title']=title
    m.document_names.add(title,'attachment');m.title_keys.add(norm(title))
    result=sq.resolve(title,m,{'law','attachment'})
    assert set(result['source_ids'])=={'attachment:prefix','attachment:body'}
    assert sq.resolve('가상규정 별표3 및 제2조',m,{'law','attachment'})['status']=='MISS'


@pytest.mark.parametrize('fault',['different_parent','ambiguous_version','missing_original'])
def test_attachment_metadata_does_not_guess_parent_or_version(fault):
    m=sample_matcher();attachment(m,parent='다른규정' if fault=='different_parent' else '가상규정')
    if fault=='ambiguous_version':attachment(m,'older')
    if fault=='missing_original':m.sources['unbound']={'document_id':'attachment','unit_id':None}
    result=sq.resolve('가상규정 별표3',m,set(m.documents))
    assert result['status']=='MISS' and not result['source_ids']


def test_embedded_original_keeps_requested_document_version():
    m=sample_matcher();attachment(m);node(m,'law','same','별표 3')
    result=sq.resolve('가상규정 별표3',m,set(m.documents))
    assert result['source_ids']==['law:same']


def test_supplement_coordinates_preserve_branch_and_ambiguity():
    m=sample_matcher();node(m,'law','main','제2조',scope='body')
    node(m,'law','s1','부칙',scope='addendum',title='부칙 <2020.1.1>')
    node(m,'law','s1a','제2조',parent='s1',scope='addendum')
    assert sq.resolve('가상규정 부칙 제2조',m,{'law'})['source_ids']==['law:s1a']
    node(m,'law','s2','부칙',scope='addendum',title='부칙 <2025.1.1>')
    node(m,'law','s2a','제2조',parent='s2',scope='addendum')
    assert sq.resolve('가상규정 부칙 제2조',m,{'law'})['failure']['code']=='AMBIGUOUS_COORDINATE'
    assert sq.resolve('가상규정 부칙 <2025.1.1> 제2조',m,{'law'})['source_ids']==['law:s2a']


def test_missing_annex_is_not_proven_absence_from_complete_body_index():
    m=sample_matcher();node(m,'law','main','제2조',scope='body');m.units[('law','main')]['family']='kr_article'
    m.unit_fulltext=NS(manifest={'index_sha256':'frozen'})
    s=NS(matcher=m,scope={'law'},context=NS(query={'generation_id':'fixed'}))
    gap=rr.bind_gap({'issue_id':'Q','kind':'MISSING_SOURCE','missing_target':'가상규정 별표3'},s)
    assert gap['target_binding']['status']=='UNLOCATED'
    assert not gap['target_binding']['absence_proven']


def seed_investigation(count=19):
    text='가상지표란 해당 원문에서 정한 기준이다.';key='가상지표'
    definitions={};sources={};units={}
    for i in range(count):
        sid=str(i);uid=str(i)
        definitions[sid]={'id':sid,'key':key,'document_id':'law','source_id':sid,'unit_id':uid,
            'block_id':uid,'source_text':text,'source_text_sha256':text_hash(text),
            'source_artifact_sha256':'frozen','term_start':0,'term_end':len(key)}
        sources[sid]={'document_id':'law','document_name':'가상규정','source_artifact_sha256':'frozen',
            'unit_id':uid,'blocks':[{'block_id':uid}]}
        units[('law',uid)]={'surface':'제'+str(i+1)+'조'}
    events=[];calls=[]
    s=NS(tools=NS(definitions=definitions,sources=sources,db=sqlite3.connect(':memory:')),
         scope={'law'},store=NS(source=lambda did,bid:{'text':text,'unit_id':bid}),
         context=NS(request={'question':'가상지표란 무엇인가?'}),
         matcher=NS(units=units,_unit_sources=lambda did,uid:[uid],unit_fulltext=NS(manifest={'index_sha256':'frozen'})),
         repo=NS(event=lambda kind,value:events.append((kind,deepcopy(value)))),
         profile={'selection_time_reserve_seconds':1})
    inv=NS(s=s,policy={'definition_entry':True},p={'laws':{}},left=lambda:100,save=lambda:None)
    inv.add_laws=lambda rows:inv.p['laws'].update({de.token(s,'L',r['document_id']):r for r in rows})
    def execute(decision,data,actions):
        assert len(decision['targets'])==1
        target=decision['targets'][0];calls.append(actions[target]['identity']['unit_id'])
        identity=actions[target]['identity'];gid=identity['unit_id']
        inv.p['window_groups']=[gid]
        inv.p.setdefault('read_plans',{})[target]={'targets':[deepcopy(identity)],
            'status':'ACQUIRED','completed':{target:gid}}
        inv.p.setdefault('selected',{})[gid]={'source_id':identity['source_id'],
            'document_id':identity['document_id'],'complete':True}
    inv.execute_tool=execute
    return inv,calls,events


def test_definition_initial_acquisition_has_no_first_eight_cutoff_and_is_idempotent():
    inv,calls,events=seed_investigation(19);de.acquire_initial(inv)
    seed=inv.p['system_definition_seed']
    assert len(calls)==len(set(calls))==len(seed['completed'])==19
    assert seed['status']=='COMPLETE' and len(inv.p['window_groups'])==19
    de.acquire_initial(inv);assert len(calls)==19
    assert events[-1][1]['adopted'] is False and events[-1][1]['omitted_targets']==0


def test_definition_interruption_preserves_completed_targets_and_resume():
    inv,calls,_=seed_investigation(12);original=inv.execute_tool
    def failing(decision,data,actions):
        if len(calls)==4:raise OSError('interrupted original read')
        return original(decision,data,actions)
    inv.execute_tool=failing
    with pytest.raises(OSError):de.acquire_initial(inv)
    assert inv.p['system_definition_seed']['status']=='INTERRUPTED'
    assert len(inv.p['system_definition_seed']['completed'])==4
    inv.p=deepcopy(inv.p);inv.execute_tool=original;de.acquire_initial(inv)
    assert len(calls)==len(set(calls))==12
    assert inv.p['system_definition_seed']['status']=='COMPLETE'


def test_definition_budget_and_deadline_preserve_pending_without_false_completion():
    inv,calls,events=seed_investigation();original=inv.execute_tool;attempts=[]
    def bounded(decision,data,actions):
        attempts.append(decision['targets'][0])
        if len(calls)>=3:raise BudgetExhausted('same request budget exhausted')
        return original(decision,data,actions)
    inv.execute_tool=bounded;de.acquire_initial(inv)
    assert len(calls)==3 and inv.p['system_definition_seed']['status']=='PARTIAL'
    assert len(attempts)==4
    assert len(events[-1][1]['pending'])==16
    inv.left=lambda:0;de.acquire_initial(inv)
    assert len(calls)==3 and inv.p['system_definition_seed']['status']=='PARTIAL'


@pytest.mark.parametrize('fault',['no_receipt','partial_original','unfinished_plan'])
def test_definition_return_without_completed_original_is_not_success(fault):
    inv,_,_=seed_investigation(1);original=inv.execute_tool
    def incomplete(decision,data,actions):
        if fault=='no_receipt':return
        original(decision,data,actions)
        if fault=='partial_original':next(iter(inv.p['selected'].values()))['complete']=False
        if fault=='unfinished_plan':next(iter(inv.p['read_plans'].values()))['status']='INTERRUPTED'
    inv.execute_tool=incomplete
    with pytest.raises(ContractError):de.acquire_initial(inv)
    assert inv.p['system_definition_seed']['status']=='INTERRUPTED'
    assert not inv.p['system_definition_seed']['completed']


@pytest.mark.parametrize('fault',['question','target','false_complete'])
def test_definition_resume_rejects_changed_binding_or_false_completion(fault):
    inv,_,_=seed_investigation(3);de.acquire_initial(inv);seed=inv.p['system_definition_seed']
    if fault=='question':inv.s.context.request['question']='다른 질문'
    if fault=='target':seed['actions'][seed['targets'][0]]['identity']['unit_id']='wrong'
    if fault=='false_complete':seed['completed'].pop()
    with pytest.raises(ContractError):de.acquire_initial(inv)
