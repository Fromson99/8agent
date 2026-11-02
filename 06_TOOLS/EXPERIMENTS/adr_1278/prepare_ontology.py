"""Explicit synthetic input authoring through current compile/review/publication APIs."""
from common import *
import sqlite3,os
from copy import deepcopy
C=ROOT/read(DES/'candidate-path.json')['snapshot']
sys.path[:0]=[str(ROOT/'02_BACKEND'),str(ROOT/'05_TESTS'),str(ROOT/'05_TESTS/CONTRACTS')]
import pytest,conftest
import test_domain_profile_workflow as fixture
old=fixture.normalized_output
def normalized(context):
 v=old(context)
 for row in v['observations']:
  for k in ('reason','purpose'):
   assert row.pop(k)['state']=='NOT_RECORDED';row['recorded_'+k]=None
 v['coverage']={r['pointer']:{k:x for k,x in r.items() if k!='pointer'} for r in v['coverage']}
 def walk(x):
  if isinstance(x,dict):
   if set(x)=={'payload_hash','pointer','start','end','quote'}:return {'pointer':x['pointer'],'quote':x['quote'],'occurrence':0}
   return {k:walk(y) for k,y in x.items()}
  if isinstance(x,list):return list(map(walk,x))
  return x
 return walk(v)
fixture.normalized_output=normalized
base=ART/'ontology';base.mkdir(exist_ok=False);generator=fixture.env.__wrapped__(base);e=next(generator)
data=ROOT/read(DES/'source.json')['data_path'];did='synthetic-whatif-v1'
from semantic_runtime.legal_agent.ontology_compiler import content_hash
from semantic_runtime.ontology_work.accumulation import observation_rows
with sqlite3.connect(data/'store.sqlite') as db:
 version=db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()[0]
 text='\n'.join(r[0] for r in db.execute('SELECT text FROM source_block WHERE document_id=? AND unit_id=? ORDER BY CAST(block_id AS INTEGER)',(did,'0')))
assert text.startswith('제1조')
e.source.update(id='S1',anchor={'document_id':did,'version':version,'unit_id':'0','content_sha256':content_hash(text),'label':'가정검증규정 제1조'},text=text)
e.w.document_ids=frozenset([did]);e.w.source_reader=lambda anchor:text if anchor==e.source['anchor'] else None
obs=fixture.add_observation(e,payload={'opinion':text,'origin':'PREDECLARED_SYNTHETIC_INPUT_NOT_MODEL_GENERATION'})
n=e.w.load(obs['bundle_id'])['normalized'];oid=next(iter(observation_rows([n])));profile=e.w.selected_profile(e.profile_id,e.profile_work_hash)['effective']
def node(key,kind,label):
 required=next(r['required_review_slots'] for r in profile['node_types'] if r['kind']==kind)
 slots={s:{'state':'NOT_RECORDED','value':None} for s in required};slots['statement']={'state':'PRESENT','value':label}
 return {'id':key,'kind':kind,'text':label,'slots':slots,'basis':[{'source':'S1','quote':text}],'observation_refs':[oid],'glossary_refs':[]}
graph={'nodes':[node('N1','EFFECT','일반 작업은 비용 요건과 서면 승인 요건을 모두 충족한 경우에만 시작할 수 있다.'),node('N2','CONDITION','1건의 작업 총액 cost가 1000000원 이하이다.'),node('N3','CONDITION','담당자의 서면 승인을 받았다.')],
 'edges':[{'id':'E'+str(i),'type':'REQUIRES_CONDITION','from':'N1','to':to,'basis':[{'source':'S1','quote':text}]} for i,to in enumerate(['N2','N3'],1)],
 'purposes':[{'id':'P1','purpose':'required-action','roots':['N1'],'title':'일반 작업 시작 요건'}],'unused_nodes':[],'unresolved':[]}
p={'graph':graph,'comparisons':[{'observation_ref':oid,'relation':'NEW','verdict':'SUPPORTED','reason':'합성 제1조의 금액 및 승인 두 요건을 그대로 등록한다. 긴급 예외는 별도 제2조 원문으로 검토한다.','basis':[{'source':'S1','quote':text}],'node_ids':['N1','N2','N3']}],'removed_nodes':[]}
draft=fixture.save(e,obs,p)
field=lambda kind,typ,unit,concept,baseline:{'kind':kind,'type':typ,'unit':unit,'concept':concept,'period':'작업1건','as_of':'2026-11-02','baseline':baseline}
spec={'fields':{'cost':field('FACT','money','KRW','작업 총액',None),'limit':field('RULE','money','KRW','허용 한도',{'type':'money','unit':'KRW','value':'1000000'}),'approved':field('FACT','boolean','','담당자 서면 승인',None)},
 'rules':[{'node_id':'N2','expression':{'op':'lte','args':[{'field':'cost'},{'field':'limit'}]},'source_ids':['S1'],'rounding':'EXACT_ONLY'}, {'node_id':'N3','expression':{'field':'approved'},'source_ids':['S1'],'rounding':'EXACT_ONLY'}]}
draft=e.w.save_evaluation_spec(draft['bundle_id'],draft['revision'],draft['work_hash'],spec)
stage=fixture.approve_stage(e,draft);receipt=e.w.verify_publication(stage['publication_id']);e.w.activate_publication(stage['publication_id'],0,receipt)
put(DES/'ontology-input.json',{'authorship':'predeclared synthetic input, fixture normalizer only during preparation; live model outputs never changed','source':e.source,'graph':graph,'evaluation_spec':spec,'publication':stage,'verification':receipt,'package':e.w.preview(draft['bundle_id'])})
put(DES/'ontology-config.json',{'version':'ontology-connection-v1','environment':'local','database':{'kind':'sqlite-local','path':str(base/'work.sqlite')}})
try:next(generator)
except StopIteration:pass
print('isolated ontology published',stage['publication_id'])
