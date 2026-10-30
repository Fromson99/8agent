from common import *
import shutil,sys
T=Path(__file__).parent;P=ROOT/'04_EXPERIMENTS/ADR/ADR-1167-supervisor-route-identity';O=ROOT/'04_EXPERIMENTS/ADR/ADR-1166-investigation-supervisor'
parentf=read(P/'artifacts/design/freeze.json');m=read(ADR/'실험/manifest.json');assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==parentf['pointer_sha256']
for n in ('baseline.json','cases.json','corpus.json','authorization.json'):put(DES/n,read(O/'artifacts/design'/n))
auth=read(DES/'authorization.json');auth.update(user_request='다시해봐',scope='Exact ADR1167 repaired candidate on MAIN112; CM001/007/009 once each sequentially; no promotion; no lightweight fallback',max_model_calls=120);put(DES/'authorization.json',auth)
put(ART/'evaluation-only/cases.json',read(O/'artifacts/evaluation-only/cases.json'))
from resource_guard import sample,self_test
put(DES/'resource-observation.json',{'at_freeze':sample(),'prior_observation':'Swap residual about3.55GiB but vmstat interval si/so0, memory PSI0, available5.36GiB; unrelated processes untouched. Admission requires5GiB, continuous minimum3GiB; prior frozen record not changed.','guard_unit_checks':self_test()})
criteria=read(O/'artifacts/design/criteria.json');criteria.pop('live_fallback',None)
criteria.update(hypothesis='Same repaired supervisor code as1167 can guide actual CM001/007/009 source investigation and final publication with dynamic resource admission.',resource={'startup_available_bytes':5*1024**3,'min_mem_available_bytes':3*1024**3,'max_rss_bytes':4*1024**3,'address_space_limit_bytes':6*1024**3,'max_swap_growth_bytes':128*1024**2,'memory_full_psi_avg10_max':1.0,'min_disk_bytes':20*1024**3,'sample_interval_seconds':1,'runtime':'workspace disk; no unrelated process or file cleanup','unknown_provider_outcome':'stop without retry, cancellation unconfirmed'},failure='Stop batch on source/ACL/output-cap integrity error, resource violation, internal contract error or unknown provider outcome. Each question at most once. Ordinary bounded incomplete answer retained and next question may run. No fallback or evaluator calls.',parent_technical='1167 exact459 files,31 passed checks inherited; 8 new experiment guard checks; no new product edits.')
put(DES/'criteria.json',criteria)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria,arms=[{'id':'supervised','role':'candidate','derived_from':['ADR-1167-experiment-v1/repaired'],'changes':'Product bytes unchanged; dynamic host-resource admission experiment only','controls':'MAIN112 data/model/budgets preserved; no gold in product'}])
m['runs'][0].update(arm_ids=['supervised'],selection_rule='Known CM001/007/009 once each; sequential; no fallback; stop on frozen resource/integrity/internal-contract/unknown-provider fault',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset']=read(O/'실험/manifest.json')['dataset'];m['dataset'].update(name='Known CM001/007/009 actual end-to-end retry',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'))
m['llm_policy']['llm_calls']=[{'role':'product_and_supervisor','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['retrieval_accounting'].update(changed=True,not_applicable_reason=None);m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
m['design']['retrieval_stage_plan']['stages_by_arm']={'supervised':[{'stage_id':'delivered_or_read','kind':'source','parent_stage_ids':[]},{'stage_id':'original_read','kind':'select','parent_stage_ids':['delivered_or_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['questions']=read(O/'실험/manifest.json')['questions']
for q in m['questions']:
 p=ADR/'실험'/q['file'];p.write_text((O/'실험'/q['file']).read_text().replace('1166','1168')+'\n\n이번 실험: 실제 새 실행 예정. 위 과거 관찰은 원인 분석용이며 새 결과 아님.\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in parentf['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'supervised',present,experiment_id=m['experiment_id'],arm_id='supervised',run_ids=['run-001']);S=C/'snapshot'
for n,h in parentf['files'].items():
 src=ROOT/parentf['code_root']/n;assert sha(src)==h
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,S/n)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
for n in ('live.py','cm_authorization.py'):shutil.copyfile(ROOT/'06_TOOLS/EXPERIMENTS/adr_1166'/n,T/n)
for n in ('batch.py','summarize.py','finalize.py'):shutil.copyfile(ROOT/'06_TOOLS/EXPERIMENTS/adr_1161'/n,T/n)
p=T/'live.py';s=p.read_text();a=s.index('values=');b=s.index("f=read(DES/'freeze.json')");s=s[:a]+s[b:]
s=s.replace('Frozen actual selected MAIN109 service; transport audit only; no product app injection.','Exact ADR1167 repaired supervisor on MAIN112; isolated native HTTP, audited transport.')
s=s.replace("runtime=base/'runtime';base.mkdir(parents=True,exist_ok=True)","runtime=base/'runtime';base.mkdir(parents=True,exist_ok=True)\nfrom resource_guard import Guard\nguard=Guard(base);guard.start()")
a=s.index('def check_resources():');b=s.index('\ndef abort_unknown',a);s=s[:a]+"def check_resources():\n    guard.check()\n"+s[b:];p.write_text(s)
p=T/'batch.py';s=p.read_text();s=s.replace("if avail<3*1024**3", "if avail<5*1024**3")
s=s.replace("row=audit(P);rows.append(row);progress(rows)","row=audit(P);rows.append(row);progress(rows)\n if (P/'resource-stop.json').exists() or (P/'watchdog.json').exists() or read(P/'result.json').get('fatal') or read(P/'result.json').get('status')=='worker_failed':\n  progress(rows,stopped='frozen resource/unknown/internal-contract guard');print('BATCH_STOP',cid,flush=True);raise SystemExit(5)")
s=s.replace("kind like '%INDEPENDENT%'", "kind like '%INDEPENDENT%' OR kind like '%SUPERVISOR%'")
p.write_text(s)
p=T/'summarize.py';s=p.read_text().replace("with tempfile.TemporaryDirectory(prefix='cm51-audit-')", "with tempfile.TemporaryDirectory(prefix='cm3-audit-',dir=ART)").replace('ADR1155 (MAIN110 base)','ADR1167 (MAIN112 base)').replace('ADR1161 CM3','ADR1168 CM3').replace('현재 MAIN109','MAIN112 후보').replace('ADR1155 수정본','ADR1167 보완 감시 코드');p.write_text(s)
p=T/'finalize.py';s=p.read_text().replace("assert summary['completed']==3", "assert summary['completed']>0\ncases=[c for c in cases if (RUN/c['id']/'analysis.json').exists()]").replace("'focused'","'supervised'").replace('ADR-1161','ADR-1168').replace('ADR1155 rev002 unchanged copied to ADR1161 rev001','ADR1167 rev001 unchanged copied to ADR1168 rev001').replace('for q in m[\'questions\']:',"for q in m['questions']:\n if not (RUN/q['case_id']/'analysis.json').exists():continue").replace("'attempted':3","'attempted':summary['completed']").replace("'execution_complete':True","'execution_complete':summary['completed']==3").replace('len(corpus)*3','len(corpus)*len(cases)').replace('MAIN110기반이며 현재활성MAIN111과 구분','MAIN112 기반이며 선택 MAIN112는 유지').replace('ADR1155rev002와666파일동일','ADR1167rev001과459파일동일').replace('MAIN111 유지','MAIN112 유지');p.write_text(s)
print('Prepared exact1167 candidate; no product edits; scripts ready for freeze')
