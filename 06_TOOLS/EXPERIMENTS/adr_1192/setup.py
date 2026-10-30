from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
base=read(ROOT/active['manifest_path'])
assert active['generation']==115
criteria={
 'scope':'Final ASSESS/repair prompt implementation and deterministic delivery contracts only',
 'success':['Only MODERN_ASSESS_PROMPT, v8.PROMPT and dependent pins change from MAIN115',
 'Preserve actor/object/time/place, numeric base/unit/cap, exceptions and norm modality in visible claims',
 'Explicitly distinguish omitted wording in delivered sources from missing originals; use existing gaps only for real needs',
 'Initial and repair calls receive the same final content checks; no extra model stage, schema or repair allowance',
 'Actual native API with frozen code/pins passes supported/limited/repair-success/repair-failure and duplicate/storage checks',
 'Stored CM007 request reconstruction changes system instructions only, preserving user evidence, schema and routing',
 'No specific document/article/benchmark answer embedded; no working or active release change'],
 'failure':'Any non-prompt runtime change, source/schema/routing drift, extra call or contract regression rejects the candidate',
 'external_model_calls':0,'quality_certified':False,'performance_certified':False,
 'resources':{'max_parallel_heavy_processes':1,'min_available_GiB':5,'address_space_GiB':6},
 'failure_contract':{'class':'Semantic omission from model claims despite delivered evidence',
   'owner':'Existing ASSESS generation and single structural repair in CompletionExecution.assess',
   'automatic_semantic_correction':False,'new_validator':False,'new_retry':False,
   'preserved':'Existing source validation, partial response, investigation reentry, source goals, state and budget'},
 'limitations':['Synthetic responses do not establish improved model compliance or legal correctness',
   'Known generic stop_reason footer defect is a separate server change and remains',
   'No live CM007/009 run or model comparison; MAIN115 remains selected'],
}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in base['files']}})
m=read(ADR/'실험/manifest.json')
h='Explicit final claim-to-original scope checking may reduce omissions; this run verifies prompt delivery and unchanged contracts, not model efficacy.'
m['lineage']['hypothesis_delta']=h
m['design'].update(hypothesis=h,primary_metric='Prompt-only integrity and deterministic native delivery contract pass rate',
 success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,
 criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,
 arms=[{'id':'scoped','role':'candidate','derived_from':['ADR-1191-experiment-v1/selected'],
 'changes':'Modern assessment and v8 content prompts only','controls':'All MAIN115 runtime logic, data, schemas, model, routing and budgets unchanged'}])
m['dataset'].update(name='Synthetic final assessment contracts and stored CM007 request integrity',version='v1',
 frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['scoped'],selection_rule='Synthetic native API contracts and input-only reconstruction; no saved model response replay or new generation',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Prompt delivery contracts; no real retrieval benchmark or candidate selection change',stage_ledger={
 'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate',
 'artifact_path':None,'sha256':None,'not_applicable_reason':'Only synthetic API fixtures and stored request integrity; retrieval effect unmeasured'})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'scoped',list(base['files']),experiment_id=m['experiment_id'],arm_id='scoped',run_ids=['run-001'])
S=C/'snapshot'
for n,h in base['files'].items():
    assert sha(ROOT/base['code_root']/n)==h,n
    shutil.copyfile(ROOT/base['code_root']/n,S/n)
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
print(S)
