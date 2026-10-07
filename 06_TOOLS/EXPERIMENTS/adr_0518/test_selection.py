from pathlib import Path
import importlib.util,hashlib,json
import pytest
R=Path(__file__).resolve().parents[3]
P=R/'02_BACKEND/lawrag/research/candidates/adr_0518/selection/revisions/rev-003/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py'
spec=importlib.util.spec_from_file_location('selection',P);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
def record(n=3):
 ev=[]
 for i in range(n):
  text='모의법 근거 '+str(i)
  ev.append({'source_id':str(i),'document_id':'d','unit_id':str(i),'evidence_id':'e'+str(i),'metadata':{'document_name':'모의법','heading':f'제{i}조'},'spans':[{'block_id':'b','start_cp':0,'end_cp':len(text),'text':text}]})
 return {'read_complete':[str(i) for i in range(n)],'selected_for_read':[str(i) for i in range(n)],'initial_selected_ids':[str(i) for i in range(n)],'evidence':ev,'routes':{},'packets':[{'delivery_status':'PREPARED_NOT_SENT','evidence':ev}]}
def output(ids,removed=()):return {'issues':[],'choices':[{'id':f'C{int(x)+1:03d}','reason':'독립 쟁점'} for x in ids],'removed':[{'id':f'C{int(x)+1:03d}','reason':'C001 원문과 중복'} for x in removed]}
def test_more_than_five_necessary_sources_remain():
 r=record(8);out=s.select_sources('각각의 근거',r,lambda *a:output(range(8)),remaining_seconds=60)
 assert len(out['final_ids'])==8 and not out['removed_ids']
def test_review_removes_only_requested_ids_preserves_packet_bytes():
 r=record();before=s.digest(r);i=0
 def call(*args):
  nonlocal i;i+=1
  return output([0,2],[1] if i==1 else [])
 out=s.select_sources('근거',r,call,remaining_seconds=60)
 assert out['final_ids']==['0','2'] and out['removed_ids']==['1']
 assert s.digest(r)==before
 assert out['final_packets'][0]['evidence']==[r['evidence'][0],r['evidence'][2]]
 assert out['selection_history'][1]['discard_reasons']['1']
def test_unexplained_deletion_rejected():
 with pytest.raises(ValueError,match='every discarded'):s.select_sources('근거',record(),lambda *a:output([0]),remaining_seconds=60)
def test_source_gap_rejected():
 r=record();sp=r['evidence'][0]['spans'][0];sp['start_cp']=1;sp['end_cp']+=1
 with pytest.raises(ValueError,match='gap'):s.originals(r)
def test_partial_original_remains_verbatim():
 text='원문 검증 '*300;parts=s.excerpts(text,'검증',[],160)
 assert sum(len(p['text']) for p in parts)<=160 and all(text[p['start']:p['end']]==p['text'] for p in parts)
def with_relation():
 r=record();txt='제1조를 준용한다.';e=r['evidence'][0];e['spans']=[{'block_id':'b','start_cp':0,'end_cp':len(txt),'text':txt}]
 ref={'id':'r','source_id':'0','source_text':txt,'source_text_sha256':hashlib.sha256(txt.encode()).hexdigest(),'target_source_ids':['1'],'reference_role':'APPLIES_MUTATIS_MUTANDIS','resolution':'EXACT','canonical_approval':False}
 r['reference_witnesses']={'r':ref};r['routes']={'1':[{'kind':'reference','anchor':'0','reference_id':'r','direction':'outgoing','witness_sha256':ref['source_text_sha256']}]};return r

def test_verified_relation_direction_and_unselected_endpoint_excluded():
 r=with_relation();sources=s.originals(r);edges=s.verified_relations(r,sources)
 assert edges[0]['from_source_id']=='0' and edges[0]['to_source_id']=='1'
 out=s.source_appendix(['0','1'],sources,{},edges)
 assert len(out['relations'])==1 and '준용 문구' in out['markdown'] and '적용성 미확정' in out['markdown']
 assert s.source_appendix(['0'],sources,{},edges)['relations']==[]
def test_corrupt_witness_rejected():
 r=with_relation();r['reference_witnesses']['r']['source_text_sha256']='bad'
 with pytest.raises(ValueError,match='witness hash'):s.verified_relations(r,s.originals(r))
def test_ambiguous_relation_not_promoted():
 r=with_relation();r['reference_witnesses']['r']['resolution']='AMBIGUOUS'
 assert s.verified_relations(r,s.originals(r))==[]
def test_render_source_labels_escape_markup():
 r=record();sources=s.originals(r);sources['0']['document_name']='<script>*x*'
 text=s.source_appendix(['0'],sources,{},[])['markdown']
 assert '<script>' not in text and '\\*x\\*' in text
def test_budget_failure_not_full_pool_fallback():
 with pytest.raises(TimeoutError):s.select_sources('근거',record(),lambda *a:None,remaining_seconds=0)
