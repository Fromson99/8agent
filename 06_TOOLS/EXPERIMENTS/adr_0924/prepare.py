from pathlib import Path
import datetime, hashlib, json, shutil, subprocess, sys, tempfile

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff'
D=A/'artifacts/design'
P=R/'04_EXPERIMENTS/ADR/ADR-0922-term-phrase-current-reference'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

assert not (D/'criteria.json').exists()
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(R/pointer['manifest_path'])
parent=read(P/'artifacts/design/normalized-binding.json')
baseline=R/release['code_root'];previous=R/parent['code_root']
criteria={
 'hypothesis':'Bound verified unread leads survive child source return and enter the existing parent item review/research; source-versus-hint projection preserves original delivery and A+B reconsideration without an adoption gate.',
 'required':['Normalized document-bound exploration and persistent reference anchors are retained on the current working-code basis.',
 'Unread reference/term leads are separately serialized, hash/scope checked, visible in parent ITEMS and selectable as exact research locators.',
 'A child may return incomplete originals; the parent may read B and jointly judge A+B without forced legal applicability or read-all completion.',
 'Old v1 returns remain valid; new v2 producer/consumer, replay, partial failures, duplicate budgets and saved consumers agree.',
 'Synthetic source/ACL/hash/state/preview-as-evidence violations are rejected; changed leads cause a new review input but identical leads do not.',
 'One actual known workflow per arm is fully recorded; legal interpretation errors and incomplete internal comparison are separate findings.'],
 'failure':['Forged/unread preview accepted as evidence','Unverified locator executed','Loss of read originals on uncertainty or source return','Budget reset, duplicate side effects or stale version accepted'],
 'controls':'Both arms use current working serving code plus the seven completed ADR0922 product changes; only bridged arm adds the planned lead handoff/parent review and display changes. Current unrelated changes preserved and fingerprinted.',
 'selection':'One known leverage query once per arm, baseline then bridged; deterministic synthetic contracts are frozen before execution. No adaptive live retry. Known clauses remain in offline audit only.',
 'limits':{'model_attempts_per_request':40,'wall_seconds':1800,'workers':1,'rss_gib':6,'as_gib':8,'min_available_gib':4,'min_disk_gib':10},
 'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fallback':False,
 'in_sample':True,'decision_eligible':False,'main_changed':False,'genos_executed':False,
 'failure_owner':'Gateway owns transport retries; native bounded_decision and parent model adapter own their schema repairs. Semantic uncertainty returns originals/leads without retry. Lead hash/ACL/revision failures fail closed. Parent research uses existing stable acquisition keys and original deadline.',
 'design_report':{'path':'07_DOCS/REFERENCE/REPORTS/CONNECTED_SOURCE_SELECTION_DESIGN_20261019/PLAN.txt','sha256':sha(R/'07_DOCS/REFERENCE/REPORTS/CONNECTED_SOURCE_SELECTION_DESIGN_20261019/PLAN.txt')},
 'promotion':'This known-case probe is not a promotion source. Any later MAIN qualification requires a new separately frozen eligible ADR.'}
put(D/'criteria.json',criteria)
put(D/'baseline.json',{'pointer':pointer,'manifest':release})
shutil.copy2(P/'artifacts/design/cases.json',D/'cases.json')
put(D/'parent-binding.json',parent)
files=set(release['files'])
for folder in ('02_BACKEND/semantic_runtime','02_BACKEND/workflow'):
    files.update(str(p.relative_to(R)) for p in (R/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.json') and '__pycache__' not in p.parts)
files={n for n in files if (R/n).is_file()}
put(D/'working-before.json',{n:sha(R/n) for n in sorted(files)})
put(D/'working-drift.json',[{'path':n,'active':release['files'].get(n),'working':sha(R/n)} for n in sorted(files) if release['files'].get(n)!=sha(R/n)])
m=read(A/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Verified lead delivery and native parent research with preserved source/state contracts',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0922-experiment-v1/normalized'],'changes':'Current working-code rebase of completed normalized candidate','controls':criteria['controls']},{'id':'bridged','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':criteria['controls']}]
m['runs'][0].update(arm_ids=['baseline','bridged'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='known-leverage-parent-handoff',version='20261019-v1',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'workflow_and_native_rag','class':'product','model':criteria['model'],'max_calls':80,'repeats':2,'temperature':0}]
stages=read(P/'실험/manifest.json')['design']['retrieval_stage_plan']['stages_by_arm']['normalized']
m['design']['retrieval_stage_plan']['stages_by_arm']={arm:stages for arm in ('baseline','bridged')}
m['retrieval_accounting'].update(changed=True,not_applicable_reason='Known source targets stay offline; exact read/return/cited ledger and separate candidate delivery trace; no approved complete legal gold.')
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),sha256='PENDING',not_applicable_reason=None)
put(A/'실험/manifest.json',m)
products=['connected_exploration.py','law_navigation.py','decision_projection.py','source_investigation.py','request_repair.py','tool_availability.py','tool_policy.py']
merges=[]
for arm in ('baseline','bridged'):
    cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',arm,'--experiment-id',m['experiment_id'],'--arm-id',arm,'--run-id','run-001']
    for name in sorted(files):cmd+=['--source',name]
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
    C=R/'02_BACKEND/lawrag/research/candidates/adr_0924'/arm;S=C/'snapshot'
    for name in products:
        rel='02_BACKEND/semantic_runtime/legal_agent/'+name;dest=S/rel
        if not (R/rel).exists():
            shutil.copy2(previous/rel,dest)
            subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',rel,'--upstream-state','absent'],check=True,stdout=subprocess.DEVNULL)
            method='new-from-parent'
        else:
            merged=subprocess.run(['git','merge-file','-p',str(R/rel),str(baseline/rel),str(previous/rel)],capture_output=True)
            assert merged.returncode==0,(rel,merged.stderr.decode(),merged.stdout.decode())
            dest.write_bytes(merged.stdout);method='three-way-current-active-parent'
        merges.append({'arm':arm,'path':rel,'method':method,'merged_sha256':sha(dest),'working_sha256':sha(R/rel) if (R/rel).exists() else None,'parent_sha256':sha(previous/rel)})
put(D/'merge.json',merges)
put(D/'serving-files.json',sorted(files|{'02_BACKEND/semantic_runtime/legal_agent/connected_exploration.py'}))
print('Frozen design; both current-based isolated snapshots created. No product files changed.')
