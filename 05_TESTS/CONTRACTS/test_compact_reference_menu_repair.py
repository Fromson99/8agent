"""Regression for ADR0622 real menu omission and invalid id/scope pair."""
import pytest
from test_batch_reference_navigation import connected, initial, decision, rel
from semantic_runtime.legal_agent.source_selection import select_sources


def test_compact_menu_has_fixed_columns_and_exact_scope_ids(connected):
    s,_=connected;rec,sid=initial(s)
    groups,_,_,_=rel.catalog(s,[sid],{},set())
    card=rel.menu(groups[0],'R1')
    assert all(isinstance(row,list) and len(row)==6 for row in card['read_options'])
    assert {row[0] for row in card['read_options']}==set(groups[0]['offers'])
    assert card['connections'][0]['witness_sha256']


def test_omitted_group_is_summarized_and_cannot_be_reported_complete(connected,monkeypatch):
    s,_=connected;rec,sid=initial(s)
    monkeypatch.setitem(rel.LIMITS,'relation_context_chars',1)
    def forbidden(*a):raise AssertionError('oversized detailed batch must not call model')
    out=rel.navigate('예외',s,{'U1':rec['unit_reads'][0]},forbidden,
        read_state={'count':0,'chars':0},seconds_left=lambda:120,max_context_chars=80000)
    data=out['batches'][0]['data']
    assert out['pending'] and data['omitted_groups']==1
    assert data['all_group_summaries'][0]['target']['document_id']=='detail'
    assert not data['all_group_summaries'][0]['read_options_presented']


def test_one_invalid_pair_is_redecided_before_any_chosen_read(connected):
    s,_=connected;rec,sid=initial(s);phases=[]
    def invoke(system,data,schema,phase,timeout):
        phases.append(phase)
        if phase=='source-unit-triage':return {'issues':[], 'needs_search':False, 'choices':[{'id':data['units'][0]['id'],'scope':'exact:999','reason':'잘못된 쌍'}]}
        if phase=='source-unit-choice-repair':
            assert data['rejected_decision']['choices'][0]['scope']=='exact:999'
            return {'issues':[],'needs_search':False,'choices':[{'id':data['units'][0]['id'],'scope':'exact:2','reason':'제시된 행의 실제 원문 범위를 다시 확인'}]}
        if phase.startswith('source-reference-batch'):return decision(data)
        return {'issues':[],'choices':[],'needs_search':False}
    out=select_sources('승인',rec,invoke,remaining_seconds=120,session=s)
    assert out['status']=='complete' and len(out['choice_repairs'])==1 and len(out['rejected_decisions'])==1
    assert out['read_scopes'][0]['offer']['unit_id']=='2' and len(phases)==4


def test_invalid_redecision_stops_without_recursive_repairs(connected):
    s,_=connected;rec,sid=initial(s);phases=[]
    def invoke(system,data,schema,phase,timeout):
        phases.append(phase)
        return {'issues':[],'needs_search':False,'choices':[{'id':data['units'][0]['id'],'scope':'exact:999','reason':'잘못된 쌍'}]}
    with pytest.raises(ValueError,match='scope'):
        select_sources('승인',rec,invoke,remaining_seconds=120,session=s)
    assert phases==['source-unit-triage','source-unit-choice-repair']
