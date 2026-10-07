"""Frozen compiler acceptance run. Public synthetic cases only; no production writes."""
import hashlib,json,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0641-shortcut-claim-quarantine';C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0641/integrated'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
candidate=read(C/'candidate.json');revision=candidate['revisions'][0]
for f in revision['files']:assert sha(ROOT/f['frozen_path'])==f['snapshot_sha256'],f['frozen_path']
for p,h in read(ADR/'artifacts/baseline-pins.json').items():assert sha(ROOT/p)==h,p
snapshot=C/'revisions/rev-001/snapshot'
sys.path.insert(0,str(ROOT/'02_BACKEND'));sys.dont_write_bytecode=True
import semantic_runtime.legal_agent,lawrag.pipeline
semantic_runtime.legal_agent.__path__.insert(0,str(snapshot/'02_BACKEND/semantic_runtime/legal_agent'))
lawrag.pipeline.__path__.insert(0,str(snapshot/'02_BACKEND/lawrag/pipeline'))
from semantic_runtime.legal_agent.shortcut_repository import ShortcutRepository
from semantic_runtime.legal_agent.corrected_memory import digest
from lawrag.pipeline.legal_wiki_compiler import compile_snapshots,rebuild,PROMPT
from lawrag.research.experiment_client import ExperimentClient
m=read(ADR/'실험/manifest.json')
m['design']['code_isolation']['candidates']=[{'candidate_id':'integrated','experiment_id':m['experiment_id'],'arm_id':'integrated','run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':revision['revision_id'],'revision_sha256':revision['revision_sha256'],
 'runner_path':str(Path(__file__).relative_to(ROOT)),'runner_sha256':sha(Path(__file__))}]
put(ADR/'실험/manifest.json',m)
dataset=read(ADR/'artifacts/inputs.json');directory=ADR/'artifacts/run-001'
assert not directory.exists(),'completed or started runs are immutable; use a new ADR'
directory.mkdir()
client=ExperimentClient(ROOT,directory/'provider',max_calls=6,max_output_tokens=10000,max_repairs=0)
binding={'model':client.model,'policy_hash':sha(ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),'prompt_hash':digest(PROMPT),'trust_zone':'external','public_export_authorized':True}
results=[]
for case in dataset['cases']:
 cid=case['id'];where=directory/cid;where.mkdir()
 principal={'user_id':'synthetic-'+cid,'team_id':'public-shortcut-research','authenticated':True,'document_ids':sorted({s['document_id'] for s in dataset['sources']})}
 repo=ShortcutRepository(where/'cases-v4.sqlite');start=time.monotonic()
 try:
  intake=repo.intake({'question':case['question'],'session_id':cid,'request_id':cid+'-initial','public_question':True,'document_ids':principal['document_ids']},principal)
  investigation=repo.connect(intake['id'],principal)
  for source in dataset['sources']:repo.source(principal,source)
  before=repo.snapshot(investigation['id'],principal);put(where/'snapshot.json',before)
  value=compile_snapshots(repo,principal,[before],model=lambda system,data,schema:client.generate(system,data,schema,phase=cid),binding=binding,publish=True)
  projection=rebuild(repo,principal,where/'wikis')
  row={'case_id':cid,'status':'ACCEPTED','units':value['units'],'build_id':value['build_id'],'projection':projection,'quality_certified':False,'seconds':time.monotonic()-start}
  put(where/'build.json',value)
 except Exception as exc:
  row={'case_id':cid,'status':'FAILED','error_type':type(exc).__name__,'error':str(exc),'seconds':time.monotonic()-start,'quality_certified':False}
  (where/'error.txt').write_text(traceback.format_exc())
 finally:repo.close()
 put(where/'result.json',row);results.append(row);put(ADR/'artifacts/run-001.json',{'results':results,'usage':client.usage,'model_calls':client.calls})
 print(json.dumps(row,ensure_ascii=False),flush=True)
print('Compiler acceptance completed',flush=True)
