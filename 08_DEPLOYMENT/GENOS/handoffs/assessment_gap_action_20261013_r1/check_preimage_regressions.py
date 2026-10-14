"""Re-run the existing recovery contracts in an isolated pre-fix code tree."""
import gzip,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3]
sha=lambda b:hashlib.sha256(b).hexdigest()
with tempfile.TemporaryDirectory(prefix='assessment-gap-preimage-') as temp:
 root=Path(temp)/'code';root.mkdir()
 config=json.loads((R/'00_SYSTEM/PIPELINE.json').read_bytes());names=set()
 for entry in config['engines'].values():
  names.add(entry['manifest']);names.update(json.loads((R/entry['manifest']).read_bytes())['files'])
 names.update(str(p.relative_to(R)) for p in (R/'00_SYSTEM').rglob('*.json'))
 names.update(str(p.relative_to(R)) for p in (R/'02_BACKEND/semantic_runtime').rglob('*.py'))
 names.update(str(p.relative_to(R)) for p in (R/'05_TESTS/CONTRACTS').glob('*.py'))
 names.update(str(p.relative_to(R)) for p in R.glob('*.py'))
 names.update(str(p.relative_to(R)) for p in (R/'08_DEPLOYMENT/GENOS').glob('*.py'))
 names.update(str(p.relative_to(R)) for p in (R/'08_DEPLOYMENT/GENOS/workflow').glob('*.py'))
 names.update(['main.py','main_workflow.py','service.py','02_BACKEND/lawrag/__init__.py','02_BACKEND/lawrag/pipeline/__init__.py'])
 for n in names:
  src=R/n
  if not src.is_file():continue
  dest=root/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
 original_sources=json.loads((O/'FINDINGS.json').read_bytes())['files']
 for n in original_sources:
  (root/n).write_bytes((O/'preimage'/n).read_bytes())
 config=json.loads((root/'00_SYSTEM/PIPELINE.json').read_bytes())
 enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
 for e in config['engines'].values():
  p=root/e['manifest'];engine=json.loads(p.read_bytes())
  for n,h in original_sources.items():
   if n in engine['files']:engine['files'][n]=h
  p.write_bytes(enc(engine));e['sha256']=sha(p.read_bytes())
 (root/'00_SYSTEM/PIPELINE.json').write_bytes(enc(config))
 (root/'.venv').symlink_to(R/'.venv',target_is_directory=True)
 env={**os.environ,'PYTHONPATH':str(root/'02_BACKEND')+':'+str(R/'05_TESTS'),'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'AD_WORKER_ENABLED':'0','GENOS_AUTO_WARMUP':'0'}
 # The API's StageRunner verifies the selected pipeline, including restored pins.
 # Unrelated ingestion engines are not exercised by these recovery contracts.
 argv=[str(R/'.venv/bin/python'),str(O/'run_installed_tests.py'),str(R/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py'),str(root),str(root/'05_TESTS/CONTRACTS/test_unified_memory_recovery.py'),'--junitxml='+str(O/'PREIMAGE_RECOVERY.xml')]
 result=subprocess.run(argv,cwd=root,env=env,text=True,capture_output=True,timeout=90)
 (O/'PREIMAGE_RECOVERY.log.gz').write_bytes(gzip.compress((result.stdout+result.stderr).encode(),mtime=0))
 (O/'PREIMAGE_RECOVERY.json').write_text(json.dumps({'returncode':result.returncode,'code_root':str(root),'snapshot_removed_after_test':True,'binding_verification':'actual selected API StageRunner','restored_sources':json.loads((O/'FINDINGS.json').read_bytes())['files'],'scope':'Existing synthetic unit regressions; same working tree except exact 3 pre-fix files and their pre-fix engine/PIPELINE pins. No active pointer, model calls or product evaluation.'},indent=2)+'\n')
 print(result.stdout[-2600:]);print(result.stderr[-1800:])
