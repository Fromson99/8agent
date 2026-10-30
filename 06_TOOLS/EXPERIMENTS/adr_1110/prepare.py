from pathlib import Path
import json,hashlib,sys,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1110-stable-review-runtime-binding';ART=ADR/'artifacts';OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1107-stable-judgment-navigation'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
c=read(OLD/'artifacts/design/criteria.json');c.update(frozen_at=datetime.now(timezone.utc).isoformat(),hypothesis='Repair native profile wiring, stable instructions, explicit new conflict and retained prior final review; same source/ACL/budgets and no automatic judgments.',changes=['allowlist3booleans and dependency guards','stable-v2 specific prompt','optional explicit CONFLICT for new review','preserve previous_final_review semantic content'])
c['primary']+=['Actual selected profile validation and full serving engine pins pass before model use.','Known145contracts plus real repository save/reserve and concurrent restart checks;4prior fixture-only failures excluded explicitly, not counted as passes.','One fresh fsc-hard-005 known failure question: inspect actual stable IDs, keyed judgments, correction/additional READ behavior, exact originals; semantic limited answer recorded separately. No automatic claim of improved legal quality or <=1second.']
c['model_run']={'cases':['fsc-hard-005'],'max_calls':40,'max_output_tokens':None,'wall_seconds':1800,'tool_limit':1024,'provider':'Parasail','model':'qwen/qwen3.8-27b','reasoning':'none','fallback':False,'selection':'Same public question as completed1086 failure; one prospective candidate only. Any failed source/binding or implementation stops; incomplete/limited semantic result reported, not hidden.'}
put(ART/'design/criteria.json',c);m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=c['hypothesis'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Actual runtime binding and preserved original action/review separation',success_criteria=c['primary'],failure_criteria='Source/ACL/hash, stale state, automatic legal finding, correction/budget bypass, startup or reference protocol failure.',criteria_frozen_before_run=True);m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None);m['dataset'].update(name='Stable recovery contracts and known fsc-hard-005 probe',version='v1',frozen_source=str((ART/'design/criteria.json').relative_to(ROOT)),sha256=sha(ART/'design/criteria.json'));m['llm_policy']['llm_calls']=[]
for a in m['design']['arms']:a.update(changes='Completed1107failure' if a['id']=='baseline' else c['changes'],controls='Same sources/model policy/ACL/budgets')
m['runs'].append({'id':'run-002','purpose':'followup','parent_run_id':'run-001','arm_ids':['integrated'],'selection_rule':'One prospectively frozen fsc-hard-005 fresh model only after contract acceptance; no response rewriting','status':'planned','artifact_path':'TODO','sha256':'PENDING'})
put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
f=read(OLD/'artifacts/design/freeze.json');P=ROOT/f['code_root'];new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('schema_preparation','stable_references','independent_read_recovery')]
C=ac.snapshot(ADR,'stable-runtime-r1',[n for n in f['files'] if n not in new],experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001','run-002']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(P/n)==h;shutil.copyfile(P/n,S/n)
for n in new:ac.register_file(C,n,upstream_state='absent')
AG=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(n,a,b):
 p=AG/n;t=p.read_text();assert t.count(a)==1,(n,a[:50]);p.write_text(t.replace(a,b))
edit('law_candidates.py',"'read_candidate_page_size': 20}","'read_candidate_page_size': 20, 'stable_navigation_references':False, 'new_read_reviews':False, 'independent_read_recovery':False}")
edit('law_candidates.py',"'read_judgment','minimal_input'))", "'read_judgment','minimal_input','stable_navigation_references','new_read_reviews','independent_read_recovery'))")
edit('law_candidates.py',"    if result['read_judgment'] and", "    if result['stable_navigation_references'] and not result['minimal_input']:raise ContractError('stable references require minimal input')\n    if result['new_read_reviews'] and (not result['read_judgment'] or not result['stable_navigation_references']):raise ContractError('new reviews require stable references and read judgment')\n    if result['independent_read_recovery'] and not result['new_read_reviews']:raise ContractError('independent read recovery requires new reviews')\n    if result['read_judgment'] and")
edit('navigation_input.py',"OPAQUE=re.compile", "STABLE_INSTRUCTIONS=INSTRUCTIONS.replace('선택 ID는 이 화면에만 유효한 짧은 문자열이다.', '문서·판단·근거·선택 ID는 이 조사 동안 같은 대상을 가리키며 화면이나 재개 시 바뀌지 않는다.')\nOPAQUE=re.compile")
edit('gateway.py',"from .navigation_input import NavigationReferences, INSTRUCTIONS", "from .navigation_input import NavigationReferences, INSTRUCTIONS, STABLE_INSTRUCTIONS")
edit('gateway.py',"            numbered_instructions=INSTRUCTIONS", "            numbered_instructions=STABLE_INSTRUCTIONS if references.stable else INSTRUCTIONS")
edit('bounded_source_session.py',"from .navigation_input import NavigationReferences, INSTRUCTIONS", "from .navigation_input import NavigationReferences, INSTRUCTIONS, STABLE_INSTRUCTIONS")
edit('bounded_source_session.py',"instructions='\\n'+INSTRUCTIONS+' text_ref", "instructions='\\n'+(STABLE_INSTRUCTIONS if references.stable else INSTRUCTIONS)+' text_ref")
edit('read_judgment.py',"r['properties'].pop('operation');r['required'].remove('operation')", "r['properties']['operation']={'enum':['SET','CONFLICT']};r['required'].remove('operation')")
edit('read_judgment.py',"if kind=='new_reviews':row['operation']='SET'", "if kind=='new_reviews':row.setdefault('operation','SET')")
edit('compact_model_input.py',"'material','seen_material','originals','previous_final_review'}", "'material','seen_material','originals'}")
for name in ('test_preparation.py','test_stable_recovery_isolated.py','test_output_contract_local.py'):
 shutil.copyfile(ROOT/'06_TOOLS/EXPERIMENTS/adr_1107'/name,Path(__file__).parent/name)
# Freeze the exact known public question rather than an answer or evaluator context.
old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1086-nonexistent/실험/manifest.json') if False else None
source=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1093-nonmodel-residual-profile/artifacts/design/freeze.json');ref=source['request'];import gzip
p=ROOT/ref['path'];assert sha(p)==ref['sha256'];req=json.loads(gzip.decompress(p.read_bytes())) if p.suffix=='.gz' else read(p)
put(ART/'design/case.json',{'id':'fsc-hard-005','request':req,'source':ref});put(ART/'design/baseline.json',{'pointer':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':read(ROOT/'08_DEPLOYMENT/RELEASES/compact-input-20261027-r1/release.json')})
print(S)
