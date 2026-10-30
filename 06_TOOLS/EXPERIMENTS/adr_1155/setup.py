from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1155-investigation-focus-offline';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(R/pointer['manifest_path']);parent=read(R/'04_EXPERIMENTS/ADR/ADR-1154-ontology-selection-release-receipt/artifacts/design/freeze.json')
put(D/'baseline.json',dict(pointer=pointer,release=release,pointer_sha256=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')))
criteria={'model_calls':0,'main_unchanged':True,'known_inputs':['cm-007','cm-009'],'tests':['initial search candidates survive connection window under same request/scope binding','preview preserves up to3 exact matching excerpts with positions; no fabricated law text','new goal observation records remain independent of original progress and never force handoff','all paginated read/tool handles reachable; hidden handles rejected; same schema on repair','stored original texts, questions, judgments unchanged by projection','stable IDs, existing progress-control and independent-read recovery preserved','no data/model/ontology/default-off changes'], 'limits':'offline contracts only; no claim of changed model choices, call reduction or legal quality','failure_contract':{'class':'selection context and semantic-progress mismatch','owner':'existing investigation/answer_progress/pager','repair':'existing bounded_decision only','budget':'40/1024/1800 unchanged','termination':'observation does not force termination; existing source/ACL/claim gates preserved'},'resource':'one test process; no full corpus load; shared immutable data','scope':'No MAIN promotion; implementation isolated until qualification'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['design']['hypothesis']='Retain search routes, matching excerpts, separate goal observation, and bound menu payload without losing selectable targets or evidence.';m['design']['success_criteria']=criteria['tests'];m['design']['arms'][1]['changes']='Scoped investigation focus edits against MAIN110';m['runs'][0]['arm_ids']=['focused'];m['llm_policy']['llm_calls']=[];put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=list(parent['files']);present=[n for n in paths if (R/n).is_file()];C=ac.snapshot(A,'focused-r1',present,experiment_id=m['experiment_id'],arm_id='focused',run_ids=['run-001'])
for n in paths:
 src=R/parent['code_root']/n;assert sha(src)==parent['files'][n];out=C/'snapshot'/n;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(D/'source-worktree.json',{n:sha(R/n) for n in present});print(C)
