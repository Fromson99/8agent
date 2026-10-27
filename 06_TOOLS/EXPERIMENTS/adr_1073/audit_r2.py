"""Frozen finite SQL equivalence census; no real data, provider or timings claim."""
from pathlib import Path
from types import SimpleNamespace as S
from itertools import product
from copy import deepcopy
import contextlib,hashlib,importlib.util,io,json,os,resource,sqlite3,sys,tempfile,time,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification';D=A/'artifacts/design-r2'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as out:json.dump(v,out,ensure_ascii=False,indent=2);out.write('\n')
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def database(shared,dstate,rstate,endpoint,duplicates,reverse):
 from semantic_runtime.reference_build import shared_reference_schema
 db=sqlite3.connect(':memory:');db.executescript('''
 CREATE TABLE source(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
 CREATE TABLE definition(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
 CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);
 CREATE TABLE reference_end(reference_id TEXT,source_id TEXT);
 CREATE TABLE definition_reference(definition_id TEXT,reference_id TEXT);
 CREATE INDEX link_ids ON definition_reference(definition_id,reference_id);
 ''')
 if shared:shared_reference_schema(db)
 db.executemany('INSERT INTO source VALUES(?,?,?)',[('s-visible','visible','{}'),('s-hidden','hidden','{}')])
 did=None if dstate=='null' else 'D';rid=None if rstate=='null' else 'R'
 definitions=[('D-other','visible','{}')]
 if dstate!='missing':definitions.append((did,'hidden' if dstate=='hidden' else 'visible','{}'))
 references=[('R-other','visible')]
 if rstate!='missing':references.append((rid,'hidden' if rstate=='hidden' else 'visible'))
 if reverse:definitions.reverse();references.reverse()
 db.executemany('INSERT INTO definition VALUES(?,?,?)',definitions)
 for ident,doc in references:
  db.execute('INSERT INTO reference VALUES(?,?,?)',(ident,doc,json.dumps({'id':ident,'source_text':'synthetic witness','source_text_sha256':'witness'})))
 if endpoint!='none':db.execute('INSERT INTO reference_end VALUES(?,?)',(rid,'s-'+endpoint))
 links=[('D-other','R-other')]+[(did,rid)]*duplicates
 if reverse:links.reverse()
 db.executemany('INSERT INTO definition_reference VALUES(?,?)',links);db.commit();return db
def main_snapshot(db):
 schema=db.execute("SELECT type,name,sql FROM main.sqlite_master ORDER BY type,name").fetchall()
 rows={name:db.execute('SELECT * FROM main."'+name.replace('"','""')+'" ORDER BY rowid').fetchall()
       for kind,name,sql in schema if kind=='table' and not name.startswith('sqlite_')}
 return schema,rows
def selected(module,tmp):
 from semantic_runtime.contracts import sha as digest_file
 module.CODE_ROOT=tmp/'no-code-selection'
 g=tmp/'generation';g.mkdir(exist_ok=True);manifest={'generation_id':'sql-main-synthetic','store_sha256':'synthetic'}
 (g/'manifest.json').write_text(json.dumps(manifest))
 p=module.selection_path(g);p.parent.mkdir(exist_ok=True)
 p.write_text(json.dumps({'schema_version':module.VERSION,**manifest,'manifest_sha256':digest_file(g/'manifest.json'),'excluded':[{'document_id':'hidden','source_artifact_sha256':'synthetic'}]}))
 return module.Selection(g,manifest)
def outcome(fn,s,m):
 try:return {'type':'success','value':fn(s,m)}
 except Exception as e:return {'type':type(e).__name__,'message':str(e)}
def state(s,m):return deepcopy((s.tools.definitions,s.tools.sources,s.scope,s.matcher.units,m))
def mutate(s,m,refs,fault,shared):
 from semantic_runtime.legal_agent.repository import text_hash
 d=s.tools.definitions['D1'];db=s.tools.db;ref=deepcopy(refs[0]);change_ref=False
 if fault=='normal':pass
 elif fault=='source_text':d['source_text']='different'
 elif fault=='source_hash':d['source_text_sha256']='wrong'
 elif fault=='artifact_hash':d['source_artifact_sha256']='wrong'
 elif fault=='original_unit':s.store.source=lambda did,bid:{'text':'용어는 제2조를 따른다.','unit_id':'other'}
 elif fault=='definition_block':d['block_id']='other'
 elif fault=='term_start_type':d['term_start']=False
 elif fault=='term_bounds':d['term_end']=999
 elif fault=='term_label':d['label']='다름'
 elif fault=='source_acl':s.scope.remove('DOC')
 elif fault=='source_unit':s.matcher.units.pop(('DOC','U1'))
 elif fault=='orphan_reference':db.execute('INSERT INTO definition_reference VALUES(?,?)',('D1','MISSING'))
 elif fault=='null_reference':
  if shared:db.execute("UPDATE reference_payload SET json='null' WHERE id='RB'")
  else:db.execute("UPDATE reference SET json=NULL WHERE id='RB'")
 elif fault=='reference_id':ref['id']='mismatch';change_ref=True
 elif fault=='reference_source':ref['source_id']='other';change_ref=True
 elif fault=='reference_document':ref['document_id']='other';change_ref=True
 elif fault=='reference_block':ref['block_id']='other';change_ref=True
 elif fault=='reference_text':ref['source_text']='different';ref['source_text_sha256']=text_hash(ref['source_text']);change_ref=True
 elif fault=='reference_hash':ref['source_text_sha256']='wrong';change_ref=True
 elif fault=='reference_span':ref['mention_start']+=1;change_ref=True
 elif fault=='target_missing':s.tools.sources.pop('S2')
 elif fault=='target_acl':s.scope.remove('TARGET_DOC')
 elif fault=='target_unit':ref['targets'][0]['unit_id']='other';change_ref=True
 elif fault=='target_block':ref['targets'][0]['block_ids']=['other'];change_ref=True
 elif fault=='unresolved_target':ref['resolution']='UNRESOLVED';ref['targets']=[{'source_id':'missing'}];change_ref=True
 else:raise AssertionError(fault)
 if change_ref:db.execute('UPDATE reference SET json=? WHERE id=?',(json.dumps(ref,ensure_ascii=False),'RB'))
 db.commit()
def main():
 sys.dont_write_bytecode=True;resource.setrlimit(resource.RLIMIT_AS,(1073741824,1073741824))
 F=read(D/'freeze.json');C=R/F['code_root'];B=read(D/'baseline.json');criteria=read(D/'criteria.json')
 assert all(sha(R/n)==h for n,h in F['files'].items())
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==B['pointer_sha256']
 sys.path.insert(0,str(C/'02_BACKEND'))
 # Refuse provider/network access even if a future fixture accidentally tries it.
 import socket
 def blocked(*a,**kw):raise RuntimeError('network forbidden in finite contract audit')
 socket.create_connection=blocked;socket.socket.connect=blocked
 from semantic_runtime import search_selection as opt_sel
 from semantic_runtime.legal_agent import definition_entry as opt_de
 base_root=R/B['manifest']['code_root']
 base_sel=load('semantic_runtime._adr1073_baseline_selection',base_root/'02_BACKEND/semantic_runtime/search_selection.py')
 base_de=load('semantic_runtime.legal_agent._adr1073_baseline_definition',base_root/'02_BACKEND/semantic_runtime/legal_agent/definition_entry.py')
 helper=load('_adr1073_fixture',C/'05_TESTS/CONTRACTS/test_definition_reference_lookup_adr1071.py')
 records=[];checks={};started=time.perf_counter()
 with tempfile.TemporaryDirectory(prefix='adr1073-sql-') as temporary:
  tmp=Path(temporary)
  matrix=criteria['visibility_matrix']
  for case in product(*matrix.values()):
   layout,dstate,rstate,endpoint,duplicates,reverse=case;outputs=[]
   for arm,module in [('baseline',base_sel),('optimized',opt_sel)]:
    db=database(layout=='compact',dstate,rstate,endpoint,duplicates,reverse)
    before=main_snapshot(db);selection=selected(module,tmp)
    try:
     selection.bind(db,navigation=True)
     rows=db.execute('SELECT * FROM temp.definition_reference ORDER BY definition_id,reference_id').fetchall()
     expected=[('D-other','R-other')]+([('D','R')]*duplicates if dstate=='visible' and rstate=='visible' and endpoint!='hidden' else [])
     assert rows==sorted(expected),(case,arm,rows,expected)
     assert main_snapshot(db)==before,(case,arm,'database mutation')
     assert db.execute('PRAGMA query_only').fetchone()[0]==1
     for sql in ['DELETE FROM main.definition_reference','PRAGMA query_only=OFF']:
      try:db.execute(sql)
      except sqlite3.DatabaseError:pass
      else:raise AssertionError(('write guard missing',case,arm))
     outputs.append(rows)
    finally:db.close()
   assert outputs[0]==outputs[1]
   records.append({'kind':'visibility','case':dict(zip(matrix,case)),'equal':True,'rows':outputs[0]})
  matrix=criteria['definition_matrix']
  for case in product(*matrix.values()):
   layout,fault,reverse=case;outputs=[]
   for arm,module in [('baseline',base_de),('optimized',opt_de)]:
    s,m,refs=helper.fixture(layout=='compact');db=s.tools.db
    try:
     if reverse:
      db.execute('DELETE FROM definition_reference');db.executemany('INSERT INTO definition_reference VALUES(?,?)',[('D1','RA'),('D1','RB')])
     mutate(s,m,refs,fault,layout=='compact');before=main_snapshot(db);inputs=state(s,m)
     result=outcome(module.verified,s,m)
     expected='success' if fault in ('normal','target_acl','unresolved_target') else 'ContractError'
     assert result['type']==expected,(case,arm,result)
     assert state(s,m)==inputs and main_snapshot(db)==before,(case,arm,'mutation')
     if fault=='normal':assert result['value']==helper.expected(m)
     if fault=='target_acl':assert all(row['targets']==[] and row['scope_limited'] is True for row in result['value']['connections'])
     outputs.append(result)
    finally:db.close()
   assert outputs[0]==outputs[1],(case,outputs)
   records.append({'kind':'definition','case':dict(zip(matrix,case)),'equal':True,'outcome':outputs[0]})
  matrix=criteria['empty_matrix']
  for case in product(*matrix.values()):
   layout,n,has_table=case;outputs=[]
   for arm,module in [('baseline',base_de),('optimized',opt_de)]:
    s,m,refs=helper.fixture(layout=='compact');db=s.tools.db
    try:
     db.execute('DELETE FROM definition_reference')
     if not has_table:db.execute('DROP TABLE definition_reference')
     else:
      for i in range(n):
       ident=f'R-extra-{i}';ref=deepcopy(refs[0]);ref['id']=ident
       db.execute('INSERT INTO reference VALUES(?,?,?)',(ident,'DOC',json.dumps(ref,ensure_ascii=False)));db.execute('INSERT INTO definition_reference VALUES(?,?)',('D1',ident))
     db.commit();before=main_snapshot(db);inputs=state(s,m);result=outcome(module.verified,s,m)
     assert result['type']=='success' and len(result['value']['connections'])==(n if has_table else 0)
     assert state(s,m)==inputs and main_snapshot(db)==before
     outputs.append(result)
    finally:db.close()
   assert outputs[0]==outputs[1]
   records.append({'kind':'empty_and_count','case':dict(zip(matrix,case)),'equal':True,'connections':n if has_table else 0})
 # Supplemental historical regressions include independent EXPLAIN checks.
 import pytest
 output=io.StringIO()
 with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
  exit_code=pytest.main(['-q','-p','no:cacheprovider','--confcutdir='+str(C/'05_TESTS/CONTRACTS'),str(C/'05_TESTS/CONTRACTS/test_definition_reference_lookup_adr1071.py'),str(C/'05_TESTS/CONTRACTS/test_definition_selection_exists_adr1072.py')])
 (A/'artifacts/run-002/supplemental.log').write_text(output.getvalue())
 assert exit_code==0,output.getvalue()
 changes=read(D/'candidate-preparation.json')['changed'];targets=read(D/'candidate-preparation.json')['source_targets']
 actual_changed=[n for n,h in B['manifest']['files'].items() if sha(C/n)!=h]
 source_changes=[n for n in actual_changed if n!='00_SYSTEM/PIPELINE.json' and not n.startswith('02_BACKEND/ENGINES/')]
 config=read(C/'00_SYSTEM/PIPELINE.json');pinchecks=0
 for entry in config['engines'].values():
  assert sha(C/entry['manifest'])==entry['sha256']
  for n,h in read(C/entry['manifest'])['files'].items():assert sha(C/n)==h;pinchecks+=1
 # Compare every non-pin configuration field, and every engine non-target pin.
 old_config=read(base_root/'00_SYSTEM/PIPELINE.json');new_config=deepcopy(config)
 for name in old_config['engines']:new_config['engines'][name]['sha256']=old_config['engines'][name]['sha256']
 assert new_config==old_config
 for entry in config['engines'].values():
  old=read(base_root/entry['manifest']);new=read(C/entry['manifest'])
  for n in targets:
   if n in old['files']:new['files'][n]=old['files'][n]
  assert old==new
 checks={'all512_visibility_cases_equal':len([x for x in records if x['kind']=='visibility'])==512,
 'all100_definition_cases_equal':len([x for x in records if x['kind']=='definition'])==100,
 'all16_empty_count_cases_equal':len([x for x in records if x['kind']=='empty_and_count'])==16,
 'exact_failures_and_normal_results':all(x['equal'] for x in records),
 'no_fixture_or_original_mutation':True,'query_only_and_authorizer_preserved':True,
 'supplemental11_tests_and_point_query_plans':exit_code==0 and '11 passed' in output.getvalue(),
 'only_two_product_files_and31_pins':source_changes==targets and len(actual_changed)==33 and changes==actual_changed,
 'all420_serving_files_bound':len(F['serving_files'])==420 and all(sha(C/n)==h for n,h in F['serving_files'].items()),
 'data_profile_search_model_and_budgets_unchanged':True,
 'engine_dependency_pins_match':pinchecks>0,'frozen_inputs_unchanged':all(sha(R/n)==h for n,h in F['files'].items()),
 'main103_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==B['pointer_sha256']}
 imported={}
 for name,module in sys.modules.items():
  if name=='semantic_runtime' or name.startswith(('semantic_runtime.','lawrag.')):
   file=getattr(module,'__file__',None)
   if file:
    p=Path(file).resolve()
    assert p.is_relative_to(C) or name in ('semantic_runtime._adr1073_baseline_selection','semantic_runtime.legal_agent._adr1073_baseline_definition'),(name,str(p))
    imported[name]=str(p.relative_to(R))
 checks['explicit_import_isolation']=True
 result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'primary_cases':len(records),'supplemental_tests':11,'engine_pins_verified':pinchecks,'new_external_model_calls':0,'new_evaluator_calls':0,'network_attempts':0,'wall_seconds':time.perf_counter()-started,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
 'quality_certified':False,'scope':criteria['evaluation_boundary'],
 'limitations':['Finite declared SQL states only; not all possible databases or malformed schemas. Valid reference IDs use the existing primary-key contract.','No new legal quality holdout, real-model reasoning, whole-service speed or GENOS Oracle latency claim.','Historical performance evidence remains ADR1070-1072, not relabeled as this primary evidence.','Actual selected service and post-activation experiments are separate required follow-up checks.']}
 put(A/'artifacts/run-002/matrix.json',records);put(A/'artifacts/run-002/imports.json',imported);put(A/'artifacts/run-002/result.json',result)
 assert result['strict_success'],checks
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
 try:main()
 except BaseException as exc:
  path=A/'artifacts/run-002/FAILED.json'
  if not path.exists():put(path,{'type':type(exc).__name__,'detail':str(exc),'traceback':traceback.format_exc(),'criteria_unchanged':True})
  raise
