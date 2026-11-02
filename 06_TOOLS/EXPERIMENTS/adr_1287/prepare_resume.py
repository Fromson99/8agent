"""Resume after missing historical summary path; original prepare failure is retained."""
from common import *
import subprocess
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1286-scenario-scope-contract-live/artifacts'
f=read(DES/'freeze.json');C=ROOT/f['code_root'];pin=f['candidate_revision']
b=read(DES/'baseline.json');p=b['pointer'];release=b['release'];pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
actual=read(prior/'run-001/result.json')
tech=ROOT/'04_EXPERIMENTS/ADR/ADR-1285-scenario-review-scope-contract/artifacts/verification.json'
criteria=read(DES/'criteria.json');m=read(ADR/'실험/manifest.json')
assert sha(pointer)==b['pointer_sha256'] and all(sha(ROOT/n)==h==sha(C/n) for n,h in f['files'].items())
assert read(tech)['status']=='TECHNICAL_PASS' and read(tech)['failed']==0
put(DES/'inherited-verification.json',{'technical':bind(tech),'actual':bind(prior/'run-001/result.json'),
 'code_identity_all527':True,'actual_status':actual['status'],'actual_claim_adoption':{'passed':1,'total':3,'low_quality_defects_remain':True},
 'quality_certified':False,'new_implementation':False})
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact selected code and consumer integrity, separate from model semantic quality',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['design']['arms'][0].update(changes='Preserved MAIN132 release',controls='Same source generation, Gold mapping, storage and model policy')
m['design']['arms'][1].update(changes='Already integrated cumulative scenario/review changes through ADR1285',controls='Exact ADR1286 tested code; no new behavior changes')
m['runs'][0].update(arm_ids=['selected'],selection_rule='Official serving closure and fresh consumer verification; no new quality benchmark',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Preserved source generation and synthetic service/scenario fixtures',version='20261102-main133',frozen_source=str((DES/'baseline.json').relative_to(ROOT)),sha256=sha(DES/'baseline.json'))
reason='Release selection and read-only ontology capability audit; no retrieval comparison'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str(Path(__file__).relative_to(ROOT)),runner_sha256=sha(__file__))]);put(ADR/'실험/manifest.json',m)
put(DES/'preview-authorization.json',{'purpose':'integration_preview'});put(DES/'preview-validation.json',{'structural_checks_passed':True,'quality_certified':False})
with (ART/'preview.log').open('x') as log:
 subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',release['data_path'],'--release-id',RELEASE+'-preview','--authorization',str(DES/'preview-authorization.json'),'--validation',str(DES/'preview-validation.json'),'--integration-preview',str(DES/'integration-preview.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
d=read(DES/'integration-preview.json');stage=dict(release['files'])
for row in d['changes']:
 assert row['after'] is not None and f['files'][row['path']]==row['after']
 stage[row['path']]=row['after'];row['reason']='Exact cumulative verified workspace: lossless case input, shared review links, typed scenario application and consumer display; known live limitations retained'
assert all(f['files'][n]==h for n,h in stage.items())
put(DES/'release-rebase.json',{'schema_version':'evaluated-release-rebase-v1','base_release_manifest_sha256':p['release_manifest_sha256'],'candidate':pin,'staged_files':stage,'excluded_candidate_paths':{n:'Auxiliary research/engine dependency outside official serving closure; retained unchanged' for n in set(f['files'])-set(stage)}})
d.update(candidate=pin,rebase_receipt=bind(DES/'release-rebase.json'));put(DES/'integration.json',d)
put(DES/'stage.json',{'files':stage,'count':len(stage),'changed':len(d['changes']),'added':[r['path'] for r in d['changes'] if r['before'] is None],'changes':d['changes']})
print({'frozen':len(f['files']),'serving':len(stage),'changed':len(d['changes']),'main132_still_selected':True})
