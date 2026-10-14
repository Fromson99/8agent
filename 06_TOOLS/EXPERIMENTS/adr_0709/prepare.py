"""Prospective, unchanged-code qualification of the completed title entry candidate."""
from pathlib import Path
import hashlib,json,sqlite3,shutil,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0709-grounded-entry-main-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run(*args):subprocess.run([str(R/'.venv/bin/python'),*map(str,args)],cwd=R,check=True)
assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==48
base=read(R/pointer['manifest_path'])
for name,h in base['files'].items():assert sha(R/name)==sha(R/base['code_root']/name)==h,name
put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':base})
criteria={'scope':'Byte-identical completed ADR0707 title-entry, including fused entry and selectable structure/fulltext, against selected MAIN48. No new recovery policy or difficulty routing.',
 'required':{'requests':6,'minimum_candidate_supported':2,'candidate_supported_at_least_baseline':True,'no_paired_supported_regression':True,'all_successful_citations_verified':True,'public_scope_only':True,'actual_binding_valid':True,'approved_judgment_and_gap_state_valid':True,'raw_diagnostics_in_public_zero':True,'new_contract_regressions_zero':True,'same_code_to_release':True,'unseen_primary_roots':True,'physical_call_accounting':True},
 'execution':{'arms':['baseline','integrated'],'case_order':['H01','H02','H03'],'arm_order':'H01 baseline,candidate; H02 candidate,baseline; H03 baseline,candidate. One fresh-process request per arm/case, no adaptive retries or case replacement.', 'model':'qwen/qwen3.8-27b','provider':'Parasail','quantization':'fp8','reasoning':'none','fallback':False,'calls_per_request':40,'output_tokens':6400,'wall_seconds':1800},
 'semantic_gate':'Detailed legal interpretation mistakes recorded separately per user instruction; citation/access/state/hash/service integrity remain blocking. Supported means original-backed response, not full legal correctness.',
 'performance_gate':'Record all attempts, tokens, per-call and E2E time, failures included. No absolute speed gate or general speed claim on three questions. Paired supported response non-regression is required.',
 'known_failure':'ADR0708 repeated rejected RESEARCH proposals remain unresolved. The model saw the error and read tools; no recovery improvement is claimed by this promotion.',
 'rollback':'Before activation preserve MAIN48 on failure. After activation rollback for citation/access/state/hash/service selection violations. Worktree backups separate from pointer rollback.',
 'authorization':'User explicitly requested current completed work be reflected in MAIN; no renewed permission needed after gates pass.'}
put(D/'criteria.json',criteria)
selection=[('H01','article:daa4ab18da6597e43495ceea','EXACT_TITLE','금융지주회사법 제3조 제3항의 구조를 설명해 주세요. 인가에 조건을 붙일 수 있는 경우와 붙여야 하는 경우를 원문 범위에서 구분해 주세요.'),
 ('H02','article:e74730011aee7108e3692135','SHORT_TITLE','개인정보법 제7조의12에서 소위원회의 구성 인원, 의결 요건, 의결의 효력을 설명해 주세요.'),
 ('H03','article:f09e3f706896efca358585f4','BODY_DETAIL','외국환평형기금 채권의 원리금은 어떤 재원으로 상환할 수 있고, 그 재원으로 상환할 수 있는 금액은 어떻게 계산하나요?')]
excluded=set(read(D/'excluded-source-ids.json'));assert not read(D/'exposure-scan.json')['failures']
allowed=set(read(R/base['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db=sqlite3.connect((R/base['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True);cases=[];gold=[]
for cid,sid,kind,question in selection:
 assert sid not in excluded,sid
 s=json.loads(db.execute('select json from source where id=?',(sid,)).fetchone()[0]);assert s['document_id'] in allowed
 cases.append({'case_id':cid,'kind':kind,'question':question})
 gold.append({'case_id':cid,'source_id':sid,**{k:s[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}})
db.close()
put(D/'dataset.json',{'cases':cases,'regression_cases':[],'product_gold':False,'source_generation':base['data_path']})
put(D/'gold.json',{'product_visible':False,'version':'Pinned local originals; no current-law certification','cases':gold})
put(D/'selection-audit.json',{'primary_roots':[x[1] for x in selection],'prior_excluded':len(excluded),'no_overlap':True,'selection_before_model_results':True,'coverage':'Three public documents; exact title + paragraph, shortened title + article, body details without statute title. No private CM inputs.'})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric='Same-code critical invariants and supported completion non-regression; all physical call costs recorded',success_criteria=criteria['required'],failure_criteria='Any required check fails; preserve MAIN48',criteria_frozen_before_run=True,repeats=1)
for a in m['design']['arms']:a.update(changes='Selected MAIN48' if a['id']=='baseline' else 'Exact completed0707 title-entry including0706 fused front',controls='Same approved65 documents, source generation, Qwen/Parasail policy, budgets and input; new process/runtime')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
m['dataset'].update(name='Three unseen public statute roots for entry integration',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule=criteria['execution']['arm_order'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
stages=[{'stage_id':'catalogue','kind':'source','parent_stage_ids':[]},{'stage_id':'recall','kind':'retrieve','parent_stage_ids':['catalogue']},{'stage_id':'acquired','kind':'select','parent_stage_ids':['recall']},{'stage_id':'presented','kind':'present','parent_stage_ids':['acquired']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a['id']:stages for a in m['design']['arms']}
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
parent=R/'02_BACKEND/lawrag/research/candidates/adr_0707/title-entry';pcm=read(parent/'candidate.json');ps=parent/'revisions/rev-001/snapshot'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0709/integrated';paths=sorted({f['target_path'] for f in pcm['files']}|set(base['files']))
cmd=['06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',A,'--candidate-id','integrated','--experiment-id',m['experiment_id'],'--arm-id','integrated','--run-id','run-001']
for name in paths:
 if (R/name).is_file():cmd+=['--source',name]
run(*cmd)
for name in paths:
 src=ps/name;dst=C/'snapshot'/name
 assert src.is_file(),name
 if not dst.is_file() or sha(dst)!=sha(src):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 if not (R/name).exists():run('06_TOOLS/run_tool.py','adr_candidate.py','register',C,'--target',name,'--upstream-state','absent')
for row in pcm['revisions'][0]['files']:
 name=Path(row['frozen_path']).relative_to(ps.relative_to(R));assert sha(R/row['frozen_path'])==sha(C/'snapshot'/name)==row['snapshot_sha256']
put(D/'parent-code.json',{'parent':str(parent.relative_to(R)),'manifest_sha256':sha(parent/'candidate.json'),'same_files':len(paths),'all_bytes_identical':True})
for name,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/name,v)
print('Prospective criteria fixed; three unexposed public roots; candidate code unchanged; no model calls')
