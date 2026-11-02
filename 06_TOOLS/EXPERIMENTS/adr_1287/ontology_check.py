"""Inspect recorded plans and exercise existing typed operations without authoring knowledge."""
from common import *
import gzip
release=read(ROOT/'08_DEPLOYMENT/RELEASES'/RELEASE/'release.json');C=ROOT/release['code_root']
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
from semantic_runtime.ontology_work.evaluation_plan import run
from lawrag.legal_knowledge.ontology import evaluate
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1286-scenario-scope-contract-live/artifacts/live/review-whatif'
def raw(name):return json.loads(gzip.decompress((prior/name).read_bytes()))
initial=raw('initial-response.json.gz')['body']['assembly']['term_agent']['review_explanation']
catalog=next(b['assembly'] for b in initial['ontology']['bundles'] if b.get('assembly',{}).get('evaluation_plan'))
plan=catalog['evaluation_plan']
money=lambda n:{'type':'money','unit':'KRW','value':str(n)}
boolean=lambda b:{'type':'boolean','unit':'','value':b}
cases=[
 {'id':'low_unknown','inputs':{'cost':money(735000),'limit':money(1000000)},'expected':'UNKNOWN'},
 {'id':'high_unknown','inputs':{'cost':money(1725000),'limit':money(1000000)},'expected':'FALSE'},
 {'id':'rule_unknown','inputs':{'cost':money(1380000),'limit':money(2450000)},'expected':'UNKNOWN'},
 {'id':'low_approved','inputs':{'cost':money(735000),'limit':money(1000000),'approved':boolean(True)},'expected':'TRUE'},
 {'id':'low_denied','inputs':{'cost':money(735000),'limit':money(1000000),'approved':boolean(False)},'expected':'FALSE'},
 {'id':'boundary_approved','inputs':{'cost':money(1000000),'limit':money(1000000),'approved':boolean(True)},'expected':'TRUE'},
 {'id':'missing_cost','inputs':{'limit':money(1000000),'approved':boolean(True)},'expected':'UNKNOWN'},
 {'id':'approval_conflict','inputs':{'cost':money(735000),'limit':money(1000000),'approved':boolean(True)},'conflict':'approved','expected':'CONFLICT'}]
expression={'op':'all','args':[{'op':'lte','args':[{'field':'cost'},{'field':'limit'}]},{'field':'approved'}]}
put(DES/'ontology-check-cases.json',{'cases':cases,'expression':expression,
 'purpose':'Existing evaluator capability only. This conjunction is not a newly approved N1 legal effect; no save/review/publish or production configuration change.'})
recorded=[]
for label,expected in [('low','TRUE'),('high','FALSE'),('rule','TRUE')]:
 comparison=raw(label+'-response.json.gz')['body']['assembly']['term_agent']['scenario_comparison']
 inputs={'cost':money(1380000),'limit':money(1000000),**comparison['changes']}
 evaluated=run(plan,inputs,binding='adr1287-read-only-'+label)
 stored={r['node_id']:r['result']['status'] for r in comparison['evaluations']}
 row={'case':label,'nodes':{k:v['status'] for k,v in evaluated.items()},'recorded_nodes':stored,
  'effect_comparison':next(r['after'] for r in comparison['comparisons'] if r['node_id']=='N1')}
 row['passed']=row['nodes']==stored and evaluated['N2']['status']==expected and evaluated['N3']['status']=='UNKNOWN'
 recorded.append(row)
operations=[]
for case in cases:
 facts={k:{'status':'CONFLICT' if k==case.get('conflict') else 'ASSERTED','origin_ref':'synthetic-diagnostic','value':v} for k,v in case['inputs'].items()}
 result=evaluate(expression,facts,binding='adr1287-operator-check-'+case['id'])
 operations.append({'case':case['id'],'expected':case['expected'],'actual':result['status'],'missing':result['missing'],'conflicts':result['conflicts'],'passed':result['status']==case['expected']})
result={'recorded_plan':{'bundle_id':plan['bundle_id'],'plan_hash':plan['plan_hash'],'approval_ref':plan['approval_ref'],'rule_nodes':[r['node_id'] for r in plan['spec']['rules']],
  'effect_N1_has_typed_expression':any(r['node_id']=='N1' for r in plan['spec']['rules']),
  'edges':[{'from':e['from'],'to':e['to'],'type':e['type']} for p in catalog['paths'] for e in p['edges']]},
 'recorded_conditions':recorded,'existing_operator_checks':operations,
 'passed':all(r['passed'] for r in recorded+operations),'new_model_calls':0,'knowledge_writes':0,'oracle_calls':0,
 'code_root':str(C),'source_records':[bind(prior/(label+'-response.json.gz')) for label in ('initial','low','high','rule')],
 'code_unchanged':all(sha(C/n)==h for n,h in release['files'].items()),
 'limits':'Checks deterministic operators and preserved numeric results, not legal applicability. Conjunction example is offline and unapproved. Scope, source version, exceptions and fact conflicts still require explicit reviewed bindings. No automatic N1 expression or semantic repair was added.'}
put(OUT/'ontology-capability-check.json',result)
assert result['passed'] and result['code_unchanged']
print({'recorded_conditions':len(recorded),'operator_checks':len(operations),'passed':result['passed'],'N1_typed':False,'knowledge_writes':0})
