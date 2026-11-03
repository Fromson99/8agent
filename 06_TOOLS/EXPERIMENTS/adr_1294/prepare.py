from pathlib import Path
import json,shutil,hashlib,sys
ROOT=Path('/home/jin/8-AGENT');OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1293-local-integration-ontology-ab';ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1294-local-ontology-ab-memory-map';ART=ADR/'artifacts';DES=ART/'design';T=Path(__file__).parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(OLD/'실험/manifest.json')['reservation']['status']=='completed'
for name in ('common.py','live.py','freeze.py','run_all.py','pinned_imports.py','resource_guard.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1293'/name).read_text().replace('ADR-1293-local-integration-ontology-ab','ADR-1294-local-ontology-ab-memory-map').replace('adr_1293','adr_1294').replace('adr1293','adr1294').replace('ADR1293','ADR1294')
 if name=='live.py':
  s=s.replace("resource.setrlimit(resource.RLIMIT_AS,(6*1024**3,6*1024**3))\n",'')
  s=s.replace("if not case.get('synthetic'):\n   query=", "if not case.get('synthetic'):\n   # Check actual embedding memory admission without any external LLM.\n   vector=store.vector_retriever.search(case['question'],documents=tuple(sorted(allowed)),limit=4)\n   put(base/'vector-preflight.json',{'type':type(vector).__name__,'value':str(vector)[:2000]})\n   query=")
 if name=='run_all.py':s=s.replace(",('comparison-one','baseline')",'')
 (T/name).write_text(s)
DES.mkdir(exist_ok=False)
for name in ('baseline.json','scoring-only-originals.json','comparison-source.json','root-files.json','ontology-on.json','ontology-off.json'):
 shutil.copyfile(OLD/'artifacts/design'/name,DES/name)
cases=[c for c in read(OLD/'artifacts/design/cases.json') if not c.get('synthetic')];put(DES/'cases.json',cases)
criteria=read(OLD/'artifacts/design/criteria.json');criteria['design']['comparison']='Not rerun: parent1293 comparison supervisor failure preserved.'
criteria['design']['harness_correction']='Remove experiment-only RLIMIT_AS6GiB; preserve actual RSS4GiB/availableRAM3GiB/swapgrowth128MiB and all product code. Separate no-LLM vector preflight before freeze/live.'
criteria['success']=[x for x in criteria['success'] if not x.startswith(('All22','Comparison returns'))]
put(DES/'criteria.json',criteria)
auth=read(OLD/'artifacts/design/authorization.json');auth['questions']=[c['question'] for c in cases];auth['source_documents']=['7bbe815ff43b6635'];put(DES/'authorization.json',auth)
m=read(ADR/'실험/manifest.json');parent=read(OLD/'실험/manifest.json');before=read(OLD/'artifacts/preregistered-manifest-before-final-accounting.json')
for k in ('design','llm_policy','dataset','retrieval_accounting'):m[k]=before[k]
m['design']['success_criteria']=criteria['success'];m['design']['code_isolation']['candidates']=[]
m['design']['criteria_freeze_evidence']={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')}
m['design']['arms'][0]['changes']='Ontology OFF on unchanged MAIN133; corrected test harness only'
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),name='Same public Commercial Act365/369 as completed1293',version='20261103-memory-map-v1')
m['runs'][0].update(arm_ids=['baseline','ontology-on'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule='Same2fixedpublicquestions;365OFFthenON,369ONthenOFF;oneattemptpercell;actualresourceguard;noASlimit')
put(ADR/'실험/manifest.json',m)
b=read(DES/'baseline.json');code=ROOT/b['release']['code_root'];files=b['release']['files'];assert all(sha(code/n)==h for n,h in files.items())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in files]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'selected-main133',paths,experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001']);ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot'
put(DES/'candidate.json',{'code_root':str((snap/b['release']['code_root']).relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':files})
for folder in ('transport','gold-connector'):shutil.copytree(OLD/'artifacts'/folder,ART/folder)
print('PREPARED1294 identical513productfiles; corrected harness; parentfailurepreserved')
