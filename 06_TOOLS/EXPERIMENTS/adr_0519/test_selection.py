from pathlib import Path
import importlib.util,hashlib
import pytest
R=Path(__file__).resolve().parents[3]
P=R/'02_BACKEND/lawrag/research/candidates/adr_0519/selection/revisions/rev-002/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py'
spec=importlib.util.spec_from_file_location('s',P);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
def record():
 ev=[]
 for sid in ['A','B','C','D','E','F']:
  text='모의 원문 '+sid
  ev.append({'source_id':sid,'document_id':'d','unit_id':ord(sid),'evidence_id':'e'+sid,'metadata':{'document_name':'모의법','heading':sid},'spans':[{'block_id':sid,'start_cp':0,'end_cp':len(text),'text':text}]})
 routes={'A':[{'kind':'fulltext','query':'쟁점','rank':1}], 'B':[{'kind':'fulltext','query':'다른 쟁점','rank':2}],
  'C':[{'kind':'reference','anchor':'A','direction':'outgoing','reference_id':'ac'}],
  'D':[{'kind':'reference','anchor':'A','direction':'outgoing','reference_id':'ad'},{'kind':'reference','anchor':'B','direction':'outgoing','reference_id':'bd'}],
  'E':[{'kind':'reference','anchor':'B','direction':'incoming','reference_id':'be'}],
  'F':[{'kind':'ambiguous_coordinate_candidate','anchor':'C','reference_id':'cf'}]}
 return {'read_complete':[e['source_id'] for e in ev],'selected_for_read':[e['source_id'] for e in ev],'evidence':ev,'routes':routes,'packets':[{'delivery_status':'PREPARED_NOT_SENT','evidence':ev}]}
def choose(*args):return {'issues':[],'choices':[{'id':'R001','reason':'질문 시작점'}]}
def test_selected_root_keeps_children_and_recursive_descendants():
 r=record();o=s.select_sources('쟁점',r,choose,remaining_seconds=60)
 assert o['selected_root_ids']==['A'];assert set(o['final_ids'])=={'A','C','D','F'}
 assert set(o['retained_linked_ids'])=={'C','D','F'}
def test_rejected_root_removes_exclusive_branch_but_keeps_shared():
 r=record();o=s.select_sources('쟁점',r,choose,remaining_seconds=60)
 assert 'B' not in o['final_ids'] and 'E' not in o['final_ids']
 assert o['selected_root_owners']['D']==['A']
def test_two_selected_roots_share_original_without_duplicate():
 r=record();b=s.root_bundles(r,['A','B'])
 assert b['selected_root_owners']['D']==['A','B'] and len(b['reachable_acquired_ids'])==6
def test_no_selected_roots_means_no_connected_sources():
 r=record();o=s.select_sources('무관',r,lambda *a:{'issues':[],'choices':[]},remaining_seconds=60)
 assert o['final_ids']==[]
def test_cycle_terminates_and_does_not_duplicate():
 r=record();r['routes']['A'].append({'kind':'reference','anchor':'F'})
 assert set(s.root_bundles(r,['A'])['reachable_acquired_ids'])=={'A','C','D','F'}
def test_dual_role_rejected_root_survives_as_child_of_selected_root():
 r=record();r['routes']['B'].append({'kind':'reference','anchor':'A'})
 o=s.select_sources('쟁점',r,choose,remaining_seconds=60)
 assert 'B' in o['root_rejected_but_protected_ids'] and 'E' in o['final_ids']
def test_selector_only_receives_direct_root_choices():
 seen=[]
 def invoke(system,data,schema,*args):
  seen.extend(data['root_candidates']);assert schema['properties']['choices']['items']['properties']['id']['enum']==['R001','R002'];return choose()
 s.select_sources('쟁점',record(),invoke,remaining_seconds=60)
 assert [x['article'] for x in seen]==['A','B']
def test_protocol_failure_preserves_pool_and_marks_degraded():
 r=record()
 def bad(*args):raise ValueError('bad model JSON')
 o=s.select_sources('쟁점',r,bad,remaining_seconds=60)
 assert o['final_ids']==r['read_complete'] and o['status']=='DEGRADED_PRESERVED' and o['error']
def test_out_of_pool_model_id_cannot_delete_sources():
 r=record();o=s.select_sources('쟁점',r,lambda *a:{'issues':[],'choices':[{'id':'X','reason':'bad'}]},remaining_seconds=60)
 assert o['error'] and o['final_ids']==r['read_complete']
def test_exact_source_packets_unchanged():
 r=record();before=s.digest(r);o=s.select_sources('쟁점',r,choose,remaining_seconds=60)
 assert s.digest(r)==before
 assert o['final_packets'][0]['evidence']==[e for e in r['evidence'] if e['source_id'] in o['final_ids']]
def test_unacquired_targets_are_not_claimed_as_read():
 r=record();r['routes']['Z']=[{'kind':'reference','anchor':'C'}]
 o=s.select_sources('쟁점',r,choose,remaining_seconds=60)
 assert 'Z' in o['reachable_unacquired_ids'] and 'Z' not in o['final_ids']
def test_reference_witness_hash_checked():
 r=record();text=r['evidence'][0]['spans'][0]['text']
 r['reference_witnesses']={'ac':{'id':'ac','source_id':'A','source_text':text,'source_text_sha256':'bad','target_source_ids':['C'],'resolution':'EXACT'}}
 with pytest.raises(ValueError,match='witness'):s.verified_relations(r,s.originals(r))
