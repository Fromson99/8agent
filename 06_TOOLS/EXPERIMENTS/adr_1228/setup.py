from common import *
import shutil
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-1226-main122-authoring-revalidation'
technical=ROOT/'04_EXPERIMENTS/ADR/ADR-1227-source-first-authoring-semantics/artifacts'
checks=read(technical/'checks-rev003.json');fixed=read(technical/'checks-fixture-corrected.json')
assert checks['passed']==81 and checks['failed']==1 and fixed['passed']==1 and fixed['failed']==0
f=read(technical/'design/freeze-current.json');source=ROOT/f['code_root']
assert all(sha(source/n)==h for n,h in f['files'].items())
baseline=read(parent/'artifacts/design/baseline.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256']
assert all(sha(ROOT/n)==h for n,h in baseline['release']['files'].items())
put(DES/'baseline.json',baseline)
for n in ('cases.json','originals.json'):raw(DES/n,read(parent/'artifacts/design'/n))
put(ART/'evaluation-only/expectations.json',read(parent/'artifacts/evaluation-only/expectations.json'))
criteria=read(parent/'artifacts/design/criteria.json')
criteria.update(user_request='잘못된 판단 지지와 없는 이유·목적 원인 수정 후 실제 실험; 너무 하드코딩으로 바꾸지 말 것',hypothesis='Separating source interpretation from prior opinions reduces anchoring; binding selected actions/modality/conditions preserves it. Nullable recorded roles with actual raw evidence reduce invented rationale/purpose.',changes='Frozen ADR1227 rev003: source-only additional stage, request-only recorded role evidence and semantic selection assembly. No clause numbers, case IDs, expected legal answer or role-word whitelist in product.',maximum_physical_calls=9,maximum_stage_attempts=2,maximum_batch_seconds=1800,stop_rule='One frozen batch, max9physical including new source-analysis and repairs. Stop UNKNOWN/resource. A draft required for B accumulation; independent B normalization may run. No after-result prompt/code edits in this ADR.',historical_comparison='Known original two fragments from CM007; not full RAG CM007/009 or holdout. Same public5/source judgments2/glossary9, prior approval persists.')
criteria['success_criteria'] += ['SOURCE_ANALYSIS actual input contains no old opinion, normalized observation, glossary, previous graph or evaluation answer','Both records keep absent recorded reason/purpose absent','A condition-like bad opinion is not supported as correct; original acquisition-and-holding actions remain normative and no fabricated acquisition prerequisite','B retains corrected prior meaning and three implementing criteria; old observation retained in history','All model-selected semantic assembly values reverified against stored independent analysis; no hardcoded expected answer']
put(DES/'criteria.json',criteria);put(DES/'technical-binding.json',{'candidate':f,'checks':{'unique_passed':82,'initial_fixture_failure_preserved':True},'no_hardcoded_clause_or_answer':True})
m=read(ADR/'실험/manifest.json');pm=read(parent/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Two normalized records + two compiled drafts, absent roles and A error correction/B preservation reviewed separately',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')},execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1226-experiment-v1/main122'],'changes':'Stored MAIN122 actual result; no new baseline call','controls':'Same public sources, raw fragments and glossary/model policy'},{'id':'source-first','role':'candidate','derived_from':['baseline'],'changes':criteria['changes'],'controls':'Same canonical validators, source authority, original records; evaluation only kept private'}])
m['runs'][0].update(arm_ids=['source-first'],selection_rule=criteria['selection'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']=pm['llm_policy'];m['dataset']={**pm['dataset'],'frozen_source':str((DES/'cases.json').relative_to(ROOT)),'sha256':sha(DES/'cases.json')};m['retrieval_accounting']=pm['retrieval_accounting']
(ADR/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
files=sorted(set(baseline['release']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'})
C=ac.snapshot(ADR,'source-first',files,experiment_id=m['experiment_id'],arm_id='source-first',run_ids=['run-001'])
for n,h in f['files'].items():
 dest=C/'snapshot'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/n,dest)
 if n not in files:ac.register_file(C,n,upstream_state='absent');files.append(n)
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'candidate.json',{'code_root':str(code.relative_to(ROOT)),'files':{n:sha(code/n) for n in files},'candidate_revision':binding,'serving_files':489,'research_transport_files':1})
print('Candidate490 frozen; technical82 passed; maximum9physical, model0')
