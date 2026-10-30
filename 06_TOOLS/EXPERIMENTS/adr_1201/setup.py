from common import *
import shutil
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1200-supervisor-recovery-live-cm007/artifacts/design/freeze-preflight-002.json')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);assert active['generation']==117
criteria={'hypothesis':'A separate final reviewer can detect relevant source content omitted or misrepresented in a completed answer, with independently validated source/answer references and durable single-review receipts.',
 'success_criteria':['Frozen candidate contracts and native publication/reuse tests pass without source/ACL/hash/budget changes','One reviewer sees full selected originals, exact final answer and original question; all offered sources and claims receive a status','Stored007 review detects known obligation/condition misclassification and bylaw15(5) omission without gold input','CM009 native API runs once regardless of previous007 semantic failure; source integrity, answer content and reviewer correctness are assessed separately'],
 'failure_criteria':'Unsupported/stale reviewer references, fabricated quotes, silent pass on incomplete reviewer or repeated unbounded review fail technical gates. Any actual missing or incorrect legal content fails the case content gate; no automatic same-case rerun.',
 'review_mode':'Advisory observation only; one logical review, no answer rewriting, no extra research/repair model; confirmed429 switch uses existing physical budget. Findings are returned and stored with exact answer/source binding. NO_ISSUES_FOUND is not quality certification.',
 'review_scope':'All selected originals supplied to final ASSESS, including unquoted parts; all returned claims. Does not claim completeness of unsearched corpus or excluded originals.',
 'order':['contracts and native API fixture','saved1200 CM007 final answer: one new reviewer request, no full007 rerun','CM009 once with reviewer regardless of saved007 review content result, unless infrastructure/integrity admission unsafe'],
 'known_cases':True,'in_sample':True,'quality_certified':False,'model':'qwen/qwen3.8-27b','provider':'ParasailFP8; confirmed429 NearAI once',
 'budget':{'per_live_case_physical':40,'tools':1024,'seconds':1800,'per_call_seconds':180,'output_cap':None,'standalone_saved_review_physical':2},
 'resources':{'same_as1200':True,'max_heavy_processes':1,'start_available_gib':5,'runtime_available_gib':3,'rss_limit_gib':4,'address_space_gib':6,'swap_growth_mib':128,'disk_free_gib':20},
 'main':'Unchanged MAIN117/GENOS; product integration only after technical checks, no active promotion',
 'user_request':'원문 마지막 다 들어갔는지 검토하는 ai하나 붙여보고 그리고9번도 돌려봐봐'}
put(DES/'criteria.json',criteria);put(DES/'baseline.json',{'pointer':active,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release,'parent':parent['candidate_revision'],'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in parent['files']}})
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1200-supervisor-recovery-live-cm007/artifacts'
for n in ('cases.json','corpus.json','authorization.json','provider-policy.json'):put(DES/n,read(old/'design'/n))
for p in (old/'evaluation-only').glob('*.json'):put(ART/'evaluation-only'/p.name,read(p))
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Final source coverage review accuracy and native009 integrity',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'reviewed','role':'candidate','derived_from':['ADR-1200-experiment-v1/recovered'],'changes':'Independent advisory final original-to-answer review','controls':'Same retrieval/recovery/ASSESS/content renderer/data/model/routing/budgets'}]);m['runs'][0].update(arm_ids=['reviewed'],selection_rule='Stored007 review once, native009 once unconditionally requested; no same-case retry',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Stored1200 CM007 plus native CM009',version='same frozen CM data and65-document ACL',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1},{'role':'final_original_review','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Frozen retrieval unchanged; native009 observed stages measured',stage_ledger={'mode':'measured','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((RUN/'retrieval-ledger.json').relative_to(ROOT)),'sha256':'PENDING','not_applicable_reason':None})
m['design']['retrieval_stage_plan']['stages_by_arm']={'reviewed':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'reviewed',list(parent['files']),experiment_id=m['experiment_id'],arm_id='reviewed',run_ids=['run-001'])
for n,h in parent['files'].items():
 assert sha(ROOT/parent['code_root']/n)==h,n
 shutil.copyfile(ROOT/parent['code_root']/n,C/'snapshot'/n)
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str((C/'snapshot').relative_to(ROOT))});print(C/'snapshot')
