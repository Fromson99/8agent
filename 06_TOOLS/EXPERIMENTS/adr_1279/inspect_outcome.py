"""Read-only inspection of actual assumption failure and preserved baseline."""
from common import *
import sqlite3
P=ART/'live/review-whatif';c=read(DES/'continuation.json');prior=ROOT/c['parent_runtime_snapshot'];runtime=ROOT/c['runtime']
initial=read(P/'initial-response.json.gz')['body'];after=read(P/'baseline-after-response.json.gz')['body'];branch=read(P/'semantic-response.json.gz')['body'];gid=initial['goal_id']
preserved=[]
for old in prior.rglob('*.sqlite'):
 new=runtime/old.relative_to(prior)
 with sqlite3.connect(old.as_uri()+'?mode=ro',uri=True) as a,sqlite3.connect(new.as_uri()+'?mode=ro',uri=True) as b:
  tables={x[0] for x in a.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if 'goal' not in tables:continue
  if not a.execute('SELECT 1 FROM goal WHERE id=?',(gid,)).fetchone():continue
  for table,col in [('goal','id'),('node','goal'),('route','goal')]:
   x=a.execute('SELECT * FROM '+table+' WHERE '+col+'=? ORDER BY rowid',(gid,)).fetchall();y=b.execute('SELECT * FROM '+table+' WHERE '+col+'=? ORDER BY rowid',(gid,)).fetchall()
   preserved.append({'table':table,'rows':len(x),'exact_equal':x==y})
ignore={'id','query_id'}
a0={k:v for k,v in initial['answer'].items() if k not in ignore};a1={k:v for k,v in after['answer'].items() if k not in ignore}
changed=[k for k in set(initial['answer'])|set(after['answer']) if initial['answer'].get(k)!=after['answer'].get(k)]
view=read(P/'canonical/001.json.gz')['view'];answer=branch['answer']['text'];assert view['hypothetical_scenario']['changes']['cost']['value']=='500000'
assert '1,500,000원' in answer and '금액 요건' in answer
record={'status':'FAIL_ASSUMPTION_NOT_APPLIED','approval_not_invented':True,'semantic_applies_changed_value':False,
 'actual_changed_input':view['hypothetical_scenario']['changes'],'current_facts':view['current_facts'],
 'numeric_condition':'N2 TRUE for500000','model_answer_uses_original_cost':True,
 'direct_cause':'semantic_branch only removes facts with exact name=cost; original model-normalized fact name is 작업 비용. Thus1500000원 stays alongside cost=500000 and original question/user_fact_sources retain1500000. Actual model uses old cost despite typed TRUE; final validator does not enforce assumption consistency.',
 'source_evidence':'canonical/001.json.gz + raw/call-001/request.json.gz + semantic-response.json.gz; model response unmodified',
 'missing_review_action_path':'Initial response naturally passed; explicit recovery action not exercised in this real run.',
 'rule_assumption_limitation':'Natural fact name 작업 비용/value1500000원 is not registered field cost, so baseline numeric value and RULE-only comparison remain UNKNOWN.',
 'quality_certified':False,'new_model_calls':0}
put(P/'semantic-review.json',record)
put(P/'baseline-preservation-inspection.json',{'goal':gid,'original_goal_same':initial['goal_id']==after['goal_id'],'revision_same':initial['revision']==after['revision'],'exact_baseline_tables':preserved,
 'answer_text_claims_evidence_same':a0==a1,'different_wire_keys':changed,'original_live_predicate':False,
 'explanation':'Live predicate compared all public answer keys. Request-specific id/query_id changed normally. Immutable original goal/node/route and answer content are checked here without discarding the original false observation.',
 'passed':bool(preserved) and all(x['exact_equal'] for x in preserved) and a0==a1 and set(changed)<=ignore,'new_model_calls':0})
print(record['status'],preserved,changed)
