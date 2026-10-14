"""Preserve observed interruptions and unstarted cases without synthesizing responses."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0690-judgment-loop-package-holdout';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
for p,h in read(D/'freeze.json')['files'].items():assert sha(R/p)==h,p
P=O/'repaired/H05';assert not (P/'result.json').exists()
db=sqlite3.connect(next((P/'runtime').rglob('journal.sqlite')).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
event=dict(db.execute('SELECT * FROM event ORDER BY seq DESC LIMIT 1').fetchone());attempt=dict(db.execute('SELECT * FROM model_attempt ORDER BY created_seq DESC LIMIT 1').fetchone());db.close()
assert event['kind']=='ATTEMPT_SENT' and attempt['response_hash'] is None
calls=sorted((P/'provider').glob('call-*'));missing=[p for p in calls if not (p/'response.json').exists()];assert len(missing)==1
usage=read(P/'provider/usage.json');assert len(usage)==4 and len(calls)==5
lines=(A/'artifacts/execution/H05-repaired.log').read_text().splitlines();times=[]
for line in lines:
 try:
  v=json.loads(line)
  if 'ts' in v:times.append(datetime.fromisoformat(v['ts']))
 except ValueError:pass
receipt={'origin':'Assistant turn interrupted; no execution process survived; user requested continuation','recorded_at':datetime.now(timezone.utc).isoformat(),
 'last_event_seq':event['seq'],'last_event_kind':event['kind'],'last_attempt_id':attempt['attempt_id'],'request_hash':attempt['request_hash'],
 'response_observed':False,'unknown_call_resent':False,'completed_provider_calls':4,'attempted_provider_calls':5,
 'unanswered_call':str(missing[0].relative_to(P)),'all_frozen_files_match':True,'raw_journal_preserved':True,'source':'Developer turn_aborted notice and user 계속해봐'}
put(P/'interruption-receipt.json',receipt)
dataset=read(D/'dataset.json');baseline=read(D/'baseline.json');bindings=read(D/'bindings.json')
for case in dataset['cases']+dataset['regression_cases']:
 for arm in ['baseline','repaired']:
  p=O/arm/case['case_id']/'result.json'
  if p.exists():continue
  interrupted=case['case_id']=='H05' and arm=='repaired'
  v={'case_id':case['case_id'],'arm':arm,'question':case['question'],'code_root':str(R/bindings['stage' if arm=='repaired' else 'baseline_code']),
   'source_generation':str(R/bindings['source_generation']),'model':'qwen/qwen3.8-27b','field_execution':False,
   'active_pointer_before':baseline['pointer_sha256'],'active_pointer_after':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
   'http_status':None,'execution_status':'EXTERNAL_USER_INTERRUPTION' if interrupted else 'NOT_EXECUTED_AFTER_INTERRUPTION',
   'error':'Final result unknown after sent call5; no resend' if interrupted else 'Not attempted: two external interruptions make frozen7/8 criterion unreachable; unchanged criteria and denominator retained',
   'total_seconds':(times[-1]-times[0]).total_seconds() if interrupted else 0,'duration_is_lower_bound':interrupted,
   'model_calls':5 if interrupted else 0,'usage':usage if interrupted else [],'output':{},'receipt_origin':'offline execution accounting, not an HTTP response'}
  if interrupted:v.update(interruption_receipt=str((P/'interruption-receipt.json').relative_to(R)),usage_complete=False)
  put(p,v)
put(A/'artifacts/external-stop.json',{'status':'terminated-after-external-interruptions','original_primary_count':8,'minimum_required_supported':7,
 'interrupted_primary':['H01/repaired','H05/repaired'],'maximum_possible_supported':6,'criteria_changed':False,
 'unstarted_cases':[x['case_id'] for x in dataset['cases'][5:]+dataset['regression_cases']],
 'decision':'Rejected; no promotion. New prospective experiment may use only previously unstarted cases without reusing this decision as a pass.'})
print('Preserved two interruptions; unstarted cases explicitly recorded, no calls')
