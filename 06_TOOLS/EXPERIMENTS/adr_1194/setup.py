from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(ROOT/active['manifest_path'])
assert active['generation']==115
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1192-final-answer-scope-prompt/artifacts/design/freeze-rev-001.json')
criteria={'scope':'User-authorized technical MAIN integration of final scope prompts and removal of unsupported generic limitation; no legal-quality certification',
 'success':['Only two approved prompt constants and generic no-gap stop limitation branch plus dependent pins change from MAIN115',
 'No gap means no fabricated unread scope; all material source/fact/version/subject gaps and explicit final assessment output-limit warning preserved',
 'Stop reason and original failure events remain; no retry, provider, budget, source, state, schema or retrieval change',
 'Prospective native API supported/limited/repair/duplicate/save contracts and existing regression preserve source and claims',
 'Exact frozen inventory is promoted and actual selected service verifies code, prompt, gap behavior, policy and mock HTTP',
 'Preserve concurrent/unrelated working changes; old stored publications still validate'],
 'failure':'Any new contract regression, lost material gap or claim/source, code drift or release mismatch blocks promotion',
 'external_model_calls':0,'quality_certified':False,'performance_certified':False,
 'resources':{'max_parallel_heavy_processes':1,'min_available_GiB':5,'address_space_GiB':6},
 'failure_contract':{'cause':'Server infers unknown legal scope solely from operational stop_reason', 'owner':'completion_contracts.refresh_limitations',
 'correction':'Remove only generic fallback; keep material gaps and explicit ASSESSMENT_OUTPUT_LIMIT warning',
 'preserved':'Raw failures, stop_reason, assessment/claim/source validation, retry budgets and stored rendering'},
 'known_case_replay':'ADR1193 saved output rendering only, separately in_sample diagnostic; not source of quality eligibility',
 'regression':'Same existing 211-case suite on MAIN115 and candidate; compare per-node outcomes, no new failures permitted'}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in base['files']}})
put(DES/'parent-freeze.json',parent)
m=read(ADR/'실험/manifest.json');h='Deterministic limitations reflect material gaps or explicit final review incompletion, while integrated final prompts preserve scope instructions through actual serving.'
m['lineage']['hypothesis_delta']=h
refs=m['integration']['parent_refs'];m['integration'].update(result_arm='integrated',rationale=h,
 common_invariants='All MAIN115 source, ACL, hash, state, provider, budgets and schemas preserved.',
 parent_contributions=[{'parent_ref':refs[0],'adopted':'All selected MAIN115 runtime/configuration and accumulated prior fixes','excluded':'None'},
 {'parent_ref':refs[1],'adopted':'Two final assessment prompt constants only','excluded':'In-sample quality/speed claims; candidate registry is never loaded by production'}],
 no_conflict_reason='1192 has identical MAIN115 code except two prompt constants and pins; new limitation branch removal is disjoint. Working journal_text cache hunk is preserved only in working checkout.')
m['design'].update(hypothesis=h,primary_metric='Technical integration contracts and exact release integrity; no model quality metric',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,
 arms=[{'id':'integrated','role':'candidate','derived_from':refs,'changes':'Two final prompts and no-gap generic limitation removal','controls':'MAIN115 model/data/routing/budgets/validators unchanged'}])
m['dataset'].update(name='Prospective deterministic limitation and native API contract matrix',version='v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Prospective synthetic contracts and identical existing regressions; known saved case kept as separate diagnostic',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Technical integration only; no retrieval benchmark',stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,'not_applicable_reason':'Synthetic API contract checks; no real retrieval effect evaluation'})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'integrated',list(base['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in parent['files'].items():
 assert sha(ROOT/parent['code_root']/n)==h,n
 shutil.copyfile(ROOT/parent['code_root']/n,S/n)
p=S/'02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py';t=p.read_text()
old="""    elif stop_reason and not items:
        items.append({'id': 'L-stop', 'kind': 'EXECUTION_LIMIT', 'issue_id': None,
                      'text': '확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.'})
"""
assert t.count(old)==1
p.write_text(t.replace(old,"    # An investigation stop is diagnostic history, not evidence of an unread scope.\n    # Preserve it below; user limitations require a material gap or incomplete final review.\n"))
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
print(S)
