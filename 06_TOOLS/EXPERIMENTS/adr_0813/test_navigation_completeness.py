"""First-planner location completeness and actual wire budget; no real model.

Known-defect contract probes. Freeze before execution; not legal holdout data.
"""
from copy import deepcopy
from dataclasses import replace
import json
from types import SimpleNamespace as NS

import pytest

from semantic_runtime.legal_agent import structure_query as sq
from semantic_runtime.legal_agent import source_selection
from semantic_runtime.legal_agent.output_contract import OutputContractError
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.legal_agent.repository import encoded, text_hash
from test_retrieval_boundaries import sample_matcher, node, seed_investigation
from test_navigation_length_recovery import adapter, work, SCHEMA
from test_legal_agent_double_harness import wire


def inventory_matcher():
    m=sample_matcher();m.tools=NS(terms={},definitions={})
    matches={'documents':[],'structures':[],'terms':[]}
    for i in range(5):
        did='law-'+str(i);m.documents[did]='가상문서 '+str(i)
        matches['documents'].append({'id':did,'name':m.documents[did]})
    for i in range(11):
        uid=str(i);node(m,'law',uid,'제'+str(i+1)+'조',scope='body',title='완전한 제목 '+str(i)+'가'*137)
        matches['structures'].append({'document_id':'law','unit_id':uid,'kind':'TITLE'})
    for i in range(7):
        ident='term-'+str(i);label='시험용어 '+str(i)
        m.tools.terms[ident]={'label':label}
        matches['terms'].append({'id':ident,'question_spans':[{'start':i,'end':i+1,'text':label}]})
    for i in range(19):
        m.tools.definitions[str(i)]={'id':str(i),'key':'시험용어 6','document_id':'law',
            'unit_id':str(i),'source_id':'source-'+str(i),'scope_status':'UNRESOLVED'}
    return m,matches


def test_first_planner_location_inventory_keeps_all_rows_and_complete_titles():
    m,matches=inventory_matcher()
    result=sq.navigation_context('가상문서 시험용어 6',m,set(m.documents),matches=matches)
    assert [len(result[k]) for k in ('documents','structures','terms','definitions')]==[5,11,7,19]
    assert [x['title'] for x in result['structures']]==[m.units[('law',str(i))]['title'] for i in range(11)]
    assert result['definition_candidates_ambiguous'] and not result['citation_eligible']
    reversed_matches={k:list(reversed(v)) for k,v in matches.items()}
    reversed_result=sq.navigation_context('가상문서 시험용어 6',m,set(m.documents),matches=reversed_matches)
    for key in ('documents','structures','terms','definitions'):
        assert sorted(map(encoded,result[key]))==sorted(map(encoded,reversed_result[key]))


def test_location_ambiguity_depends_on_competing_identities_not_row_count():
    m,matches=inventory_matcher()
    for d in m.tools.definitions.values():d.update(unit_id='same',source_id='same')
    result=sq.navigation_context('시험용어 6',m,set(m.documents),matches=matches)
    assert len(result['definitions'])==19 and not result['definition_candidates_ambiguous']
    m.tools.definitions['18']['document_id']='law-4'
    assert sq.navigation_context('시험용어 6',m,set(m.documents),matches=matches)['definition_candidates_ambiguous']
    scoped=sq.navigation_context('시험용어 6',m,{'law'},matches=matches)
    assert not scoped['documents'] and len(scoped['definitions'])==18
    assert not scoped['definition_candidates_ambiguous']


@pytest.mark.parametrize('route_kind',['coordinate','heading','definition'])
def test_unambiguous_exact_route_is_not_rejected_for_more_than_sixteen_sources(route_kind):
    m=sample_matcher();m.tools=NS(definitions={});headings=[];coordinates=[]
    for i in range(19):
        uid=str(i);heading='독립요건제목'+str(i);coordinate='제'+str(i+1)+'조'
        node(m,'law',uid,coordinate,scope='body',title=heading)
        m.structures.add(heading,{'document_id':'law','unit_id':uid,'kind':'TITLE'})
        headings.append(heading);coordinates.append(coordinate)
        m.tools.definitions[uid]={'id':uid,'key':'가상지표','document_id':'law','unit_id':uid,'source_id':'law:'+uid}
    query='가상규정 '+(' 및 '.join(coordinates) if route_kind=='coordinate' else
                      ' / '.join(headings) if route_kind=='heading' else "'가상지표'의 정의")
    result=sq.resolve(query,m,{'law'})
    assert result['status']=='MATCH' and len(result['pairs'])==len(result['source_ids'])==19
    assert set(result['source_ids'])==set(m.sources)
    assert sq.resolve(query,m,set())['status']=='MISS'


def initial_session(work):
    s,calls=adapter(work,['stop'])
    inv,_,_=seed_investigation(19)
    s.context=replace(s.context,request={**s.context.request,'question':'가상지표란 무엇인가?','use_llm':True})
    s.sources=inv.s;s.sources.context=s.context
    m=s.sources.matcher;m.documents={'law':'가상규정'};m.tools=s.sources.tools
    m.tools.terms={};m.stored_coordinates={}
    m.starts=lambda q,scope:{'documents':[],'structures':[],'terms':[]}
    s.navigation_context=None;s.bounded_started=False;s.structure_first_record=None
    s.source_recall_record=None;s.source_selection_record=None;s.request_route=None
    s.direct_answer=None;s.limitations=[]
    s.retrieval=lambda:{'complete':False,'limitations':deepcopy(s.limitations)}
    return s,calls


def link_reference(s,*,denied=False):
    # The reference witness is literal original text; no made-up relationship.
    d=s.sources.tools.definitions['0'];text=d['source_text'];locator='해당 원문'
    start=text.index(locator)
    target='outside' if denied else '18'
    if denied:
        s.sources.tools.sources[target]={'document_id':'other-version','unit_id':'elsewhere'}
    ref={'id':'reference-1','source_id':'0','document_id':'law','block_id':'0',
        'source_text':text,'source_text_sha256':text_hash(text),'mention_start':start,
        'mention_end':start+len(locator),'mention_text':locator,'locator':locator,
        'resolution':'EXACT_TEST_LOCATION','targets':[{'source_id':target,'unit_id':target}]}
    db=s.sources.tools.db
    db.execute('CREATE TABLE definition_reference(definition_id TEXT, reference_id TEXT)')
    db.execute('CREATE TABLE reference(id TEXT, json TEXT)')
    db.execute('INSERT INTO definition_reference VALUES(?,?)',('0','reference-1'))
    db.execute('INSERT INTO reference VALUES(?,?)',('reference-1',json.dumps(ref)))


@pytest.mark.parametrize('denied',[False,True])
def test_first_planner_gets_verified_all_definitions_and_scoped_reference_targets(work,denied):
    s,calls=initial_session(work);link_reference(s,denied=denied)
    hints=s.prepare_navigation_context()
    assert len(hints['definitions'])==hints['location_counts']['definitions']==19
    assert hints['location_inventory_complete'] and calls==[]
    linked=next(d for d in hints['definitions'] if d['definition_id']=='0')['connections'][0]
    if denied:
        assert linked['targets']==[] and linked['scope_limited']
    else:
        assert linked['targets'][0]['source_id']=='18'
    assert all(d['verification']=='EXACT_ORIGINAL_LOCATION' and not d['citation_eligible'] for d in hints['definitions'])
    assert s.prepare_navigation_context() is hints


@pytest.mark.parametrize('fault',['source_hash','source_version','reference_hash'])
def test_initial_definition_integrity_failure_is_not_a_partial_hint_success(work,fault):
    s,calls=initial_session(work);link_reference(s)
    if fault=='source_hash':s.sources.tools.definitions['18']['source_text_sha256']='wrong'
    if fault=='source_version':s.sources.tools.sources['18']['document_id']='other-version'
    if fault=='reference_hash':
        db=s.sources.tools.db;ref=json.loads(db.execute('SELECT json FROM reference').fetchone()[0])
        ref['source_text_sha256']='wrong';db.execute('UPDATE reference SET json=?',(json.dumps(ref),))
    with pytest.raises(ContractError):s.prepare_navigation_context()
    assert s.navigation_context is None and calls==[]


def test_initial_budget_measures_the_identical_complete_actual_wire_request(work):
    s,calls=initial_session(work);hints=s.prepare_navigation_context()
    s.profile['max_context_chars']=1000000
    result=s.structured('initial planner',{'question':s.context.request['question'],
        'navigation_context':hints},SCHEMA,'source-query-plan',60)
    assert result=={'ok':True} and len(calls)==1
    row=work.db.execute("SELECT payload_json FROM event WHERE kind='QUESTION_NAVIGATION_CONTEXT_BUDGET' ORDER BY seq DESC LIMIT 1").fetchone()
    receipt=json.loads(row[0])
    assert receipt['actual_request_chars']==len(encoded(calls[0]))
    assert receipt['status']=='WITHIN_BUDGET' and receipt['omitted_locations']==0
    sent=json.loads(calls[0]['messages'][1]['content'])['view']['navigation_context']
    assert sent==hints and work.budget()['model_reserved']==1


def test_oversized_first_input_reaches_existing_incomplete_handler_without_model_call(work):
    s,calls=initial_session(work);s.profile['max_context_chars']=1
    result=s.investigate()
    assert not result['complete'] and len(result['limitations'])==1
    assert 'context budget' in result['limitations'][0]
    assert calls==[] and work.budget()['model_reserved']==0
    records=[(r[0],json.loads(r[1])) for r in work.db.execute('SELECT kind,payload_json FROM event ORDER BY seq')]
    receipt=next(v for k,v in records if k=='QUESTION_NAVIGATION_CONTEXT_BUDGET')
    assert receipt['status']=='INCOMPLETE' and receipt['location_counts']['definitions']==19
    assert not receipt['source_absence_proven'] and receipt['omitted_locations']==0
    assert any(k=='BOUNDED_SOURCE_FAILURE' and v['type']=='BudgetExhausted' for k,v in records)
    assert len(s.navigation_context['definitions'])==19


def selection_call(work,value,*,legacy):
    s,calls=initial_session(work)
    s.profile['candidate_navigation']['investigation_control']=not legacy
    schema=source_selection.selection_schema(['C-A','C-B'],2)
    if legacy:
        item=schema['properties']['choices']['items']
        item['properties'].pop('status');item['required'].remove('status')
    def send(*,body,ticket):
        calls.append(deepcopy(body));return wire(deepcopy(value))
    s.gateway.transport.send_once=send
    return s,schema,calls


@pytest.mark.parametrize('legacy',[True,False])
def test_selection_validator_keeps_the_exact_declared_wire_and_return_contract(work,legacy):
    value={'issues':[],'choices':[{'id':'C-A','reason':'가상 원문 선택',**({} if legacy else {'status':'ADOPT'})}]}
    before=deepcopy(value);s,schema,calls=selection_call(work,value,legacy=legacy)
    result=s.structured('selection',{},schema,'source-triage',60)
    assert result==before and value==before and len(calls)==1
    fields=calls[0]['response_format']['json_schema']['schema']['properties']['choices']['items']['properties']
    assert ('status' in fields) is (not legacy)


def test_canonical_selection_still_rejects_missing_adoption_status(work):
    value={'issues':[],'choices':[{'id':'C-A','reason':'가상 원문 선택'}]}
    s,schema,calls=selection_call(work,value,legacy=False)
    with pytest.raises(OutputContractError):s.structured('selection',{},schema,'source-triage',60)
    assert 'status' not in value['choices'][0] and len(calls)<=2


@pytest.mark.parametrize('legacy',[True,False])
@pytest.mark.parametrize('fault',['duplicate','unknown'])
def test_legacy_normalization_cannot_bypass_closed_pool_or_unique_selection(work,legacy,fault):
    ids=['C-A','C-A'] if fault=='duplicate' else ['outside']
    value={'issues':[],'choices':[{'id':ident,'reason':'가상 선택',**({} if legacy else {'status':'ADOPT'})} for ident in ids]}
    before=deepcopy(value);s,schema,calls=selection_call(work,value,legacy=legacy)
    error = ProposalError if fault=='duplicate' else OutputContractError
    with pytest.raises(error):s.structured('selection',{},schema,'source-triage',60)
    assert value==before and len(calls)<=2
