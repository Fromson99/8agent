from pathlib import Path
import json,shutil,hashlib,sys
ROOT=Path('/home/jin/8-AGENT');OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1294-local-ontology-ab-memory-map';ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1296-local-ontology-ab-derived-grant';ART=ADR/'artifacts';DES=ART/'design';T=Path(__file__).parent
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert read(OLD/'실험/manifest.json')['reservation']['status']=='completed'
for name in ('common.py','live.py','freeze.py','run_all.py','pinned_imports.py','resource_guard.py'):
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1294'/name).read_text().replace('ADR-1294-local-ontology-ab-memory-map','ADR-1296-local-ontology-ab-derived-grant').replace('adr_1294','adr_1296').replace('adr1294','adr1296').replace('ADR1294','ADR1296')
 if name=='resource_guard.py':s=s.replace("s['rss']>4*GIB","s['rss']>5*GIB").replace('above 4GiB','above 5GiB').replace("('rss',5*GIB)","('rss',6*GIB)")
 if name=='live.py':
  s=s.replace("auth_hash=sha(DES/'authorization.json');allowed=set(case['document_ids'])", "auth_hash=sha(DES/'authorization.json');allowed=set(case['document_ids']);host_derived_questions=set();derivations=[]")
  s=s.replace("request.get('question',query['question'])!=case['question']","request.get('question',query['question']) not in {case['question']}|host_derived_questions")
  s=s.replace("t=Authorized(C,ROOT);profile.update(model_binding=t.binding,max_output_tokens=None)","""t=Authorized(C,ROOT);profile.update(model_binding=t.binding,max_output_tokens=None)
 from contextlib import contextmanager
 from semantic_runtime.legal_agent.unified_rag import UnifiedRag
 from authorization import derive,self_test
 assert self_test()==8
 original_open=UnifiedRag.open
 @contextmanager
 def approved_open(host,state,principal,body):
  effective=derive(body,state,case['question'],allowed,'adr1296-'+base.name)
  assert effective==host.retrieval_question(state)
  session=host.model.ensure()
  receipt=session.context.binding['external_authorization']
  assert receipt['authorization_sha256']==auth_hash and set(receipt['scope_document_ids'])<=allowed
  host_derived_questions.add(effective)
  derivations.append({'original_question':body['question'],'effective_question':effective,'task':state['task'],'facts':deepcopy(state['facts']),'document_ids':state['document_ids'],'request_id':body['request_id'],'run_id':session.context.run_id,'product_state_rewritten':False})
  put(base/'authorized-derivations.json',derivations)
  with original_open(host,state,principal,body) as execution:yield execution
 UnifiedRag.open=approved_open""")
  a=s.index('   # Check actual embedding memory admission');b=s.index('   query=',a);s=s[:a]+s[b:]
 if name=='run_all.py':
  s=s.replace(" if p.returncode:\n", " result_path=ART/'live'/(case+'-'+arm)/'result.json'\n result=read(result_path) if result_path.exists() else {}\n if p.returncode or (result.get('http_status',0)>=500 and not result.get('unknown')):\n")
 (T/name).write_text(s)
DES.mkdir(exist_ok=False)
for name in ('baseline.json','scoring-only-originals.json','comparison-source.json','root-files.json','ontology-on.json','ontology-off.json','cases.json'):
 shutil.copyfile(OLD/'artifacts/design'/name,DES/name)
criteria=read(OLD/'artifacts/design/criteria.json');criteria['design']['harness_correction']='Original API question/session/IDs must match; product-validated host task+facts projected through unchanged retrieval_question are registered only at UnifiedRag.open. No output/state modification. No ASlimit; sampledRSS5GiB and terminalru_maxrss5GiB; available3GiB/swapgrowth128MiB unchanged. Stop remaining cells on any500+ nonunknown APIfailure.'
criteria['limits']['rss_GiB']=5;put(DES/'criteria.json',criteria)
auth=read(OLD/'artifacts/design/authorization.json');auth['derived_context']='Only original fixed API request/session/initial request ID and product-validated same-scope host task/facts; record derivations, never change product output.';put(DES/'authorization.json',auth)
m=read(ADR/'실험/manifest.json');before=read(OLD/'artifacts/preregistered-manifest-before-final-accounting.json')
for k in ('design','llm_policy','dataset','retrieval_accounting'):m[k]=before[k]
m['lineage']['hypothesis_delta']='Same two ON/OFF pairs on MAIN133 with corrected experiment-derivedquestiongrant; no product change; explicit5GiBpeakRSSlimit.'
m['design']['code_isolation']['candidates']=[];m['design']['arms'][0]['derived_from']=['ADR-1294-experiment-v1/ontology-on']
m['design']['criteria_freeze_evidence']={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')}
m['dataset'].update(frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),version='20261103-derived-grant-v1')
m['runs'][0].update(arm_ids=['baseline','ontology-on'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)),selection_rule='Same2publicquestions;365OFFthenON,369ONthenOFF;oneattemptpercell;stoponunknown/resource/5xx; onlyexperimentgrantcorrected')
put(ADR/'실험/manifest.json',m)
b=read(DES/'baseline.json');code=ROOT/b['release']['code_root'];files=b['release']['files'];assert all(sha(code/n)==h for n,h in files.items())
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
paths=[str((code/n).relative_to(ROOT)) for n in files]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/research/openrouter_legal_adapter.py','02_BACKEND/lawrag/core/request_deadline.py']
candidate=ac.snapshot(ADR,'selected-main133',paths,experiment_id=m['experiment_id'],arm_id='ontology-on',run_ids=['run-001']);ac.freeze(candidate);assert not ac.validate(candidate)
cm=read(candidate/'candidate.json');rev=cm['revisions'][-1];snap=candidate/'revisions'/rev['revision_id']/'snapshot'
put(DES/'candidate.json',{'code_root':str((snap/b['release']['code_root']).relative_to(ROOT)),'snapshot_root':str(snap.relative_to(ROOT)),'pin':{'manifest_path':str((candidate/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(candidate/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']},'selected_files':files})
for folder in ('transport','gold-connector'):shutil.copytree(OLD/'artifacts'/folder,ART/folder)
print('PREPARED1296 identical513productfiles; derivedgrantrecording; corrected5GiBthreshold')
