from pathlib import Path
import json,sqlite3,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0794-definition-entry-storage-binding';O=A/'artifacts/live';read=lambda p:json.loads(p.read_text())
result=read(O/'result.json');response=read(O/'response.json');target='article:c3af79efc692a91026430460';calls=[];target_read=0;errors=[];definitions=[];rejected=[]
for p in sorted((O/'raw').glob('call-*')):
 req=read(p/'request.json');req=req.get('body',req);v=read(p/'response.json') if (p/'response.json').exists() else {};schema=req.get('response_format',{}).get('json_schema',{}).get('schema',{});data=json.loads(req['messages'][-1]['content']).get('view',{})
 if 'definition_entries' in data:definitions.append({'call':p.name,'entries':data['definition_entries']})
 calls.append({'call':p.name,'model':v.get('model'),'provider':v.get('provider'),'schema_bytes':len(json.dumps(schema,ensure_ascii=False).encode()),'provider_error':v.get('error')})
for p in (O/'runtime').rglob('journal.sqlite'):
 db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 target_read+=db.execute('SELECT count(*) FROM evidence_unit WHERE source_id=?',(target,)).fetchone()[0]
 for r in db.execute("SELECT kind,payload_json FROM event WHERE kind='LAW_DECISION_REJECTED'"):
  v=json.loads(r['payload_json']);rejected.append({'kind':r['kind'],'attempt':v.get('attempt'),'error':v.get('diagnostics',{}).get('error_message'),'error_category':v.get('diagnostics',{}).get('output_contract',{}).get('category')})
 db.close()
meta=response.get('assembly',{}).get('term_agent',{});answer=response.get('answer',{});text=answer.get('text','')
out={'http_status':result.get('http_status'),'model_calls':result['model_calls'],'seconds':result['elapsed_seconds'],'model_usage':result['model_usage'],'provider_errors':[c for c in calls if c['provider_error']],'model_provider_verified':all(c['model']=='qwen/qwen3.8-27b' and c['provider']=='Parasail' for c in calls),'calls':calls,'initial_navigation_has_definitions':bool(definitions) and definitions[0]['call'].startswith('call-002'),'definition_entries':definitions[:1],'target_original_evidence_count':target_read,'target_in_response':target in json.dumps(response),'target_coordinate_in_answer':'3-24' in text,'accepted_outcome':meta.get('accepted_outcome'),'answer_coverage':meta.get('answer_coverage'),'answer_preview':text[:1400],'rejected_navigation':rejected,'known_case':True,'quality_certified':False,'no_gold_to_product':True}
(O/'diagnostic.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('model_usage','calls','definition_entries','answer_preview')},ensure_ascii=False))
