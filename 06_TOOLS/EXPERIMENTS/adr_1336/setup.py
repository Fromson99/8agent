from common import *
import shutil,subprocess,runpy
DES.mkdir(exist_ok=False)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);assert active['generation']==141
wf=ROOT/'09_ARTIFACTS/AUDITS/20261104-workflow-review-followup';w=read(wf/'package-code.json');W=Path(w['code_root'])
assert all(sha(W/n)==h for n,h in w['files'].items())
assert read(wf/'package-checks.json')['passed']==73 and read(wf/'package-checks.json')['failed']==0
base=read(ROOT/'08_DEPLOYMENT/RELEASES/genos-oracle-startup-20261104-r1/release.json')
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
changes=[n for n,h in w['files'].items() if base['files'].get(n)!=h]
products=[n for n in changes if '/ENGINES/' not in n and n not in ('00_SYSTEM/PIPELINE.json','02_BACKEND/semantic_runtime/oracle_query_plans.py')]
assert len(changes)==43 and len(products)==11
assert all(release['files'][n]==base['files'][n] for n in products),'Unexpected product overlap between Gold and workflow'
put(DES/'baseline.json',{'pointer':active,'release':release,'working_files':{n:sha(ROOT/n) for n in release['files']},'gold_binding':read(gold/'binding.json'),'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.py','.json','.yaml')},'prior_validation':{'path':str((wf/'package-checks.json').relative_to(ROOT)),'sha256':sha(wf/'package-checks.json')},'product_changes':products,'workflow_source':w,'included':'MAIN141 Gold + completed1326 and the 2 workflow/review handoff changes','excluded':'Later1332 working delta and new model experiments1333/1335'})
criteria={'authorization':'User asked in related workflow thread to include that work with current MAIN141 Gold; received delegated coordination before this merge',
 'scope':'MAIN142 = MAIN141 Gold plus exact completed1326-based workflow handoff; no product invention or current1332 merge',
 'required':['All528 frozen files equal prepared/selected release','Gold product7 preserved exactly from MAIN141','Workflow product11 exact handoff bytes; no product overlaps with Gold','Native639 executable SQL/list/AST unchanged; regenerated source metadata/pins','Workflow owner verifies five frozen handoff suites73 on exact candidate; Gold prepared36contracts and Oracle1 pass','Fresh actual selected MAIN and Goldbinding check; source data and working tree unchanged','MAIN141 rollback and old Goldbinding preserved'],
 'failure':'Stop apply on validation, identity, ACL, hash or state failure; preserve logs and rollback selected release on entrypoint failure',
 'resource_limits':'Same ADR1334 Guard: startup5GiB available, runtime3GiB, worker4GiB, swap-growth128MiB, disk20GiB',
 'new_models':0,'field_deploy':False}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Combine disjoint completed Gold and workflow/review changes while preserving exact publication and source contracts'
m['design'].update(hypothesis='Gold and completed1326 workflow handoff have disjoint product changes and can share one exact selected release',primary_metric='Scoped contracts and exact serving binding',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for a in m['design']['arms']:a.update(changes='Inventory reference MAIN141' if a['id']=='baseline' else 'Workflow handoff product11 over MAIN141; rebuild native metadata and pins',controls='Gold product7, source generation, record format authority, models and budgets preserved')
m['integration'].update(result_arm='integrated',rationale=criteria['scope'],common_invariants='Exact original sources/ACL/hash/state; Gold B003 and S_1 choices; no model/field calls',conflicts=[],no_conflict_reason='Three-way comparison against MAIN140 finds product11 workflow changes disjoint from Gold product7; shared native metadata and pin manifests are regenerated without changing executable SQL',rollback_ref='ADR-1334-experiment-v1/integrated')
for p in m['integration']['parent_contributions']:
 p['adopted']='All MAIN141 Gold mapping and previous MAIN140 code' if '1334' in p['parent_ref'] else 'Completed1326 cumulative memory/review contract; exact verified handoff adds source folding/review explanation'
 p['excluded']='No field certification or quality inference; latest1332 changes excluded'
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Existing Gold and workflow consumer contracts; no legal answer evaluation',version='20261104-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(selection_rule='All frozen Gold36+Oracle1 and workflow73 suites; actual selected entrypoint checks',artifact_path=str((ART/'result.json').relative_to(ROOT)))
reason='Merge and release binding technical audit, no retrieval policy/quality comparison';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',list(release['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);C=can/'snapshot'
for n in release['files']:shutil.copyfile(ROOT/release['code_root']/n,C/n)
for n in products:shutil.copyfile(W/n,C/n)
sys.path.insert(0,str(ROOT/'06_TOOLS/maintenance'));import prepare_oracle_queries as pq
pq.ROOT=C;queries=pq.source_queries;pq.source_queries=lambda:queries(C);sys.argv=['prepare_oracle_queries.py'];pq.main()
with (ART/'rehash.log').open('x') as log:subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','--root',str(C),'rehash-engines','--apply'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
old=runpy.run_path(str(ROOT/release['code_root']/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS'];new=runpy.run_path(str(C/'02_BACKEND/semantic_runtime/oracle_query_plans.py'))['PLANS']
def sql(p):return {k:{a:b for a,b in v.items() if a!='sources'} for k,v in p.items()}
assert sql(old)==sql(new) and len(new)==639
ac.freeze(can);assert not ac.validate(can),ac.validate(can)
cm=read(can/'candidate.json');rev=cm['revisions'][-1];C=can/'revisions'/rev['revision_id']/'snapshot'
desc={'code_root':str(C.relative_to(ROOT)),'selected_files':{n:sha(C/n) for n in release['files']},'pin':{'manifest_path':str((can/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(can/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}}
assert all(sha(C/n)==w['files'][n] for n in products)
put(DES/'candidate-integrated.json',desc)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(desc['pin'],candidate_id='integrated',experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1336/run.py',runner_sha256=sha(Path(__file__).with_name('run.py')))])
put(ADR/'실험/manifest.json',m)
p=ROOT/'09_ARTIFACTS/AUDITS/20261104-workflow-review-main-coordination.txt'
with p.open('a') as out:out.write('\nADR1336 동결 후보 준비: '+str(C)+'\n해시목록: '+str(DES/'candidate-integrated.json')+'\n범위: 완료1326+메일워크플로우2수정,1332제외, MAIN141Gold 유지.\n워크플로우 담당은 이 경로에서 기존5suite73검사만 수행 후 별도 결과JSON/로그 경로를 이 파일에 추가해주세요. Gold37검사와 selection은 root가 수행하므로 중복하지 않습니다.\n')
print('Frozen merged528; workflow11 exact; Gold7 preserved; native639 same')
