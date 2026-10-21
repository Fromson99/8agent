from pathlib import Path
import json,hashlib,shutil,gzip
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0960-scoped-multiturn-qualification';A=D/'artifacts'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
shutil.copyfile(R/'05_TESTS/CONTRACTS/test_scoped_multiturn_api.py',A/'test_scoped_multiturn_api.initial.py')
for i,p in enumerate(Path('/tmp/pytest-of-jin/pytest-340').glob('test*ask[0-9]/runtime/legal-agent/runs/*/*/journal.sqlite')):
 with p.open('rb') as src,gzip.open(A/f'api-initial-journal-{i}.sqlite.gz','wb') as dst:shutil.copyfileobj(src,dst)
result={'strict_success':False,'checks':{'five_commands_complete':False,'four_api_consumers_pass':False},'live':{'pass':4,'total':5,'error':'HTTP429 during fifth case verification','physical_calls':10},'api':{'pass':1,'fail':3,'reason':'Scripted transport uses old literal intent and indexes empty read candidates. Runtime constraints unchanged.'},'decision':'Do not promote this run; retain failures and requalify unchanged code with repaired harness in a new ADR.'}
save(A/'result.json',result);p=D/'실험/manifest.json';m=json.loads(p.read_text());m['runs'][0].update(status='complete',sha256=sha(A/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','source':'ADR0957'},'qualified':{'status':'complete','strict_success':False}},usage={'model_calls':10},latency={},judge_disagreements=0,error_taxonomy=['provider HTTP429','scripted harness intent quote mismatch','scripted harness empty read menu']);save(p,m)
for path in [D/'README.md',D/'실험/README.md',D/'실험/질문-001-scoped-multiturn-heldout.md']:
 old=path.read_text();header=''
 if old.startswith('---'):
  _,front,body=old.split('---',2);header='---'+front+'---\n';old=body
 lines=[x for x in old.splitlines() if x.startswith('#')]
 body=''
 for h in lines:body+=h+'\n\nQualification failed: four of five live synthetic commands passed; the fifth verification hit provider HTTP429. API tests: one pass and three scripted-model failures (stale intent literal and empty read menu). Frozen runtime code was not changed. No MAIN activation. Exact failure records and candidate hashes are in artifacts/result.json, artifacts/model, artifacts/qualification-api.log and the experiment manifest. Follow-up will retain code and use repaired harness; no result is legal ground truth.\n\n'
 path.write_text(header+'\n'+body)
rows=[]
for p in sorted(A.rglob('*')):
 if p.is_file() and p.name!='manifest.json' and p.suffix not in ('.sqlite','.pyc') and 'sqlite-' not in p.name:rows.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Immutable failed qualification evidence','contains_raw_prompts_and_outputs':p.is_relative_to(A/'model')})
save(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0960','created_at':m['reservation']['created_at'],'files':rows})
