from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
DES.mkdir(exist_ok=False)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);base=ROOT/release['code_root'];files=release['files'];assert all(sha(base/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':active,'release':release})
names=['02_BACKEND/semantic_runtime/legal_agent/completion_execution.py','02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py','02_BACKEND/semantic_runtime/legal_agent/unified_runtime.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
for n in names:
 p=ART/'working-before'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,p)
put(DES/'working-before.json',{n:sha(ROOT/n) for n in names})
m=read(ADR/'실험/manifest.json');can=ac.snapshot(ADR,'explanation',list(files),experiment_id=m['experiment_id'],arm_id='explanation',run_ids=['run-001'])
for n,h in files.items():
 if sha(can/'snapshot'/n)!=h:shutil.copyfile(base/n,can/'snapshot'/n)
display='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py';shutil.copyfile(ROOT/display,can/'snapshot'/display)
put(DES/'mutable-candidate.json',{'path':str(can.relative_to(ROOT)),'files':list(files),'new_files':['02_BACKEND/semantic_runtime/legal_agent/source_explanation.py']})
criteria={'hypothesis':'Only unresolved final presentation changes: grounded prose first, specific uncertainty and question last; original source details stay in cards. No document title, excerpt previews, rejected claim reuse or assessment promotion.', 'success':['Source quote bindings valid; unknown or fabricated quotes rejected','Original assessment, coverage, disposition and source cards unchanged','Actual Qwen on previously acquired CM003 originals produces explanatory paragraphs without source headers; specific followup last','Native COMPOSE and public display use same tested module; duplicate publication adds no generation'], 'limits':{'model':'qwen/qwen3.8-27b','provider':'Parasail FP8 current default','reasoning':'none','max_output_tokens':None,'calls':4,'request_seconds':180,'reported_cost_usd':1},'stop':'UNKNOWN halts all sends; no automatic retries. Only one structural correction inside existing bounded COMPOSE if complete invalid output.', 'input':'Recorded actual CM003 ASSESS and verified source receipts from ADR1409; question and public original bodies only; no rejected proposal or historical needs as facts','quality_certified':False,'main_promoted':False}
put(DES/'criteria.json',criteria)
print(can/'snapshot')
