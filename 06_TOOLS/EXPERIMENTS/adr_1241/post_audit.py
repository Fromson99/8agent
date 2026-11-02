"""Read-only actual transport stop, vector/source and judgment trajectory audit."""
from pathlib import Path
import json,gzip,sys,math
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001';cid=sys.argv[1];P=O/'live'/cid
def read(p):
 with (gzip.open(p,'rt') if str(p).endswith('.gz') else p.open()) as f:return json.load(f)
C=R/read(D/'before.json')['binding']['engine_root'];sys.path[:0]=[str(C/'02_BACKEND'),str(R/'06_TOOLS/maintenance')]
from semantic_runtime.legal_agent.journal_storage import connect
from experiment_json import write_summary,write_raw_json
calls=read(P/'calls.json');a=read(P/'audit.json');result=read(P/'result.json');events=[];states=[];acquired=set();model_attempts=[]
for jp in sorted((P/'runtime/legal-agent').rglob('journal.sqlite')):
 with connect(jp.as_uri()+'?mode=ro',uri=True) as db:
  events += [{'seq':r[0],'kind':r[1],'payload':json.loads(r[2])} for r in db.execute('select seq,kind,payload_json from event order by seq')]
  states += [{'kind':r[0],'entity_id':r[1],'version':r[2],'payload':json.loads(r[3])} for r in db.execute('select kind,entity_id,version,payload_json from entity_version order by version')]
  acquired |= {r[0] for r in db.execute('select distinct source_id from evidence_unit')}
  model_attempts += [dict(r) for r in db.execute('select a.attempt_id,v.phase,a.status from model_attempt a join model_view v using(view_id) order by a.created_seq')]
views=[]
for cp in sorted((P/'canonical').glob('[0-9][0-9][0-9].json.gz')):
 v=read(cp)['view'];views.append(v)
finals=[v for v in views if str(v.get('source_stage','')).startswith('memory-assess')]
recalls=[s['payload'] for s in states if s['kind']=='case_stage' and s['entity_id']=='case:RECALL'];recalled=(recalls[-1].get('discovery',{}).get('law_navigation',{}) if recalls else {});rows=recalled.get('vector_candidates',[])
candidates={x['source_id'] for x in rows};scope=set(read(P/'request.json')['json']['document_ids']);finalids={x['source_id'] for v in finals for x in v.get('sources',[])}
vector_sql=sum('VECTOR_DISTANCE(' in s for s in read(P/'sql-statements.json.gz'));embedding_calls=sum(e['payload'].get('embedding_calls',0) for e in events if 'VECTOR' in e['kind'])
unknowns=[x['number'] for x in calls if x['status']=='unknown'];after=[x['number'] for x in calls if unknowns and x['number']>unknowns[0]]
unknown_stop=[e for e in events if e['kind']=='SUPERVISOR_UNKNOWN_STOP'];rejections=[e for e in events if any(s in e['kind'] for s in ('REJECT','FAILED','INCOMPLETE','UNRESOLVED'))]
vector={'embedding_calls':embedding_calls,'oracle_vector_searches':vector_sql,'candidate_count':len(rows),'unique_source_ids':len(candidates),'all_within_scope':all(x['document_id'] in scope for x in rows),'rank_contiguous':[x['rank'] for x in rows]==list(range(1,len(rows)+1)),'finite_sorted_distances':all(math.isfinite(x['distance']) for x in rows) and [x['distance'] for x in rows]==sorted(x['distance'] for x in rows),'vector_candidates_acquired':len(candidates&acquired),'vector_candidates_in_final':len(candidates&finalids),'final_answer_issued':a['final_answer_present'],'publication_id':recalled.get('vector_publication'),'search_policy':recalled.get('search_policy')}
summary={'case_id':cid,'unknown':{'observed_calls':unknowns,'later_physical_calls':after,'stop_without_later_calls':None if not unknowns else not after,'supervisor_stop_events':len(unknown_stop),'triggered':bool(unknowns)},'vector':vector,'final_model_inputs':len(finals),'provider_switches':sum(e['kind']=='MODEL_PROVIDER_STATE' for e in events),'ontology_acquisitions':[e for e in events if e['kind']=='ONTOLOGY_BUNDLE_ACQUISITION'],'rejection_events':rejections,'model_attempts':model_attempts,'quality_certified':False,'actual_duplicate_request_retest':False,'new_model_calls':0}
summary['detail']=write_raw_json(P/'post-audit-detail.json.gz',{'events':events,'states':states,'vector_candidates':rows,'vector_and_final':sorted(candidates&finalids)})
if cid=='cm-009':
 summary['full_e2e_gates']={'real_embedding':embedding_calls>0,'real_vector_sql':vector_sql>0,'scoped_candidates':bool(rows) and vector['all_within_scope'],'vector_originals_in_final':vector['vector_candidates_in_final']>0,'saved_final_answer':result.get('http_status')==200 and a['final_answer_present'] and a['storage'].get('answer_equal',False),'exact_originals_ACL_wire':a['source_checks']>0 and not a['source_mismatches'] and not a['acl_violations'] and not a['wire_request_mismatches'],'budget_exact':a['physical_budget_matches'],'no_unknown_or_resource_stop':not unknowns and not a['resource']['stop']}
write_summary(P/'post-audit.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k not in ('rejection_events','detail','model_attempts','ontology_acquisitions')},ensure_ascii=False,indent=2))
