from common import *
P=ART/'saved-cm007-review';r=read(P/'result.json');p=next((P/'raw').glob('call-*/output.json'));v=read(p);data=read(P/'input.json.gz')
assert r['status']=='INCOMPLETE' and r['error']=='review finding conflicts with source status'
ids={x['source_id'] for x in data['sources']};assert len(ids)==6
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1200-supervisor-recovery-live-cm007/artifacts/live/cm-007'
assert data['draft']['text']==(old/'answer.txt').read_text()
receipts=[]
for n in ('request.json','response.json','output.json'):
 p=next((P/'raw').glob('call-*/'+n));receipts.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p)})
report={'case_id':'cm-007','reviewer_valid':False,'known_two_defects_detected':False,'observed_known_defects_detected':0,'known_defect_count':2,
 'findings_emitted':len(v['findings']),'false_positive_findings_observed':2,
 'reason':'Reviewer source rows said COVERED while findings alleged omissions. It missed the obligation-as-condition error and bylaw15(5) cause. It instead said acquisition time/price were absent from application conditions, even quoting the answer sentence that contains them; KOSPI time/price are also explicitly in the obligation. These are incorrect omission findings, not fixes.',
 'schema_shape_valid':True,'server_semantic_reference_status_check_passed':False,
 'answer_exact':True,'selected_sources':len(ids),'reference_answer_in_model_input':False,'raw_receipts':receipts,
 'previous1200_grade_unchanged':True,'no_automatic_retry':True,'quality_certified':False,'new_audit_model_calls':0}
put(P/'content-audit.json',report);print(json.dumps(report,ensure_ascii=False))
