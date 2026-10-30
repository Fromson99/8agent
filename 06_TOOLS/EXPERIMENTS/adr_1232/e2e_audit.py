"""Audit actual vector lineage and ontology activation without new model calls."""
from pathlib import Path
import json,gzip,hashlib,sys,math
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1232-gold-connected-live-revalidation';O=A/'artifacts/run-001';P=O/'live/cm-009';C=R/'08_DEPLOYMENT/RELEASES/schema-factor-20261029-r1/code'
def read(p):
 with (gzip.open(p,'rt') if str(p).endswith('.gz') else p.open()) as f:return json.load(f)
sys.path[:0]=[str(C/'02_BACKEND'),str(R/'06_TOOLS/maintenance')]
from semantic_runtime.legal_agent.journal_storage import connect
from experiment_json import write_summary,write_raw_json
j=connect(next((P/'runtime/legal-agent').rglob('journal.sqlite')).as_uri()+'?mode=ro',uri=True)
stages={r[0]:json.loads(r[1]) for r in j.execute("select entity_id,payload_json from entity_version where kind='case_stage'")}
recalled=stages['case:RECALL']['discovery']['law_navigation'];rows=recalled['vector_candidates'];scope=set(read(P/'request.json')['json']['document_ids']);candidates={x['source_id'] for x in rows}
acquired={x[0] for x in j.execute('select distinct source_id from evidence_unit')};final=read(P/'canonical/006.json.gz')['view'];finalids={x['source_id'] for x in final['sources']}
events=[{'seq':r[0],'kind':r[1],'payload':json.loads(r[2])} for r in j.execute('select seq,kind,payload_json from event') if any(t in r[1] for t in ['VECTOR','ONTOLOGY'])]
def strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for x in v.values():yield from strings(x)
 elif isinstance(v,list):
  for x in v:yield from strings(x)
wire=read(P/'raw/006/request.json.gz');wiretexts=list(strings(json.loads(wire['messages'][-1]['content'])))
spans=[s for s in final['evidence_options'] if all(k in s for k in ['text','document_id','block_id','start_cp','end_cp'])]
wirehits=[s for s in spans if any(s['text'] in t for t in wiretexts)]
vector_sql=sum('VECTOR_DISTANCE(' in s for s in read(P/'sql-statements.json.gz'))
profile=read(P/'binding.json')['profile']['candidate_navigation'];active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/active['manifest_path']);currentprofile=read(R/release['code_root']/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json')['candidate_navigation']
result={'actual_case':'cm-009','vector':{'search_policy':recalled['search_policy'],'sql_vector_searches':vector_sql,'embedding_calls':sum(e['payload'].get('embedding_calls',0) for e in events),'candidate_count':len(rows),'within_scope':all(x['document_id'] in scope for x in rows),'unique_ids':len(candidates),'rank_contiguous':[x['rank'] for x in rows]==list(range(1,len(rows)+1)),'finite_sorted_distances':all(math.isfinite(x['distance']) for x in rows) and [x['distance'] for x in rows]==sorted(x['distance'] for x in rows),'vector_candidates_also_acquired':len(candidates&acquired),'vector_candidates_in_final_source_list':len(candidates&finalids),'all_acquired_sources':len(acquired),'all_final_sources':len(finalids),'final_original_spans':len(spans),'final_wire_exact_text_hits':len(wirehits),'final_answer_issued':False,'publication_id':recalled['vector_publication'],'truncated':recalled['vector_truncated'],'reach':'real question embedding -> Oracle vector SQL -> source candidates -> original acquisition -> final model input; final response failed'},'ontology':{'actual_gold_profile':{k:v for k,v in profile.items() if 'ontology' in k},'selected_main_generation':active['generation'],'selected_main_profile':{k:v for k,v in currentprofile.items() if 'ontology' in k},'actual_ontology_events':sum('ONTOLOGY' in e['kind'] for e in events),'actual_final_ontology_bundles':len(final.get('ontology_bundles',[])),'gold_publication_excludes_approved_ontology':True,'exclusion_code':'02_BACKEND/lawrag/research/candidates/adr_1214/connected/revisions/rev-036/snapshot/08_DEPLOYMENT/LOCAL/gold_connection_r12/engine_build.py:147','actual_e2e':'NOT_CONNECTED; default OFF and no configured approved publication repository','authoring_to_answer_contract_test':'Separate synthetic native API on selected MAIN123; see checks-current-schema.json. Does not establish Gold Oracle or actual model integration.'},'source_integrity':{k:read(P/'audit.json')[k] for k in ['source_checks','nested_view_checks','flat_view_checks','source_mismatches','acl_violations','wire_request_matches']},'new_model_calls':0,'quality_certified':False,'scope_extension_request':'우리 온톨로지하고 벡터도 e2e로 자 돌아가는지 확인해줘'}
write_summary(O/'ontology-vector-e2e.json',result)
write_raw_json(O/'ontology-vector-lineage.json.gz',{'events':events,'vector_candidates':rows,'acquired_source_ids':sorted(acquired),'final_source_ids':sorted(finalids),'vector_and_final':sorted(candidates&finalids)})
print(json.dumps(result,ensure_ascii=False,indent=2))
