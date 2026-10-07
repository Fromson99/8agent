"""Two preregistered related-case compiler turns, no legal-quality claim."""
from pathlib import Path
import hashlib,json,sys,time,traceback
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0644-shortcut-incremental-related-operations';C=R/'02_BACKEND/lawrag/research/candidates/adr_0644/integrated';D=A/'artifacts/design';OUT=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not OUT.exists(),'new ADR required after any attempted run'
for name,h in read(D/'freeze.json')['files'].items():assert sha(R/name)==h,name
for row in read(C/'candidate.json')['revisions'][0]['files']:assert sha(R/row['frozen_path'])==row['snapshot_sha256']
sys.path.insert(0,str(C/'revisions/rev-001/snapshot/02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import digest
from lawrag.pipeline.legal_wiki_compiler import compile_snapshots,rebuild,PROMPT
# Host audit client is deliberately separate from candidate runtime.
import importlib.util
spec=importlib.util.spec_from_file_location('audit',R/'02_BACKEND/lawrag/research/experiment_client.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
inputs=read(D/'inputs.json');OUT.mkdir();repo=ShortcutRepository(OUT/'cases-v4.sqlite');client=audit.ExperimentClient(R,OUT/'provider',max_calls=2,max_output_tokens=10000,max_repairs=0)
p=inputs['principal'];cases=[];events=[]
for index,text in enumerate(inputs['initial_questions']):
 intake=repo.intake({'question':text,'session_id':'public-'+str(index),'request_id':'initial','public_question':True,'document_ids':p['document_ids']},p)
 cases.append(repo.connect(intake['id'],p));events.append(intake['event'])
for value in inputs['sources']:repo.source(p,value)
event=repo.advance(cases[0]['id'],p,cases[0]['revision'],'EXPLICIT_RELATION',{'text':'별개 사건이며 원문 쟁점만 공통'})
repo.relation(cases[0]['id'],cases[1]['id'],p,kind='SAME_TOPIC',reason='같은 원문을 비교하되 개별 사실은 분리',event=event)
binding={'model':client.model,'policy_hash':sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'prompt_hash':digest(PROMPT),'trust_zone':'external','public_export_authorized':True};results=[]
try:
 for turn in (1,2):
  if turn==2:
   intake=repo.intake({'question':inputs['correction'],'session_id':'public-0','request_id':'correction','public_question':True,'document_ids':p['document_ids']},p);repo.connect(intake['id'],p,investigation_id=cases[0]['id'])
  snapshots=repo.related_inputs(repo.compiler_input(cases[0]['id'],p),p);put(OUT/f'turn-{turn}-snapshots.json',snapshots)
  start=time.monotonic()
  try:
   value=compile_snapshots(repo,p,snapshots,model=lambda system,data,schema:client.generate(system,data,schema,phase='related-turn-'+str(turn)),binding=binding,publish=True)
   with repo.transaction():
    for snapshot in snapshots:repo.compiler_progress(snapshot)
   put(OUT/f'turn-{turn}-build.json',value)
   row={'turn':turn,'status':'ACCEPTED','units':value['units'],'prior_links':value['prior_links'],'input_cases':len(snapshots),'event_ids':{s['case']['id']:[e['id'] for e in s['events']] for s in snapshots},'seconds':time.monotonic()-start}
  except Exception as exc:
   row={'turn':turn,'status':'FAILED','error_type':type(exc).__name__,'error':str(exc),'seconds':time.monotonic()-start};(OUT/f'turn-{turn}-error.txt').write_text(traceback.format_exc())
  results.append(row);put(OUT/'result.json',{'results':results,'calls':client.calls,'usage':client.usage,'quality_certified':False,'main_unchanged':True})
  print(json.dumps(row,ensure_ascii=False),flush=True)
 projection=rebuild(repo,p,OUT/'wikis');put(OUT/'projection.json',projection)
finally:repo.close()
