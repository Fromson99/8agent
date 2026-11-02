from types import SimpleNamespace as NS
from experiment_json import write_raw_json
fixture=read(DES/'scope-fixture.json');did=fixture['document_id'];elapsed=time.monotonic();pairs=[];raw=[];checks={}
with connect.open_store(documents=[did],seconds=900,max_calls=10000) as (store,request,transport):
 import engine_runtime
 from semantic_runtime.oracle_query_fulltext import UnitIndex
 idx=UnitIndex(request);before=request.sql.calls
 actual=idx.scope_keys(idx,did,fixture['units']);expected=sorted((x['key'],x['source_id']) for x in fixture['expected_rows']);assert actual==expected
 checks['scope_keys_equal_immutable_mirror']=True
 checks['scope_lookup_sql']=request.sql.calls-before
 before=request.sql.calls;assert idx.scope_keys(idx,did,[])==[];checks['empty_no_sql']=request.sql.calls==before
 try:idx.scope_keys(idx,'unauthorized',fixture['units'])
 except Exception as e:assert 'QUERY_SCOPE' in str(e);checks['foreign_document_rejected_before_query']=request.sql.calls==before
 else:raise AssertionError('foreign scope accepted')
 keys=[k for k,_ in actual]
 hit=idx._page(['의결권'],None,'hits',limit=100,unit_keys=keys)
 assert hit['items'] and {x['key'] for x in hit['items']}<=set(keys) and all(x['document_id']==did for x in hit['items'])
 checks['scoped_lexical_hits_with_original_bodies']=len(hit['items'])
 # Same immutable release, same ACL, same request and cursor; no DB writes.
 first=request.records.page('native.unit',document_id=did,limit=100)
 root=next(x['unit_id'] for x in fixture['expected_rows'] if x['key'].endswith('#unit:'+x['unit_id']))
 # Select a real stored parent for the owner-filter shape, independent of answer semantics.
 unit=request.records.page('native.unit',document_id=did,lookup_id=engine_runtime.digest([did,root]),limit=2)['rows'][0]
 owner=str(unit['unit'].get('parent') or root)
 selected=connect.mapped_reads
 for name,filters in [('owner',{'document_id':did,'owner_id':owner}),('page',{'document_id':did,'after':first['next']})]:
  assert name!='page' or first['next'] is not None
  outputs=[];timings=[];statements=[]
  for variant in ('baseline','narrowed'):
   connect.mapped_reads=(lambda rt,c,sql,binds:rt.rewrite_reads(sql,c)) if variant=='baseline' else selected
   from semantic_runtime.oracle_query_catalog import Records
   uncached=Records(request.sql,request.release_id,request.records.manifest,document_ids=request.sources.allowed)
   begin=time.monotonic();count=request.sql.calls;value=uncached.page('native.unit',limit=100,**filters);timings.append(time.monotonic()-begin);outputs.append(value);statements.append(transport.statements[-1]);assert request.sql.calls-count==1
  connect.mapped_reads=selected
  assert outputs[0]==outputs[1]
  assert ' UNION ALL ' in statements[0] and ' UNION ALL ' not in statements[1]
  pairs.append({'shape':name,'rows':len(outputs[0]['rows']),'same_rows_cursor_hash':True,'baseline_seconds':timings[0],'candidate_seconds':timings[1],'physical_sql_each':1,'old_sql_sha256':engine_runtime.hashlib.sha256(statements[0].encode()).hexdigest(),'new_sql_sha256':engine_runtime.hashlib.sha256(statements[1].encode()).hexdigest()})
  raw.append({'shape':name,'filters':filters,'outputs':outputs,'statements':statements})
 plan={'status':'unavailable','extra_metadata_selects':0}
 try:
  with transport.connection.cursor() as cursor:
   plan['extra_metadata_selects']+=1
   cursor.execute("SELECT PREV_SQL_ID FROM V$SESSION WHERE SID=SYS_CONTEXT('USERENV','SID')")
   sid=cursor.fetchone()[0]
   plan['extra_metadata_selects']+=1
   cursor.execute('SELECT ID,PARENT_ID,OPERATION,OPTIONS,OBJECT_NAME,ACCESS_PREDICATES,FILTER_PREDICATES FROM V$SQL_PLAN WHERE SQL_ID=:sid ORDER BY CHILD_NUMBER,ID',sid=sid)
   plan.update(status='read',sql_id=sid,rows=[list(x) for x in cursor.fetchall()])
 except Exception as exc:plan.update(error_type=type(exc).__name__,reason=str(exc))
 store.check_unchanged();idx.check_unchanged()
 result={'passed':True,'checks':checks,'pairs':pairs,'actual_sql_calls':request.sql.calls,'mapping_metadata_selects':1,'plan':plan,'seconds':time.monotonic()-elapsed,'new_models':0,'new_embeddings':0,'source_mirror_only_for_precomputed_expected_keys':True,'runtime_corpus_sqlite':False,'data_changes':0,'same_request_engine':str(ROOT/f['code_root']) if mode=='candidate' else str(ROOT/connect.engine_binding()['engine_root'])}
 out=ART/('gold-'+mode);out.mkdir(exist_ok=True)
 result['raw']=write_raw_json(out/'scope-comparison-raw.json.gz',raw)
 put(out/'scope-verification.json',result)
 print(json.dumps({k:v for k,v in result.items() if k not in ('raw','plan')},ensure_ascii=False))
