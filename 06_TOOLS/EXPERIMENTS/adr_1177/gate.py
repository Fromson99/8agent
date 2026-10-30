"""Offline followup gate. Gold never enters product input or corrective prompts."""
from common import *
import sys,sqlite3
cid=sys.argv[1];P=ART/'live'/cid;a=read(P/'audit.json');r=read(P/'result.json');storage=read(P/'storage-audit.json');out=a.get('accepted_outcome') or {}
refs=next(x for x in read(ART/'evaluation-only/cases.json') if x['id']==cid)
data=ROOT/read(DES/'baseline.json')['release']['data_path'];db=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True);coords=set()
for sid in a['read_source_ids']:
 row=db.execute('select json from source where id=?',(sid,)).fetchone()
 if row:
  v=json.loads(row[0]);co=v.get('article_coordinate') or {};coords.add((co.get('doc_id',v.get('document_id')),str(co.get('node',v.get('unit_id')))))
required={(x['doc_id'],str(x['node'])) for x in refs['targets'] if x.get('role')=='required'}
missing=required-coords
assessment=(a['assessments'][-1]['payload'] if a['assessments'] else {})
checks={'http_ready':r.get('http_status')==200 and r.get('status')=='READY','original_integrity':not a['source_mismatches'] and not a['acl_violations'],'physical_budget_matches':a['physical_budget_matches'],'no_output_cap':not a['output_cap_fields'],'pointer_unchanged':r['active_pointer_unchanged'],'covered':out.get('answer_coverage')=='COVERED' and out.get('disposition')=='ANSWER','supported_claims':a['claim_count']>0,'no_material_gap':not any(x.get('material') for x in assessment.get('gaps',[])),'required_originals_acquired':not missing,'storage_complete':storage.get('stored_request_status')=='COMPLETE' and all(storage.get(k) is True for k in ('view_hash_verified','stored_answer_text_equal','stored_assessment_hash_equal'))}
g={'case_id':cid,'passed':all(checks.values()),'checks':checks,'missing_required_originals':[{'doc_id':d,'node':n} for d,n in sorted(missing)],'question_completeness_passed':all(checks.values()),'legal_quality_certified':False,'main_eligible':False,'scope':'Frozen containment, required-source and completion conditions; no legal accuracy certification','new_model_calls':0}
put(P/'gate.json',g);print(json.dumps(g,ensure_ascii=False))
