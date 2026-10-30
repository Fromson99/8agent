from common import *
import shutil,os
T=Path(__file__).parent;P=ROOT/'04_EXPERIMENTS/ADR/ADR-1184-model-absolute-deadline'
a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert a['generation']==114
r=read(ROOT/a['manifest_path']);C=ROOT/r['code_root'];assert all(sha(C/n)==h for n,h in r['files'].items())
put(DES/'baseline.json',{'pointer':a,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':r})
for n in ('cases.json','corpus.json','authorization.json','provider-policy.json'):put(DES/n,read(P/'artifacts/design'/n))
for p in (P/'artifacts/evaluation-only').glob('*.json'):put(ART/'evaluation-only'/p.name,read(p))
criteria={'hypothesis':'Exact selected MAIN114 can acquire required originals, review all request parts, and complete CM007; CM009 runs only after all CM007 integrity, completion, requirement-review and content gates pass.',
 'success_criteria':['HTTP200 READY; ANSWER/COVERED; supported claims; no material gaps; actual required originals both acquired and cited','All spans and ACL exact; physical requests equal reserved budget; no output cap; selected MAIN114 and all466 code hashes unchanged','Final ASSESS contains a bound requirement_review; current question parts and issues covered; no unresolved required items','Saved COMPLETE response equals returned text and assessment; offline content review against frozen reference and actual originals passes'],
 'failure_criteria':'Any source/ACL/code/budget discrepancy, missing required original, incomplete/incorrect final answer, resource stop or unknown model result stops conditional CM009; no automatic same-case rerun.',
 'per_case_budget':{'physical':40,'tools':1024,'seconds':1800,'output_cap':None},'order':['cm-007 once','cm-009 once only on all cm-007 gates'],
 'resource_policy':{'unchanged_from':'ADR1184','minimum_start_available_gib':5,'minimum_running_available_gib':3,'worker_rss_limit_gib':4,'address_space_limit_gib':6,'swap_growth_stop_mib':128,'minimum_workspace_free_gib':20},
 'scope':'Selected local service MAIN114; no product/guard changes, no promotion/GENOS, no stronger-model comparison; known cases in-sample, no legal quality certification',
 'content_review':'Offline agent review only after product finishes; must cover both markets quantity, caps and holding duration, and exceptions when applicable, using stored source version. No gold in product or correction input.',
 'outside_deadline_guard_seconds':1860,'allow_external':True,'request':'1번일단 진행해보'}
put(DES/'criteria.json',criteria)
put(DES/'user-authorization.json',{'request':'1번일단 진행해보','scope':'Prior item1: MAIN114 CM007 once then CM009 only if passes','session':os.environ.get('CODEX_THREAD_ID')})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='CM007 final-answer completion with original integrity and requirement coverage; conditional CM009',success_criteria=criteria['success_criteria'],failure_criteria=criteria['failure_criteria'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'selected','role':'candidate','derived_from':['ADR-1188-experiment-v1/reviewed'],'changes':'No product changes; actual selected MAIN114 service retest','controls':'Same question/data/65-document ACL/model/provider/budgets/resource guard'}])
m['runs'][0].update(arm_ids=['selected'],selection_rule='User selected CM007; CM009 conditional on first pass; once each',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='CM007 and conditional CM009',version='same stored CM source as ADR1184',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['retrieval_accounting'].update(changed=False,not_applicable_reason=None,stage_ledger={'mode':'recorded','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':'run-001','artifact_path':str((RUN/'retrieval-ledger.json').relative_to(ROOT)),'sha256':'PENDING','not_applicable_reason':None})
m['design']['retrieval_stage_plan']['stages_by_arm']={'selected':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
snapshot=ac.snapshot(ADR,'selected',list(r['files']),experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'])
for n,h in r['files'].items():
 p=snapshot/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(C/n,p)
ac.freeze(snapshot);assert not ac.validate(snapshot),ac.validate(snapshot)
c=read(snapshot/'candidate.json');v=c['revisions'][-1]
b={'manifest_path':str((snapshot/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(snapshot/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(b,candidate_id='selected',experiment_id=m['experiment_id'],arm_id='selected',run_ids=['run-001'],runner_path=str((T/'live.py').relative_to(ROOT)),runner_sha256=sha(T/'live.py'))])
m['design']['execution_note']='Snapshot provenance is identical to selected release. Actual native service imports the selected release, with all466 file hashes asserted; research files never enter product selection.'
put(ADR/'실험/manifest.json',m)
put(DES/'freeze.json',{'code_root':r['code_root'],'files':r['files'],'candidate_revision':b,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'inputs':{str(p.relative_to(ROOT)):sha(p) for p in DES.glob('*.json')},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in T.glob('*.py')}})
print('Frozen exact MAIN114/466; CM007 then conditional009; no product edits')
