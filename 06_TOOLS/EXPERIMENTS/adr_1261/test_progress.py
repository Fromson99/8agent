from pathlib import Path
from contextlib import contextmanager
import json,copy,random,hashlib
import pytest
from semantic_runtime.oracle_agent_records import AgentRecords,sha
from semantic_runtime.oracle_dp_io import canonical,DPError
from semantic_runtime import oracle_progress_body as progress
# Reuse the existing isolated BODY SQL contract; no network or physical DB.
import sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/EXPERIMENTS/adr_1246'))
from test_safety import MemorySQL

def row(value, table='stage_progress'):
 return canonical({'table':table,'columns':['goal','input_hash','payload','hash'],'values':[['text','goal'],['text','binding'],['text',canonical(value)],['text','f'*64]],'key':[['integer','1']],'rowid':True}).encode()
def sample(seed=3):
 rnd=random.Random(seed)
 return {'sources':[{'id':str(i),'text':rnd.randbytes(900).hex(),'coordinates':[i,0,900],'claim':None} for i in range(180)],'ontology':{'anchors':['A1'],'gaps':['unresolved']},'budget':{'model_reserved':3,'deadline':1234567890},'frame':0}

def test_all_historical_revisions_exact_and_fresh_cache():
 sql=MemorySQL();store=AgentRecords(sql,namespace='history');data=sample();original=[]
 for n in range(12):
  data['frame']=n;data['sources'][n]['claim']='proposal'+str(n);raw=row(data);original.append(raw);store.put_bodies([raw])
 fresh=AgentRecords(sql,namespace='history');got=fresh.bodies(sha(v) for v in original)
 assert all(got[sha(v)]==v for v in original)
 assert all(sql.parts[(sha(v),0)]['layout_version']==4 for v in original)
 assert all(len(canonical(v).encode())<=4000 for v in sql.parts.values())
 assert len(sql.parts)<len(original)*100

@pytest.mark.parametrize('table',['other','stage_progress'])
def test_small_and_other_rows_keep_layout3(table):
 raw=row({'x':'small'} if table=='stage_progress' else sample(),table);sql=MemorySQL();r=AgentRecords(sql,namespace='plain');r.put_bodies([raw]);assert sql.parts[(sha(raw),0)]['layout_version']==3;assert AgentRecords(sql,namespace='plain').body(sha(raw))==raw

@pytest.mark.parametrize('layout',[2,3])
def test_existing_legacy_progress_never_rewritten(layout):
 raw=row(sample());parts,manifest=AgentRecords._encode_body(raw,layout=layout);sql=MemorySQL()
 for p in [*parts,manifest]:sql.parts[(p['hash'],p['seq'])]=p['json']
 before=copy.deepcopy(sql.parts);r=AgentRecords(sql,namespace='legacy');r.put_bodies([raw]);assert sql.parts==before;assert r.body(sha(raw))==raw

@pytest.mark.parametrize('layout',[2,3])
def test_partial_legacy_progress_finishes_original_format(layout):
 raw=row(sample());parts,manifest=AgentRecords._encode_body(raw,layout=layout);sql=MemorySQL();sql.parts[(sha(raw),1)]=parts[0]['json'];r=AgentRecords(sql,namespace='legacy-partial');r.put_bodies([raw]);assert r.body(sha(raw))==raw;assert sql.parts[(sha(raw),0)]['layout_version']==layout

def test_partial_v4_data_upload_finishes_without_duplicate_parts():
 raw=row(sample());sql=MemorySQL();r=AgentRecords(sql,namespace='partial');r.put_bodies([raw]);full=copy.deepcopy(sql.parts)
 # Every leaf is complete; root data upload was interrupted before its manifest.
 sql.parts.pop((sha(raw),0));r=AgentRecords(sql,namespace='partial');r.put_bodies([raw]);assert sql.parts==full;assert r.body(sha(raw))==raw

def test_leaf_manifests_precede_root_publication():
 raw=row(sample());sql=MemorySQL();old=sql.mutate
 def capture(text,binds):
  b={k:v for k,v,*_ in binds}
  for p in json.loads(b['parts']):
   if p['seq']==0 and p['json']['layout_version']==4:
    assert all((h,0) in sql.parts for h in progress.plan({sha(raw):raw})[0] if h!=sha(raw))
  old(text,binds)
 sql.mutate=capture;AgentRecords(sql,namespace='order').put_bodies([raw])

@pytest.mark.parametrize('failure',['missing_leaf','corrupt_leaf','recipe_hash','raw_length','cycle'])
def test_corrupt_reference_is_rejected(failure):
 raw=row(sample());sql=MemorySQL();AgentRecords(sql,namespace='bad').put_bodies([raw]);root=sha(raw);m=sql.parts[(root,0)];_,recipes=progress.plan({root:raw});refs=json.loads(recipes[root])
 if failure=='missing_leaf':sql.parts.pop((refs[0],0))
 elif failure=='corrupt_leaf':sql.parts[(refs[0],1)]['data_base64']='YQ=='
 elif failure=='recipe_hash':m['recipe_sha256']='0'*64
 elif failure=='raw_length':m['total_bytes']+=1
 else:
  recipe=canonical([root,root]).encode();parts,manifest=AgentRecords._encode_body(recipe)
  for k in [k for k in sql.parts if k[0]==root]:del sql.parts[k]
  for p in parts:p['hash']=root;p['json']['layout_version']=4;sql.parts[(root,p['seq'])]=p['json']
  mm=manifest['json'];mm.update(layout_version=4,body_sha256=root,total_bytes=len(raw),recipe_bytes=len(recipe),recipe_sha256=sha(recipe));sql.parts[(root,0)]=mm
 with pytest.raises((DPError,ValueError)):AgentRecords(sql,namespace='bad').body(root)

def test_missing_namespace_cannot_recover_from_global_cache():
 raw=row(sample());sql=MemorySQL();AgentRecords(sql,namespace='first').put_bodies([raw]);other=MemorySQL()
 with pytest.raises(DPError):AgentRecords(other,namespace='second').body(sha(raw))

def test_same_writer_no_reupload_and_logical_sha_unchanged():
 raw=row(sample());sql=MemorySQL();store=AgentRecords(sql,namespace='same');store.put_bodies([raw]);writes=sql.writes;store.put_bodies([raw]);assert sql.writes==writes;assert sha(store.body(sha(raw)))==sha(raw)
