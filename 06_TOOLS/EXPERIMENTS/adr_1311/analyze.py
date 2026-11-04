from common import *
import collections,sqlite3
results={};raw=sqlite3.connect((ROOT/read(DES/'baseline.json')['release']['data_path']/'store.sqlite').as_uri()+'?mode=ro',uri=True)
blocks={}
for arm in ('before','optimized'):
 P=ART/'replay'/('ontology-369-'+arm);r=read(P/'result.json');checks=read(P/'replay-checks.json')
 assert r['http_status']==200 and r['replay_complete'] and len(checks)==8 and all(x['protected_exact'] for x in checks)
 samples=read(P/'sample-stacks.json.gz');inc=collections.Counter()
 for row in samples['stacks']:
  for frame in set(tuple(x) for x in row['stack']):inc[frame]+=row['seconds']
 sql=read(P/'sql-observation.json');queries=[{**q,**sql['sql_shapes'].get(q['query_id'],{})} for q in sql['query_stats'] if q['phase']=='request']
 count=lambda part:sum(q['calls'] for q in queries if part in q.get('shape',''))
 secs=lambda part:sum(q['exclusive_seconds'] for q in queries if part in q.get('shape',''))
 sourcechecks=0
 def check(v):
  global sourcechecks
  if isinstance(v,dict):
   if v.get('document_id') and isinstance(v.get('spans'),list):
    for span in v['spans']:
     if isinstance(span,dict) and all(k in span for k in ('block_id','start_cp','end_cp','text')):
      k=(v['document_id'],str(span['block_id']))
      if k not in blocks:blocks[k]=raw.execute('SELECT text FROM source_block WHERE document_id=? AND block_id=?',k).fetchone()
      assert k[0] in read(DES/'cases.json')[0]['document_ids'] and blocks[k]
      assert blocks[k][0][span['start_cp']:span['end_cp']]==span['text'];sourcechecks+=1
   for item in v.values():check(item)
  elif isinstance(v,list):
   for item in v:check(item)
 for p in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):check(read(p)['view'])
 results[arm]={'seconds':r['request_seconds'],'protected_requests':len(checks),'final_equal':r['replay_complete'],'recorded_responses':8,'physical_calls':0,'source_span_checks':sourcechecks,'source_mismatches':0,'children_sample_seconds':sum(v for k,v in inc.items() if k[0].endswith('structure_selection.py') and k[2]=='children'),'block_point_queries':count('SELECT * FROM source_block WHERE document_id=? AND block_id=?'),'source_json_point_queries':count('SELECT json FROM source WHERE id=?'),'fts_queries':count('WHERE unit_fts MATCH'),'fts_seconds':secs('WHERE unit_fts MATCH'),'sqlite_api_seconds':sum(q['exclusive_seconds'] for q in queries),'top_stacks':[{'file':k[0],'line':k[1],'function':k[2],'seconds':v} for k,v in inc.most_common(20)],'top_sql':sorted(queries,key=lambda q:q['exclusive_seconds'],reverse=True)[:10]}
raw.close();reduction=100*(1-results['optimized']['seconds']/results['before']['seconds'])
validation=read(ART/'contracts-final/result.json');baseline=read(ART/'baseline-fixture/result.json')
assert validation['passed']==89 and validation['failed']==1 and baseline['failed']==1
assert [x['test'] for x in validation['rows'] if x['outcome']=='failed']==[x['test'] for x in baseline['rows'] if x['outcome']=='failed']
out={'status':'complete','by_arm':results,'replay_reduction_percent':reduction,'speed_hypothesis_pass':reduction>=50,'contracts_passed':89,'preexisting_fixture_failures':1,'new_regressions':0,'model_calls':0,'oracle_calls':0,'main_changed':False,'limits':'One identical observer pair; diagnostic replay excludes model service latency, no Oracle corpus speed estimate. Primary source independent span checks preserve exact text.'}
put(ART/'comparison.json',out);put(RUN/'result.json',out)
print(json.dumps({a:{k:v for k,v in x.items() if k not in ('top_stacks','top_sql')} for a,x in results.items()},ensure_ascii=False,indent=2));print('REDUCTION',reduction)
