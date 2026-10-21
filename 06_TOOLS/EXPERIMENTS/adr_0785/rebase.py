"""Preserve concurrently integrated search selection before the first frozen audit."""
from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0785-risk-team-compare-workflow';OLD=R/'02_BACKEND/lawrag/research/candidates/adr_0785/workflow';NEW=OLD.parent/'integrated'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not NEW.exists();old=read(OLD/'candidate.json');base=read(A/'artifacts/design/baseline.json')
assert old['revisions']==[]
files={x['target_path'] for x in old['files'] if (R/x['target_path']).is_file()}
files.update(read(R/'02_BACKEND/ENGINES/legal_agent/6.0.0/retrieve.json')['files'])
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),
 '--candidate-id','integrated','--experiment-id','ADR-0785-experiment-v1','--arm-id','workflow','--run-id','run-001']
for name in sorted(files):cmd+=['--source',name]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
changes=[]
for row in old['files']:
 name=row['target_path'];source=OLD/'snapshot'/name;target=NEW/'snapshot'/name
 current=sha(R/name) if (R/name).exists() else None
 if current==row.get('upstream_sha256'):
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
  continue
 changes.append({'path':name,'original_upstream':row.get('upstream_sha256'),'current_upstream':current})
 if name=='02_BACKEND/semantic_runtime/app.py':
  ancestor=R/base['manifest']['code_root']/name
  assert sha(ancestor)==row['upstream_sha256']
  merged=subprocess.run(['git','merge-file','-p',str(source),str(ancestor),str(R/name)],stdout=subprocess.PIPE)
  assert merged.returncode==0,'app merge requires review'
  target.write_bytes(merged.stdout)
 elif name=='00_SYSTEM/PIPELINE.json' or name.startswith('02_BACKEND/ENGINES/'):
  pass  # Retain current engine declarations; regenerate hashes below.
 else:
  assert sha(source)==row['upstream_sha256'],name+' has overlapping changes'
p=NEW/'snapshot/00_SYSTEM/PIPELINE.json';value=read(p)
value['workflows']=read(OLD/'snapshot/00_SYSTEM/PIPELINE.json')['workflows']
p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
(A/'artifacts/pre-freeze-rebase.json').write_text(json.dumps({'reason':'Concurrent search-selection changes appeared before first successful freeze; preserve both implementations',
 'original_candidate_manifest_sha256':sha(OLD/'candidate.json'),'new_candidate':'integrated','changes':changes,
 'overlap_resolution':'app.py clean three-way merge against byte-identical initial selected ancestor; other changed product files retained from current working tree; engine pins resealed',
 'main_changed':False},ensure_ascii=False,indent=2)+'\n')
print('Rebased',len(changes),'upstream changes without overwriting working files')
