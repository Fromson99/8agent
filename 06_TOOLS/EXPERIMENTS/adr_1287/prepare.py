"""Freeze the already integrated and tested workspace; no product edits."""
from common import *
import subprocess
DES.mkdir();OUT.mkdir()
prior=ROOT/'04_EXPERIMENTS/ADR/ADR-1286-scenario-scope-contract-live/artifacts'
f=read(prior/'design/freeze.json');actual=read(prior/'run-001/result.json')
tech=ROOT/'04_EXPERIMENTS/ADR/ADR-1285-scenario-review-scope-contract/artifacts/run-001/result.json'
assert actual['status']=='NOT_PASSED' and actual['physical_calls']==8
assert len(f['files'])==527 and all(sha(ROOT/n)==h for n,h in f['files'].items())
pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';p=read(pointer);release=read(ROOT/p['manifest_path']);assert p['generation']==132
put(DES/'baseline.json',{'pointer':p,'pointer_sha256':sha(pointer),'release':release,
 'gold_binding':read(GOLD/'binding.json'),'gold_files':{str(x.relative_to(ROOT)):sha(x) for x in GOLD.iterdir() if x.is_file()}})
criteria={'hypothesis':'The exact completed cumulative workspace can be selected with preserved source, permissions, storage, rollback and actual API consumers; inspect ontology boundaries without claiming semantic quality.',
 'success':['Working and frozen527 files match completed ADR1285/1286','Official complete serving closure and prepared API13 plus scenario API7 pass','Actual root and maintained Gold connector select the same MAIN133','Original data/mapping/settings and Oracle layout4 reader retained','Known live failures remain NOT_PASSED and ontology proposals remain unimplemented'],
 'failure':['Unverified code or new consumer regression','Source, ACL, state, data or mapping identity failure','Treating failed live results as quality certification'],
 'authorization':'일단 지금가지 한거 메인에 반영해 그리고 남은거 한번확인해봐 한계점이 명확한 부분ㅇ느 우리 온톨로지로 해결할수 이쓴지 봐봐고',
 'quality_certified':False,'new_model_calls':0,'oracle_calls':0,'genos_deployed':False,
 'rollback':'Official MAIN132 rollback and preserved Gold binding together; retain layout4 and all history'}
put(DES/'criteria.json',criteria)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
m=read(ADR/'실험/manifest.json')
S=ac.snapshot(ADR,'selected',sorted(f['files']),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001']);ac.freeze(S);assert not ac.validate(S)
rev=read(S/'candidate.json')['revisions'][-1];C=S/'revisions'/rev['revision_id']/'snapshot'
pin={'manifest_path':str((S/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(S/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(C.relative_to(ROOT)),'files':f['files'],'candidate_revision':pin,'pointer_sha256':sha(pointer)})
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
