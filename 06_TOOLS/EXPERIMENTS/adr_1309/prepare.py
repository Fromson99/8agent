from common import *
import shutil,ast,datetime
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1307-main135-final-tables-off-sqlite'
T=Path(__file__).parent
DES.mkdir(exist_ok=False)
for name in ('baseline.json','scoring-only-originals.json','nearai-only.json','authorization.json','sqlite-source.json','provider-endpoints.json','endpoint-check.json'):
 shutil.copyfile(OLD/'artifacts/design'/name,DES/name)
shutil.copytree(OLD/'artifacts/transport',ART/'transport')
before=read(DES/'baseline.json');pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==136
after={'pointer':pointer,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':read(ROOT/pointer['manifest_path'])}
assert before['release']['data_path']==after['release']['data_path']
put(DES/'baseline-before.json',before);put(DES/'baseline-after.json',after)
cases=read(OLD/'artifacts/design/cases.json')
for c in cases:c['arms']=['before','after']
put(DES/'cases.json',cases)
criteria=read(OLD/'artifacts/design/criteria.json')
criteria.update(hypothesis='MAIN136 reduces same-question request latency and SQLite work relative to MAIN135 while preserving source-supported final content.',primary_metric='Paired total request seconds for completed same-question answers; SQL traced statements and exclusive SQLite API seconds, physical model seconds/calls as explanatory metrics.',success=['Both questions in each arm deliver all three original core rules with valid source links, no unsupported material rule.','Candidate sum of successful paired request seconds is lower than baseline; report per-case regressions separately.','Original spans, ACL, wire, code/source hashes, budgets and duplicate retrieval checks preserved.'],failure=['Any unsupported/missing core rule or source/ACL/wire/budget violation.','No candidate request speed reduction on completed matched pairs.','Unknown provider outcome or resource limit stops remaining physical dispatches; no automatic cell rerun.'],order=['ontology-365/before','ontology-365/after','ontology-369/after','ontology-369/before'],repeats=1,scope='Fresh MAIN135 and MAIN136 serving snapshots, both with identical candidate-only final judgment and requirement table gates OFF. Existing navigation and core citation checks remain. SQLite, ontologyOFF, NearAI only, reasoningnone; source and gold separate.',comparison='Fresh paired two-known-question version comparison. MAIN136 includes SQL/cache/stop and display changes, so not isolated SQL causal attribution. Each cell fresh process; OS/page cache not cleared. Alternating order; no general p95 or significance from n2.',user_steering='테스트 해봐 얼마나 빨라졌ㄴ즌지; prior SQLite/NearAI-only and tables-off test preference retained.',limits={'per_request_physical_calls':40,'global_physical_calls':160,'call_deadline_seconds':180,'cell_timeout_seconds':2100,'output_cap':None,'unknown_stop':True,'same_cell_retry':False},environment={'MALLOC_ARENA_MAX':'1','resource_limits_unchanged':True},measurement={'request':'native HTTP ask call; excludes startup, duplicate and cleanup','sql':'Trace actual statements including nested base-method calls. SQLite API execute/fetch exclusive wall seconds include row factories/UDF; not pure engine CPU. Untimed base calls still traced. Corpus/journal/memory separated. Observer overhead shared across arms.','model':'physical post interval sum, sequential calls; residual is not pure DB time','quality':'post-run source-based core3 per question; no evaluation model calls'})
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');old=read(OLD/'실험/manifest.json')
for k in ('design','llm_policy','dataset','retrieval_accounting'):m[k]=old[k]
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1308-experiment-v1/optimized'],'changes':'Completed optimization lineage only; no baseline dispatch','controls':'Historical parent, not a speed observation'},*({'id':arm,'role':'candidate','derived_from':['baseline'],'changes':f'Fresh {name}, final two tables OFF; API and SQL observer','controls':'Same data/model/questions/budgets/observer, isolated runtime'} for arm,name in [('before','MAIN135'),('after','MAIN136')])]
stages=old['design']['retrieval_stage_plan']['stages_by_arm']['tables-off'];m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','before','after')};m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['llm_policy']['provider_override'].update(path=str((DES/'nearai-only.json').relative_to(ROOT)),sha256=sha(DES/'nearai-only.json'))
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261103-main136-latency-v1')
m['runs'][0].update(arm_ids=['before','after'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule='Same two public known questions, each version once, alternating order; stop UNKNOWN/resource; preserve all failures; no adaptive retry')
for q in m['questions']:
 p=next((OLD/'실험').glob('*'+q['case_id']+'.md'));s=p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\nNot dispatched; prospective paired latency test.\n';(ADR/'실험'/q['file']).write_text(s)
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
for arm,base in [('before',before),('after',after)]:
 release=base['release'];code=ROOT/release['code_root']
 assert all(sha(code/n)==h for n,h in release['files'].items())
 paths=[str((code/n).relative_to(ROOT)) for n in release['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
 candidate=ac.snapshot(ADR,arm,paths,experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001']);S=candidate/'snapshot'/release['code_root']
 p=S/'02_BACKEND/semantic_runtime/legal_agent/completion_execution.py';s=p.read_text();needle="        if modern and profile.get('candidate_navigation',{}).get('read_judgment'):";assert s.count(needle)==1
 s=s.replace(needle,"        # ADR1309: identical user-authorized final-table ablation in both arms.\n        if False and modern and profile.get('candidate_navigation',{}).get('read_judgment'):")
 needle2='requirement_context = requirements.context(utterance,self.issues,options) if modern and requirements.enabled(profile) else None';assert s.count(needle2)==1
 s=s.replace(needle2,'requirement_context = None  # ADR1309: final requirement table OFF in both arms');p.write_text(s)
 for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
  d=read(p);changed=False
  for n,h in d.get('files',{}).items():
   if (S/n).is_file() and sha(S/n)!=h:d['files'][n]=sha(S/n);changed=True
  if changed:p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 p=S/'00_SYSTEM/PIPELINE.json';d=read(p)
 def pins(x):
  if isinstance(x,dict):
   for k,v in list(x.items()):
    if isinstance(v,str) and len(v)==64 and k.startswith('02_BACKEND/ENGINES/') and (S/k).is_file():x[k]=sha(S/k)
    elif isinstance(v,str) and k in ('manifest','manifest_path') and (S/v).is_file():
     for hk in ('manifest_sha256','sha256'):
      if hk in x and isinstance(x[hk],str) and len(x[hk])==64:x[hk]=sha(S/v)
    elif isinstance(v,(dict,list)):pins(v)
  elif isinstance(x,list):
   for v in x:pins(v)
 pins(d);p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 for p in S.rglob('*.py'):ast.parse(p.read_text())
 ac.freeze(candidate);assert not ac.validate(candidate),ac.validate(candidate)
 cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot';C=snap/release['code_root']
 files={n:sha(C/n) for n in release['files']};delta=[n for n,h in files.items() if h!=release['files'][n]]
 assert [n for n in delta if n.endswith('.py')]==['02_BACKEND/semantic_runtime/legal_agent/completion_execution.py']
 descriptor={'code_root':str(C.relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':files,'original_selected_files':release['files'],'delta':delta}
 put(DES/('candidate-'+arm+'.json'),descriptor)
 if arm=='after':put(DES/'candidate.json',descriptor)
 print('Prepared',arm,len(files),'files, candidate delta',len(delta),flush=True)
