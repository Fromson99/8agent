"""Reserve-first strict prototype design; product inputs never contain gold."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0594-rag-chain-strict-contracts'
PARENT = ROOT / '04_EXPERIMENTS/ADR/ADR-0593-rag-chain-native-kind-repair'
D = ADR / 'artifacts/design'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

def main():
    for name in ['inputs.json', 'gold.json', 'RAW/documents.json', 'RAW/manifest.json']:
        p=D/name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((PARENT/'artifacts/design'/name).read_bytes())
    gold=json.loads((D/'gold.json').read_text())
    inputs=json.loads((D/'inputs.json').read_text())
    inputs.append({'case_id':'GUARD','data_kind':'SYNTHETIC','turns':[
      {'goal':'G1','utterance':'내규에서 국내 법인 절차를 알려줘. 긴급 여부는 아직 몰라.'},
      {'goal':'G1','utterance':'긴급하지 않은 사건이라고 확인됐어. 그 조건을 반영해줘.'},
      {'goal':'G1','utterance':'방금 긴급하지 않다고 한 건 잘못이야. 긴급 사건으로 고쳐줘.'},
      {'goal':'G1','utterance':'그 정정도 잘못됐어. 긴급 여부는 아직 미확인이야. 미확인 상태로 되돌려줘.'},
      {'goal':'G1','utterance':'현재 긴급 여부와 판단을 조회해줘.'},
      {'goal':'G1','utterance':'같은 조건의 현재 경로로 다시 답해줘.','action':'reuse'}]})
    gold['GUARD']={'checkpoints':{'1':{'procedure':'B','urgent':None,'needs_check':None},'2':{'urgent':False,'needs_check':False},'3':{'urgent':True,'needs_check':True},'4':{'urgent':None,'needs_check':None},'5':{'urgent':None,'needs_check':None},'6':{'urgent':None,'needs_check':None}},'gold_sources':['MOCK-INTERNAL/main','MOCK-INTERNAL/exception'],'reuse_required':True}
    write(D/'inputs.json',inputs)
    gold['SEQ03']['required_execution']={'2':['PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE'], '3':['SELECT','ASSESS','COMPOSE']}
    for cid, spec in gold.items():
        if cid not in ('SEQ01','GUARD'):spec['checkpoints']['1']['urgent']=None
        spec['final_goal']='G1'
        spec['require_response_binding']=True
        spec['require_ready_envelope']=True
    write(D/'gold.json', gold)
    guards=[
      'explicit FOLLOW SELECT must execute SELECT ASSESS COMPOSE',
      'all seven explicit review entry stages execute their descendants',
      'pending ASSESS plus earlier PLAN correction must resume at PLAN',
      'restore without a retrieved original must CLARIFY without revision change',
      'restore values are derived from the referenced immutable original, not invented command values',
      'foreign-goal provenance must be rejected before mutation',
      'PRESENT with upstream edits must not bypass upstream recomputation',
      'INSPECT and REUSE return assessment route goal revision and actual retrieval',
      'unknown urgent is distinct from false; false/true/null survive composition',
      'wrong procedure or conditions in answer claims cannot publish',
      'answer text contradiction is detected; repair is bounded and recorded',
      'exhausted repair leaves no newly ACTIVE route and can resume',
      'answer source ids outside read/selection cannot publish',
      'final response ledger is bound to its consumed route, never the last other-goal search',
      'bad dependency/head coherence and stale revision cannot publish',
      'native journal failure rolls back chain node/head mutation',
    ]
    write(D/'guard-spec.json', {'data_kind':'SYNTHETIC','checks':guards,'kind':'deterministic adversarial contract tests with scripted model outputs; not model accuracy'})
    m=json.loads((ADR/'실험/manifest.json').read_text())
    pm=json.loads((PARENT/'실험/manifest.json').read_text())
    m['lineage']['hypothesis_delta']='Repair stage precedence, original provenance admission, response envelope, consumed-route accounting and semantic answer consistency; expand checks before new product calls.'
    m['design'].update(hypothesis='Explicit re-entry plus provenance/semantic publication contracts repair observed failures without losing long-chain restoration and current-route reuse.', primary_metric='Predeclared sequential feature checks and adversarial guard checks, separately counted', success_criteria='STRICT passes every expanded sequential check and adversarial check; all requested stage descendants run; zero wrong-goal/stale/unsupported publications; failures block publication rather than masquerading as success.', failure_criteria='Any expanded checkpoint or guard failure, accidental clarification of resolvable requests, wrong final text, stale source ownership, hidden repeat or production mutation.', criteria_frozen_before_run=True)
    m['design']['arms'][0].update(changes='Completed ADR0593 CHAIN ancestor, not rerun as baseline role', controls='Exact completed parent hashes preserved')
    m['design']['arms'][1].update(changes='Exact ADR0593 CHAIN code rerun under new expanded evaluator', controls='Same six sources, 43 utterances, Qwen3.8 and native repository; full history')
    m['design']['arms'][2].update(changes='Stricter stage/provenance/response/publication contracts, nullable urgent, product text verifier and at most one explicit answer repair', controls='Same frozen sources, utterances and native repository; no gold enters products')
    plan=copy.deepcopy(pm['design']['retrieval_stage_plan']['stages_by_arm']['CHAIN'])
    m['design']['retrieval_stage_plan']['stages_by_arm']={a:plan for a in ['baseline','PARENT','STRICT']}
    m['design']['planned_faults']=pm['design']['planned_faults']
    m['design']['limits']=['Local synthetic stage executor only; no production RAG API/Coordinator/GENOS wiring', 'Fixed goal/link/exact configuration reuse; no independent semantic wiki matching', 'No DB admin or legal approval; preservation and rejection contracts only', 'One in-sample 43-turn set per arm; no generalized quality certification', 'Product text verifier uses same model; an independent post-product evaluator records text drift and evaluator disagreement', 'One explicitly bounded compose repair; no model/provider fallback or hidden experiment reruns']
    m['runs'][0].update(arm_ids=['PARENT','STRICT'], selection_rule='Five parent sequences (43 turns) plus six-turn emergency-state sequence; alternate whole-arm order by case; one run. Deterministic adversarial contracts separately reported.', artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
    m['dataset'].update(name='synthetic-rag-chain-strict-contracts', version='r4-strict-v1', frozen_source=str((D/'inputs.json').relative_to(ROOT)), sha256=sha(D/'inputs.json'), legal_version_checked=True, reference_version_checked=True)
    m['llm_policy']['llm_calls']=[{'role':role,'class':cls,'model':'qwen/qwen3.8-27b','repeats':1,'temperature':0} for role,cls in [('resolve_select_assess_compose','product'),('command_text_verify_and_bounded_repair','product'),('post_product_text_audit','offline_evaluator')]]
    m['retrieval_accounting'].update(changed=True,corpus_total=6,not_applicable_reason=None)
    m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',not_applicable_reason=None)
    write(ADR/'실험/manifest.json',m)
    protected=json.loads((PARENT/'artifacts/design/baseline-binding.json').read_text())
    protected[str((PARENT/'실험/manifest.json').relative_to(ROOT))]=sha(PARENT/'실험/manifest.json')
    protected[str((PARENT/'artifacts/run-001/result.json').relative_to(ROOT))]=sha(PARENT/'artifacts/run-001/result.json')
    write(D/'baseline-binding.json',protected)
    write(D/'pre-code-design.json', copy.deepcopy(m))
    print(json.dumps({'sequences':6,'turns_per_arm':49,'guard_categories':len(guards)},ensure_ascii=False))

if __name__=='__main__': main()
