"""Prospective, user-authorized final read-review ablation; isolated candidate only."""
from pathlib import Path
import sys,json,shutil,hashlib,ast
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1305-main135-nearai-sqlite';ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1306-main135-final-review-off-sqlite';ART=ADR/'artifacts';DES=ART/'design'
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
for name in ('common.py','live.py','resource_guard.py','pinned_imports.py','authorization.py','audit.py','ledger.py','archive_all_closed.py','run_all.py','freeze.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1305'/name).read_text().replace('ADR-1305-main135-nearai-sqlite','ADR-1306-main135-final-review-off-sqlite').replace('adr_1305','adr_1306').replace('adr1305','adr1306').replace('ADR1305','ADR1306').replace('ADR-1305','ADR-1306')
 s=s.replace("'sqlite'","'review-off'").replace("'-sqlite.log'","'-review-off.log'")
 if name=='live.py':
  s=s.replace('Product code is byte-identical to selected MAIN135.','One candidate module disables final read judgment review; selected MAIN135 unchanged.')
  s=s.replace('assert all(sha(C/n)==sha(selected_code/n)==h for n,h in candidate[\'selected_files\'].items())',"assert all(sha(C/n)==h for n,h in candidate['selected_files'].items())\nassert all(sha(selected_code/n)==h for n,h in candidate['original_selected_files'].items())")
  s=s.replace("'product_code_unchanged':True","'selected_main_unchanged':True,'candidate_final_read_review_disabled':True")
  s=s.replace("'selected_equivalent':True","'selected_equivalent':False,'candidate_delta':'final read judgment review disabled, engine pins rebound'")
  s=s.replace("'selected_code_unchanged':all","'frozen_candidate_unchanged':all")
  s=s.replace("number=len(generations)+1;stage=view.get('source_stage',phase);", "number=len(generations)+1;stage=view.get('source_stage',phase);\n  if stage in ('memory-assess','memory-assess-repair'):\n   assert 'read_judgment_review' not in self.protocol.schema(schema_name)['properties']\n   assert 'read_judgments' not in view\n   assert 'requirement_review' in self.protocol.schema(schema_name)['properties']\n   assert view['evidence_options']\n  ")
 if name=='freeze.py':s=s.replace("'selected-main135'","'review-off'")
 (T/name).write_text(s)
sys.path.insert(0,str(T));from common import put
DES.mkdir(exist_ok=False)
for name in ('baseline.json','scoring-only-originals.json','nearai-only.json','authorization.json','sqlite-source.json','provider-endpoints.json','endpoint-check.json'):
 shutil.copyfile(OLD/'artifacts/design'/name,DES/name)
shutil.copytree(OLD/'artifacts/transport',ART/'transport')
cases=read(OLD/'artifacts/design/cases.json')
for c in cases:c['arms']=['review-off']
put(DES/'cases.json',cases)
criteria=read(OLD/'artifacts/design/criteria.json')
criteria.update(hypothesis='Removing the duplicate final read_judgment_review contract allows existing source-backed core answers to be delivered; source correctness is independently graded.',primary_metric='Final complete source-supported answers /2; all3 question-specific core rules required, no unsupported added rule.',order=['ontology-365/review-off','ontology-369/review-off'],scope='SelectedMAIN135 plus one isolated completion module gate and engine pins. Only final read_judgment_review context, schema, prompt, validation and retention disabled; navigation read judgments remain. Existing requirement_review, core claim/evidence/ACL/version/state/budget checks remain. SQLite and NearAI only.',user_steering='일단이거 빼보고 답 잘하는지 확인해봐',comparison='Historical ADR1305 baseline only, no new baseline model calls. Same two known questions and source/model settings, temporal/model variability prevents causal accuracy/stability claims.',environment={'MALLOC_ARENA_MAX':'1','resource_limits_unchanged':True})
put(DES/'criteria.json',criteria)
put(DES/'ablation-authorization.json',{'user_instruction':criteria['user_steering'],'scope':criteria['scope'],'main_cutover':False,'model_calls_before_freeze':0})
m=read(ADR/'실험/manifest.json');old=read(OLD/'실험/manifest.json')
for k in ('design','llm_policy','dataset','retrieval_accounting'):m[k]=old[k]
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary_metric'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1305-experiment-v1/sqlite'],'changes':'Historical completed ADR1305, no new calls','controls':'SameMAIN135/source/model/questions'}, {'id':'review-off','role':'candidate','derived_from':['baseline'],'changes':criteria['scope'],'controls':'Same source, SQLite, NearAI, reasoning, navigation, original checks and budgets'}]
stages=old['design']['retrieval_stage_plan']['stages_by_arm']['sqlite'];m['design']['retrieval_stage_plan']['stages_by_arm']={'baseline':stages,'review-off':stages};m['design']['code_isolation']['candidates']=[]
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['llm_policy']['provider_override'].update(path=str((DES/'nearai-only.json').relative_to(ROOT)),sha256=sha(DES/'nearai-only.json'))
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261103-read-review-off-v1')
m['runs'][0].update(arm_ids=['review-off'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule='Sameknown2publicquestions eachonce;finalreadreviewOFF;NearAIonly;nogoldinproduct;stopUNKNOWN/resource;preservefailure;noadaptivecellretry')
for q in m['questions']:
 p=next((OLD/'실험').glob('*'+q['case_id']+'.md'));s=p.read_text().split('## 8. 사례 최종 판정')[0]+'## 8. 사례 최종 판정\n\nNot dispatched; prospectively frozen review-off candidate.\n';(ADR/'실험'/q['file']).write_text(s)
put(ADR/'실험/manifest.json',m)
release=read(DES/'baseline.json')['release'];code=ROOT/release['code_root']
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation']==135
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in release['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'review-off',paths,experiment_id=m['experiment_id'],arm_id='review-off',run_ids=['run-001']);S=candidate/'snapshot'/release['code_root']
p=S/'02_BACKEND/semantic_runtime/legal_agent/completion_execution.py';s=p.read_text();needle="        if modern and profile.get('candidate_navigation',{}).get('read_judgment'):";assert s.count(needle)==1
s=s.replace(needle,"        # ADR1306 user-authorized ablation: omit only the final read-review contract.\n        if False and modern and profile.get('candidate_navigation',{}).get('read_judgment'):")
p.write_text(s)
# Candidate-only engine dependency pin updates, preserving MAIN and working tree.
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
put(DES/'candidate.json',{'code_root':str(C.relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':files,'original_selected_files':release['files'],'delta':delta})
put(DES/'candidate-delta.json',{'changed_files':delta,'product_modules':1,'engine_pin_files':len(delta)-1,'source_sqlite_unchanged':True,'navigation_read_judgments_enabled':True,'requirement_review_enabled':True,'final_read_judgment_review_enabled':False})
print('Prepared',len(files),'files; delta',len(delta),'one product module; no model calls')
