import json,hashlib,sqlite3
from pathlib import Path
from binding import sha,verify
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery';D=A/'artifacts/design'
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
pold=R/'04_EXPERIMENTS/ADR/ADR-0556-pecab-qwen-authorized-routing/artifacts/export-rebinding.json';b=json.loads(pold.read_text());b.pop('experiment_policy_path',None);policy=json.loads((R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json').read_text())
g=R/'01_DATA/TERM_RELEASES/pecab-only-public-main-20260929-v1/generation'
b.update(generation=str(g.relative_to(R)),policy_sha256=sha(R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),destination=policy['endpoint'],model=policy['model'],basis='User requested correction and experiment on our actual CM data in current thread; same verified145 public sources, current experiment policy; no private documents/questions',parent_rebinding_sha256=sha(pold),source_manifest_sha256=sha(g/'manifest.json'))
put(D/'source-binding.json',b);verify(all_files=True)
mp=A/'실험/manifest.json';m=json.loads(mp.read_text());cs=[];paths=[]
for arm,ident in [('BASELINE','baseline-memory'),('RECOVERED','bounded-memory')]:
 cp=R/'02_BACKEND/lawrag/research/candidates/adr_0612'/ident/'candidate.json';c=json.loads(cp.read_text());rev=c['revisions'][-1];runner=R/'06_TOOLS/EXPERIMENTS/adr_0612/run.py'
 cs.append({'candidate_id':ident,'experiment_id':m['experiment_id'],'arm_id':arm,'run_ids':['run-001'],'manifest_path':str(cp.relative_to(R)),'manifest_sha256':sha(cp),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str(runner.relative_to(R)),'runner_sha256':sha(runner)})
 paths += [cp,*[R/f['frozen_path'] for f in rev['files']]]
m['design']['code_isolation']={'schema_version':'adr-code-isolation-v1','mode':'candidate_snapshot','reason':None,'production_paths_modified_before_decision':False,'runtime_import_allowed':False,'production_registry_registered':False,'main_wiring_unchanged':True,'candidates':cs}
nav=json.loads((g/'navigation/manifest.json').read_text());print('Navigation manifest keys',list(nav));print('Navigation files',[x.name for x in (g/'navigation').iterdir()])
# Canonical source IDs from the actual navigation database; used offline and for scope counting.
ndb=next((g/'navigation').glob('*.sqlite'));db=sqlite3.connect('file:'+str(ndb)+'?mode=ro',uri=True)
rows=[{'source_id':s,'doc_id':d,'node':int(u)} for s,d,u in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if d in b['scope_document_ids'] and str(u).isdigit()];db.close();put(D/'source-coordinates.json',rows);m['retrieval_accounting']['corpus_total']=len(rows)
# Preflight failure notes are implementation preparation, not model experiments.
put(D/'preflight-notes.json',{'external_calls_before_freeze':0,'scaffold_adjustment':'Snapshot tool requires candidate role for registered snapshots; BASELINE is the comparison baseline, represented as candidate role in the registry.','contracts_passed':43,'contracts_total':43,'source_public_scope_documents':len(b['scope_document_ids']),'source_canonical_units':len(rows),'raw_internal_documents_excluded':True,'source_flags_modified':False})
put(mp,m);put(D/'pre-run-manifest.json',m)
prev=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0610-memory-forced-turn-examples/artifacts/design/freeze.json').read_text())
paths += [R/p for p in prev if ('02_BACKEND/semantic_runtime/' in p and 'candidates/' not in p) or p in ('00_SYSTEM/PIPELINE.json','01_DATA/ACTIVE/local/ACTIVE_RELEASE.json','00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','02_BACKEND/lawrag/research/experiment_client.py')]
paths += [R/'08_DEPLOYMENT/CONFIG/legal-source-export.json',pold,*D.glob('*.json'),*(R/'06_TOOLS/EXPERIMENTS/adr_0612').glob('*.py'),A/'artifacts/contracts/result.json',A/'artifacts/contracts/native-result.json']
paths += [g/'manifest.json',g/'store.sqlite',g/'navigation/manifest.json',ndb,g/'fulltext/manifest.json',g/'glossary/bundle/manifest.json']
put(D/'freeze.json',{str(p.relative_to(R)):sha(p) for p in set(paths) if p.name not in ('freeze.json','finalize.py','report.py')})
print('Frozen',len(json.loads((D/'freeze.json').read_text())),'files with verified public145 provenance.')
