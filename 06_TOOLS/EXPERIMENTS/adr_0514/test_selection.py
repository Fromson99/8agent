"""Synthetic provenance and packet contracts; no benchmark/gold input."""
from pathlib import Path
import importlib.util
import pytest

R=Path(__file__).resolve().parents[3]
P=R/'02_BACKEND/lawrag/research/candidates/adr_0514/selection/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py'
spec=importlib.util.spec_from_file_location('selection_contract',P);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def record():
    evidence=[]
    for i in range(3):
        text='모의법의 승인 대상과 예외 조항 '+str(i)
        evidence.append({'source_id':str(i),'document_id':'d','unit_id':str(i),'evidence_id':'e'+str(i),
            'metadata':{'document_name':'모의법','heading':'제'+str(i)+'조'},
            'spans':[{'block_id':'b','start_cp':0,'end_cp':len(text),'text':text}]})
    return {'read_complete':['0','1','2'],'selected_for_read':['0','1','2'],'evidence':evidence,
        'routes':{'0':[{'kind':'fulltext','query':'승인 대상','rank':1,'branch':b} for b in ['global','scoped']],
          '1':[{'kind':'reference','anchor':'0','reference_id':'ref1','direction':'outgoing','resolution':'EXACT','branch':b} for b in ['global','scoped']],
          '2':[{'kind':'ambiguous_coordinate_candidate','anchor':'1','reference_id':'ref2','canonical_approval':False}]},
        'packets':[{'delivery_status':'PREPARED_NOT_SENT','evidence':evidence}]}


def test_branch_repeats_do_not_become_independent_paths():
    r=record();sources=s.originals(r);q,p=s.provenance(r,sources,{'0':'C001','1':'C002','2':'C003'})
    assert p['0']['raw_events']==2 and p['0']['distinct_queries']==1
    assert len(p['0']['direct'])==1
    assert p['1']['distinct_edges']==1 and p['1']['links'][0]['root_queries']==['Q1']
    assert p['2']['links'][0]['canonical_approval'] is False


def test_source_reassembly_rejects_gap():
    r=record();r['evidence'][0]['spans'][0]['start_cp']=1;r['evidence'][0]['spans'][0]['end_cp']+=1
    with pytest.raises(ValueError,match='gap'):s.originals(r)


def test_source_reassembly_rejects_conflicting_overlap():
    r=record();r['evidence'][0]['spans'].append({'block_id':'b','start_cp':0,'end_cp':2,'text':'오류'})
    with pytest.raises(ValueError,match='conflict'):s.originals(r)


def test_excerpts_are_exact_and_bounded():
    text='가나다라 '*200+'승인 예외'*40
    slices=s.excerpts(text,'승인 예외',['허가'],420)
    assert sum(len(x['text']) for x in slices)<=420
    assert all(text[x['start']:x['end']]==x['text'] for x in slices)


@pytest.mark.parametrize('choices', [['X'],['a','a'],['a','b','c']])
def test_closed_ids_duplicates_and_budget(choices):
    with pytest.raises(ValueError):s.checked_choices({'choices':[{'id':x} for x in choices]},['a','b'],2)


def test_two_turn_recovery_preserves_first_and_original_pool():
    r=record();before=s.digest(r);calls=[]
    def invoke(system,data,schema,phase,timeout):
        calls.append((data,phase))
        return {'issues':['승인 예외'],'choices':[{'id':'C001' if len(calls)==1 else 'C002','reason':'명시 준용 경로'}],'remaining_gap':''}
    result=s.select_sources('승인 대상은?',r,invoke,remaining_seconds=60)
    assert result['first_ids']==['0'] and result['recovered_ids']==['1'] and result['final_ids']==['0','1']
    assert s.digest(r)==before and result['deferred'][0]['recoverable']
    assert [e['source_id'] for p in result['final_packets'] for e in p['evidence']]==['0','1']
    assert all(p['delivery_status']=='PREPARED_NOT_SENT' for p in result['final_packets'])
    assert calls[1][0]['selected_original_excerpts'] and calls[1][0]['deferred_candidates']


def test_timeout_does_not_silently_return_all_candidates():
    with pytest.raises(TimeoutError):s.select_sources('승인',record(),lambda *args:None,remaining_seconds=0)
