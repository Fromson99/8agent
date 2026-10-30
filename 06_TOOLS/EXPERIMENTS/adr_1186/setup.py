from common import *
import shutil,subprocess
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline'
f=read(P/'artifacts/design/execution-binding-001.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path']);m=read(ADR/'실험/manifest.json');T=Path(__file__).parent
assert active['generation']==112
criteria={'scope':'Prospectively fixed technical integration audit, no legal-quality certification or new model call',
 'requirements':['Exact parent466 bytes and current MAIN112 source/data/model/budgets bound; no implicit unrelated promotion',
 'Cumulative source goals, repair separation, exclusion/containment, honest final answer, 429 routing and absolute deadline stay connected',
 'Only reviewed deltas merged into working code; independent storage edits preserved; engine pins reflect actual working bytes',
 'Same staged serving inventory verified by technical tests and native API; regression outcomes unchanged',
 'Official qualified prepare/apply selects new MAIN; actual selected service health and mock transport verified in ontology OFF/ON-unconfigured/ON-empty modes',
 'Previous MAIN112 retained for rollback; CM007/009 failures and resource stop preserved; no new live questions, GENOS deployment or legal quality claim'],
 'failure':'Any new source/ACL/state/deadline/budget regression, code binding drift or selected-service mismatch blocks or rolls back activation',
 'resource_policy':{'heavy_processes':1,'available_start_GiB':5,'available_running_GiB':3,'rss_limit_GiB':4,'address_space_GiB':6,'disk_min_GiB':20,'swap_growth_stop_MiB':128},
 'authorization':'일단 지금까지 한거 메인에 반영해 가치가 있어보여','new_model_calls':0}
put(DES/'criteria.json',criteria);put(DES/'parent-freeze.json',f)
paths=set(f['files'])|set(base['files'])
working={n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in paths}
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':working})
for n in ('cases.json','corpus.json','authorization.json','provider-policy.json'):
 put(DES/n,read(P/'artifacts/design'/n))
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'integrated',[n for n in f['files'] if (ROOT/n).is_file()],experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot';known={x['target_path'] for x in read(C/'candidate.json')['files']}
for n,h in f['files'].items():
 assert sha(ROOT/f['code_root']/n)==h,n
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['code_root']/n,S/n)
 if n not in known:ac.register_file(C,n,upstream_state='absent')
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1184').glob('test_*.py'):
 (T/p.name).write_text(p.read_text().replace('ADR-1184-model-absolute-deadline','ADR-1186-required-source-main-integration'))
# Preserve exact base and working variants for a narrow three-way integration.
changed=[n for n,h in f['files'].items() if base['files'].get(n)!=h]
for n in changed:
 if (ROOT/n).is_file():
  dst=ART/'working-backup'/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dst)
put(DES/'integration-plan.json',{'changed':changed,'serve_exclude':['02_BACKEND/lawrag/research/experiment_client.py'],'overlapping_working_edits':['02_BACKEND/semantic_runtime/legal_agent/completion_execution.py','02_BACKEND/semantic_runtime/legal_agent/output_contract.py'],'preserve':'Existing journal_text/reader integration; only candidate delta added','release_id':'source-contract-20261028-r1','expected_main':113})
m['lineage']['hypothesis_delta']='The cumulative verified source/response/deadline contracts can be integrated with MAIN112 and selected locally without source, state, budget or binding regressions.'
m['design'].update(hypothesis=m['lineage']['hypothesis_delta'],primary_metric='Technical invariants and exact selected serving binding',success_criteria=criteria['requirements'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'integrated','role':'candidate','derived_from':['ADR-1184-experiment-v1/bounded'],'changes':'MAIN112 integration and selected-service verification','controls':'Same parent product bytes, data/model/budgets; technical tests only'}])
m['dataset'].update(name='Synthetic technical integration fixtures; parent CM outcomes referenced only',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[];m['runs'][0].update(arm_ids=['integrated'],selection_rule='Prospective technical invariant and service binding checks; no legal evaluation or model calls',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Technical integration, no new legal retrieval benchmark',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,'not_applicable_reason':'No new legal retrieval benchmark'})
m['design']['retrieval_stage_plan']={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}}
put(ADR/'실험/manifest.json',m)
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
c=read(C/'candidate.json');v=c['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';files={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'execution_id':'rev-001','candidate_revision':binding,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
m=read(ADR/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path=str((T/'check.py').relative_to(ROOT)),runner_sha256=sha(T/'check.py'))]);put(ADR/'실험/manifest.json',m)
assert files==f['files']
print('Exact466 parent bytes reserved for MAIN integration; differences',len(changed))
