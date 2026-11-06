from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
DES.mkdir(exist_ok=False)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==151
base=ROOT/release['code_root'];files=release['files']
assert all(sha(base/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':active,'release':release,'working_files':{n:sha(ROOT/n) for n in files}})
criteria={'authorization':'구현해봐 쭉 그리고 실험해보고 메인에 반영까지 해줘',
 'hypothesis':'One navigation decision offers READ/FOLLOW/SEARCH/ASK_USER/ANSWER, pauses without another review when user facts or scope are needed, preserves original shortages and output failures, and resumes/records confirmed experience through the existing memory.',
 'success':['Actual offered-target and original-span validation, ACL, binding and revision checks remain intact.',
 'ASK_USER is reachable before any read and after reads; no final generation or research continues after asking.',
 'Known missing originals remain material until acquired or explicitly excluded with original evidence; no COVERED/confirmation from silence.',
 'Malformed final output remains a technical failure, not a fabricated SCOPE/FACT question; UNKNOWN never retried.',
 'User facts resume the same paused investigation with originals and history preserved; identical requests add no calls.',
 'Unresolved/failure answers cannot become confirmed knowledge; resolved and confirmed experience can be reused with conditions/ACL/version checks.',
 'Candidate and selected local service contract checks pass, with baseline failures separately measured.'],
 'failure':['New source/ACL/hash/state/budget regression','Lost source shortage or false knowledge confirmation','Unrecorded calls or post-UNKNOWN sends'],
 'live':{'cases':['cm-003','cm-018'],'scope':'financial cm public documents only; natural language fact/scope followup and confirmation/reuse when preceding stage permits',
 'control':'MAIN151 baseline and frozen candidate; no gold in model inputs; source/semantic findings manually reviewed separately',
 'max_physical_calls':40,'max_reported_cost_usd':2,'timeout_seconds_per_call':180,'stop_on_unknown':True,'max_output_tokens':None,
 'model':'qwen/qwen3.8-27b','provider_policy':'current Parasail FP8; preexisting known-429 switch only','legal_quality_certified':False},
 'resources':{'heavy_processes':1,'min_available_GiB':4,'max_swap_growth_MiB':128},
 'deployment':'User-directed local MAIN after source/state/API checks; preserve failures and rollback, do not claim general legal certification or GENOS deployment.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Pause/resume/shortage/knowledge contract correctness and observed real model task completion',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['dataset'].update(name='Financial CM003 and CM018; synthetic lifecycle and failure contracts',version='guided-navigation-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
for a in m['design']['arms']:a.update(changes='Selected MAIN151' if a['id']=='baseline' else criteria['hypothesis'],controls='Same source generation, ACL and model policy; isolated runtime and frozen code')
m['runs'][0].update(selection_rule='Preselected CM003 and CM018, sequential baseline/candidate; lifecycle followups only after prerequisite success; stop after UNKNOWN',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'guided',list(files),experiment_id=m['experiment_id'],arm_id='guided',run_ids=['run-001'])
for n in files:shutil.copyfile(base/n,can/'snapshot'/n)
put(DES/'mutable-candidate.json',{'path':str(can.relative_to(ROOT)),'files':list(files),'new_files':['02_BACKEND/semantic_runtime/legal_agent/guided_navigation.py']})
put(DES/'candidate-baseline.json',{'code_root':release['code_root'],'selected_files':files})
print(can/'snapshot')
