from pathlib import Path
import json,hashlib,sys,subprocess
from datetime import datetime,timezone
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0774/source-gap-action'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
criteria=read(D/'criteria.json');criteria['matrix']['single_kinds']=['MISSING_SCOPE','UNREAD_SAVED','MISSING_SOURCE','UNRESOLVED_REFERENCE','WRONG_SUBJECT','MISSING_FACT','VERSION_AMBIGUOUS'];criteria['prefreeze_note']='Canonical enum transcribed before any audit calls. No product change or result-driven selection.'
criteria['regression_suites']=['test_assessment_gap_action.py','test_main50_request_repair.py','test_focused_input_modality.py','test_single_rule_content.py','test_source_span_norm.py','test_narrative_answer.py','test_judgment_loop_recovery.py','test_wire_repair.py','test_public_display_boundary.py','test_genos_model_stream_completion.py','test_successful_shortcut.py','test_successful_core_routes.py','test_bounded_wiki_recall.py']
put(D/'criteria.json',criteria)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
base=read(D/'baseline.json');cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
fullbinding={**binding,'candidate_id':'source-gap-action','arm_id':'source-gap-action','experiment_id':'ADR-0774-experiment-v1','run_ids':['run-001'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_0774/audit.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0774/audit.py')}
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.control import prepare
put(D/'preview-authorization.json',{'purpose':'integration_preview'});put(D/'preview-validation.json',{'structural_checks_passed':True})
prepare(R,code,R/base['manifest']['data_path'],'assessment-gap-action-frozen-preview',D/'preview-authorization.json',D/'preview-validation.json',D/'integration-draft.json')
integration=read(D/'integration-draft.json');integration['candidate']=binding
for row in integration['changes']:row['reason']='Only reviewed 3-source gap action normalization and corresponding engine/Pipeline pins; every other MAIN59 file unchanged.'
files=dict(base['manifest']['files'])
for row in integration['changes']:
 if row['after'] is None:files.pop(row['path'])
 else:files[row['path']]=row['after']
for name,h in files.items():assert sha(code/name)==h,name
rebase={'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':base['pointer']['release_manifest_sha256'],'candidate':binding,'staged_files':files,'excluded_candidate_paths':{x['target_path']:'Synthetic contract fixture, not served' for x in cm['files'] if x['target_path'] not in files},'reviewed_changes':integration['changes'],'base_code_root':base['manifest']['code_root'],'stage':str(code.relative_to(R)),'reason':'Prior unit-tested fix qualified as exact MAIN59 integration. No new product changes in ADR; exhaustive audit plus regressions.'}
put(D/'release-rebase.json',rebase);ref={'path':str((D/'release-rebase.json').relative_to(R)),'sha256':sha(D/'release-rebase.json')};integration['rebase_receipt']=ref;put(D/'integration.json',integration)
from semantic_runtime.release_integration import check
check(R,{'pointer':base['pointer'],'pointer_sha256':base['pointer_sha256']},files,integration)
m=read(A/'실험/manifest.json');m['dataset']['sha256']=sha(D/'criteria.json');m['design']['code_isolation']['candidates']=[fullbinding];m['design']['release_rebase']=ref;put(A/'실험/manifest.json',m)
paths=list((R/'06_TOOLS/EXPERIMENTS/adr_0774').glob('*.py'))+list(D.glob('*.json'))+[C/'candidate.json',R/'00_SYSTEM/WORKSPACE.json',R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json']
frozen={str(p.relative_to(R)):sha(p) for p in paths};frozen.update({str((code/x['target_path']).relative_to(R)):sha(code/x['target_path']) for x in cm['files']})
put(D/'freeze.json',{'frozen_at':datetime.now(timezone.utc).isoformat(),'code_root':str(code.relative_to(R)),'files':frozen,'serving_files':files,'candidate':binding})
print('Frozen',len(files),'serving files; changes',len(integration['changes']))
