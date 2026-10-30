from common import *
import sqlite3
P=ART/'live/cm-009';a=read(P/'audit.json');r=read(P/'result.json');calls=read(P/'calls.json')
last=read(P/'canonical/012-output.json.gz');first=read(P/'canonical/011-output.json.gz')
assert last['gaps'][0]['material'] is True and last['requirement_review'][0]['status']=='SATISFIED' and not last['requirement_review'][0]['gap_indices']
assert first['gaps']==last['gaps'] and first['requirement_review']==last['requirement_review']
failures=[e for e in a['events'] if e['kind']=='COMPLETION_ASSESSMENT_REJECTED']
source_ids=['article:ece2450f99b261c5d36eb688','article:a70a998a1d8db68d8cfe4cf3']
assert all(s in a['read_source_ids'] for s in source_ids)
wire_receipts=[]
for n in (12,13):
 p=P/'raw'/f'call-{n:03d}'/'request.json.gz';raw=read(p);text=raw['messages'][1]['content'];wire_receipts.append({'call':n,'request_sha256':sha(p),'source31_text_present':'신속이전기업' in text,'exemption_exclusion_present':'대형법인' in text})
result={'case_id':'cm-009','full_case_passed':False,'cause':'REQUIREMENT_GAP_COVERAGE','source_acquisition_passed':True,'required_originals':source_ids,'actual_wire':wire_receipts,
 'first_and_repair_same_material_gap_and_review':True,'reported_material_gap':last['gaps'][0],'conflicting_review':last['requirement_review'][0],
 'final_assessment_calls':2,'reviewer_calls':sum(x['stage']=='memory-final-original-review' for x in calls),'final_answer_present':False,
 'failure_at':'ASSESS before COMPOSE/new reviewer','reason':'Model kept a material missing-source gap but left its requirement SATISFIED with no gap_indices; existing validation rejected both original and one repair. This is not a deadline/resource failure or caused by a new reviewer call.',
 'existing_requirement_validator_unchanged':sha(ROOT/read(DES/'freeze-live.json')['code_root']/'02_BACKEND/semantic_runtime/legal_agent/requirement_coverage.py')==sha(ROOT/'02_BACKEND/lawrag/research/candidates/adr_1200/recovered/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent/requirement_coverage.py'),
 'rejections':failures,'request_failed':True,'no_auto_repeat':True,'new_audit_model_calls':0}
put(P/'failure-analysis.json',result);print(result['reason'])
