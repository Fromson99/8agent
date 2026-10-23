"""Offline exact trace/source audit; no model calls or product changes."""
from common import *
import sqlite3,sys,collections
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
P=ART/'known-query/candidate';s=read(ART/'stage.json');G=ROOT/s['base_release']['data_path']
def ro(p):
 db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
nav=ro(G/'navigation/navigation.sqlite');source=ro(G/'store.sqlite')
def origin(sid):
 row=nav.execute('select json from source where id=?',(sid,)).fetchone();return json.loads(row[0]) if row else None
def coord(v):
 if not v:return None
 a=v.get('article_coordinate') or {};did=a.get('doc_id',v.get('document_id'));node=a.get('node',v.get('unit_id'))
 return {'doc_id':did,'node':int(node)} if did and str(node).isdigit() else None
def uniq(rows):return [json.loads(x) for x in sorted({json.dumps(x,sort_keys=True) for x in rows if x})]
def h(t):return hashlib.sha256(t.encode()).hexdigest()
def cited(v):
 if isinstance(v,list):return set().union(*(cited(x) for x in v))
 if isinstance(v,dict):return set(v.get('source_ids',[])).union(*(cited(x) for k,x in v.items() if k!='source_ids'))
 return set()
def expand(v):
 if isinstance(v,list):return [expand(x) for x in v]
 if isinstance(v,dict):
  if 'table_rows' in v:return [expand(dict(zip(v['table_columns'],r))) for r in v['table_rows']]
  return {k:expand(x) for k,x in v.items()}
 return v
response=read(P/'response.json');body=response['body'];result=read(P/'result.json');allowed=read(P/'request.json')['json']['document_ids']
events=[];checks=[];read_rows=[]
for p in (P/'runtime').rglob('journal.sqlite'):
 db=ro(p)
 for row in db.execute('select seq,kind,payload_json from event order by seq'):events.append({'seq':row['seq'],'kind':row['kind'],'payload':json.loads(row['payload_json'])})
 for row in db.execute('select * from evidence_unit'):
  e=dict(row);spans=[dict(x) for x in db.execute('select * from evidence_span where evidence_id=? order by ordinal',(e['evidence_id'],))];valid=bool(spans)
  for span in spans:
   raw=source.execute('select text,source_artifact_sha256 from source_block where document_id=? and block_id=?',(e['document_id'],span['block_id'])).fetchone()
   valid=valid and bool(raw) and raw['source_artifact_sha256']==e['source_artifact_hash'] and h(raw['text'])==span['block_hash'] and raw['text'][span['start_cp']:span['end_cp']]==span['text'] and h(span['text'])==span['span_hash']
  valid=valid and h('\n'.join(x['text'] for x in spans))==e['text_hash']
  checks.append({'evidence_id':e['evidence_id'],'span_count':len(spans),'exact_original_match':bool(valid),'within_scope':e['document_id'] in allowed})
  o=origin(e['source_id']);read_rows.append({'evidence_id':e['evidence_id'],'source_id':e['source_id'],'canonical':coord(o),'heading':o.get('heading'),'blocks':[x['block_id'] for x in spans]})
 db.close()
trace=[]
for p in sorted((P/'model').glob('call-*/request.json')):
 raw=read(p);v=expand(json.loads(next(x['content'] for x in raw['messages'] if x['role']=='user'))['view']);reply=read(p.with_name('response.json'))
 try:out=json.loads(reply['choices'][0]['message']['content'])
 except (ValueError,KeyError):out={'invalid_model_output':True,'finish_reason':reply.get('choices',[{}])[0].get('finish_reason'),'raw_response':str(p.with_name('response.json').relative_to(ROOT))}
 trace.append({'call':p.parent.name,'source_stage':v.get('source_stage',v.get('phase')),'source_count':len(v.get('sources',[])),'reference_summary':{k:v.get('references',{}).get(k) for k in ('connection_groups','omitted_dependency_cards','current_anchor_ids')},'dependency_cards':v.get('references',{}).get('dependency_cards',[]),'scope_choices':v.get('connection_scope_choices',[]),'selected_scope':v.get('selected_connection_scope'),'relation_groups':v.get('groups',[]),'sources92':[x for x in v.get('sources',[]) if '제92조' in x.get('heading','')],'proposal':out})
 if 'read-choice' in str(v.get('source_stage')):save(ART/'navigation-input-expanded.json',v)
save(ART/'events.json',events)
save(ART/'source-audit.json',{'checks':checks,'read_evidence':read_rows})
save(ART/'calls.json',trace)
# Exact stored definition relationship versus all explicit references in the same item.
details=[]
for row in nav.execute("select id,json from definition where document_id=? and json_extract(json,'$.source_id')=?",('61789e1949a9e2cd','article:1b06d5bed318597090c9d778')):
 d=json.loads(row['json']);d['linked_references']=[json.loads(x[0]) for x in nav.execute('select r.json from definition_reference l join reference r on r.id=l.reference_id where l.definition_id=?',(row['id'],))];details.append(d)
refs=[]
for r in nav.execute('select distinct r.json from reference r join reference_end e on e.reference_id=r.id where e.source_id=?',('article:1b06d5bed318597090c9d778',)):
 v=json.loads(r[0])
 if v.get('source_id')=='article:1b06d5bed318597090c9d778' and str(v.get('block_id'))=='1142':refs.append(v)
save(ART/'definition-and-item-references.json',{'definitions':details,'item_explicit_references':refs})
finalids=sorted(cited(body.get('answer',{})));reads=uniq(x['canonical'] for x in read_rows);finals=uniq(coord(origin(x)) for x in finalids)
rec=StageLedgerRecorder('capital-gains-expenses','candidate',identity_canonicalizer)
rec.record_stage('original_read','source',reads)
rec.record_stage('final_cited','present',finals,parent_stage_ids=['original_read'],discard_reasons=[{'identity':x,'reason':'Read evidence or preview not selected for final citation; no irrelevance or source-absence finding.'} for x in reads if x not in finals])
graded=grade_capture(rec.capture(),[])
ledger=build_experiment_artifact('ADR-0998','ADR-0998-experiment-v1',[build_run_artifact('run-001',[graded],{'candidate':['original_read','final_cited']})]);save(ART/'retrieval-ledger.json',ledger)
corpus=nav.execute('select count(*) from source where document_id in ('+','.join('?' for _ in allowed)+')',allowed).fetchone()[0]
scoped_catalogs=[]
for line in (P/'scope-trace.jsonl').open():
 event=json.loads(line)
 if event['kind']=='scoped_catalog' and event['data']['selected_scope_spans'] is not None:
  value=event['data']
  assert set(value['anchors'])<=set(value['selected_scope_spans'])
  assert all(g['anchor']['source_id'] in value['selected_scope_spans'] for g in value['groups'])
  scoped_catalogs.append(value)
save(ART/'selected-scope-audit.json',{'catalogs':scoped_catalogs,'scope_events':[e for e in events if e['kind'].startswith('CONNECTION_SCOPE_')],
    'navigation_has_combined_dependency_cards':any(x['dependency_cards'] for x in trace),
    'actions':[x['proposal'].get('choice') for x in trace if 'read-choice' in str(x['source_stage'])]})
report={'status':'COMPLETE','diagnostic_complete':True,'legal_answer_certified':False,'native_result':result,'model_seconds':sum(x['seconds'] for x in result['usage']),'non_model_elapsed_seconds':result['seconds']-sum(x['seconds'] for x in result['usage']),'input_tokens':sum(x['input_tokens'] for x in result['usage']),'output_tokens':sum(x['output_tokens'] for x in result['usage']),'cost_usd':sum(x['cost_usd'] for x in result['usage']),
 'read_choices':[x for x in events if x['kind']=='UNIT_READ_CHOICE'],'read_coordinates':reads,'final_coordinates':finals,'corpus_total':corpus,'source_checks':{'count':len(checks),'mismatches':sum(not x['exact_original_match'] for x in checks),'scope_violations':sum(not x['within_scope'] for x in checks)},'outcome':body.get('assembly',{}).get('term_agent',{}).get('accepted_outcome',{'answer_status':body.get('answer_status'),'failure_reason':body.get('failure_reason')}),'answer':body.get('answer',{}).get('text',body.get('message','')),'main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']}
report['scope_catalog_count']=len(scoped_catalogs)
save(ART/'observations.json',report);(ART/'answer.txt').write_text(report['answer']+'\n')
print(json.dumps({k:report[k] for k in ['status','model_seconds','non_model_elapsed_seconds','input_tokens','output_tokens','cost_usd','source_checks','main_unchanged']},ensure_ascii=False))
nav.close();source.close()
