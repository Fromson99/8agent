"""Execute the actual attached TXT; all fixtures are synthetic and local."""
import json,os,subprocess,sys,gzip,zipfile,ast
from pathlib import Path
from tempfile import TemporaryDirectory
import build_delivery as b
OUT=b.OUT;ROOT=b.ROOT;NAME=b.NAME;RUN=OUT/(NAME+'_RUN.txt')

def main():
 results=[];transcript=[];tested=set();wanted={
  'GENOS_QUERY_LATENCY_20261007_R4', 'GENOS_QUERY_LATENCY_20261007_R3',
  'GENOS_CM_ONECLICK_20261008_R15','GENOS_CM_ONECLICK_20261008_R14'}
 for label,before in b.states():
  family=label.split('/')[0];suffix='r5' if label.endswith('/applied-display-r5') else 'base'
  key=(family,suffix)
  if family not in wanted or key in tested or (suffix=='base' and '/applied-display-' in label):continue
  tested.add(key)
  with TemporaryDirectory(prefix='focused-handoff-check-') as td:
   tmp=Path(td);root=tmp/'DEV';root.mkdir();b.write_payload(root,before)
   env={**os.environ,'GENOS_DEV_ROOT':str(root),'GENOS_PYTHON_DIR':str(ROOT/'.venv/bin'),
    'PYTHONPATH':str(root/'02_BACKEND')+':'+str(ROOT/'05_TESTS/CONTRACTS')+':'+str(ROOT/'05_TESTS/REGRESSION/core'),
    'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root),'GENOS_AUTO_WARMUP':'0','AD_WORKER_ENABLED':'0'}
   for k in ('GENOS_GENERATION','GENOS_DATA_ROOT','GENOS_PATCH_DEV'):env.pop(k,None)
   # Synthetic selected generation identity for existing CM operator-fixed binding.
   if b.load('field_app',OUT/'apply_patch.py').CONFIG in before:
    gen=tmp/'generation';gen.mkdir();(gen/'manifest.json').write_text('{"mock": true}')
    env['GENOS_GENERATION']=str(gen)
   def run(*args,okay=True):
    r=subprocess.run(['bash',str(RUN),*args],cwd=root,env=env,text=True,capture_output=True,timeout=90)
    transcript.append({'basis':label,'command':list(args),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    assert (r.returncode==0)==okay,r.stdout+r.stderr
    return r
   run('check');run('apply');run('apply');run('verify')
   backup=next((root/'TRANSFER/rag-focused-rules-r1').glob('backup-*'))
   with zipfile.ZipFile(backup/'APPLIED_CODE.zip') as z:
    assert all((root/n).read_bytes()==z.read(n) for n in z.namelist())
    assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
   protected=['service.py','00_SYSTEM/GENOS_SERVING_PATHS.json','02_BACKEND/semantic_runtime/resident_data.py','02_BACKEND/semantic_runtime/runtime_cache.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','02_BACKEND/semantic_runtime/legal_agent/transport.py']
   assert all((root/n).read_bytes()==before[n] for n in protected if n in before)
   tests=['test_focused_input_modality.py','test_navigation_input_compaction.py','test_single_rule_content.py','test_source_span_norm.py','test_followup_structure_lookup.py','test_document_focus.py','test_main50_request_repair.py','test_completion_v4.py']
   if family.endswith('_R4') and suffix=='r5':
    for source in (ROOT/'00_SYSTEM').rglob('*.json'):
     dest=root/source.relative_to(ROOT)
     if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source.read_bytes())
    # Fixture-only builder dependency: old serving compiler does not import it.
    helper=root/'02_BACKEND/semantic_runtime/factorized_audit.py'
    if not helper.exists():helper.write_bytes((ROOT/'02_BACKEND/semantic_runtime/factorized_audit.py').read_bytes())
    (root/'.venv').symlink_to(ROOT/'.venv',target_is_directory=True)
    testdir=root/'05_TESTS/CONTRACTS';testdir.mkdir(parents=True)
    for source in (ROOT/'05_TESTS/CONTRACTS').glob('*.py'):(testdir/source.name).write_bytes(source.read_bytes())
    # GENOS service passes an explicit runtime_root; local default layout is a different workspace.
    for test_name in ('test_focused_input_modality.py','test_single_rule_content.py','test_source_span_norm.py','test_main50_request_repair.py'):
     test_path=testdir/test_name;test_source=test_path.read_text()
     test_path.write_text(test_source.replace('contracts_root=ROOT,', "runtime_root=tmp_path/'runtime',contracts_root=ROOT,"))
    cmd=[str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0693/run_contracts.py'),str(root),*[str(testdir/t) for t in tests],'--junitxml='+str(OUT/'CONTRACTS.xml')]
    r=subprocess.run(cmd,cwd=root,env=env,text=True,capture_output=True,timeout=180)
    (OUT/'CONTRACTS.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
    print(r.stdout.splitlines()[-1],flush=True)
   target=root/'02_BACKEND/semantic_runtime/legal_agent/completion_v8.py';saved=target.read_bytes();target.write_bytes(saved+b'\n# unknown edit\n')
   run('verify',okay=False);run('undo',str(backup),okay=False);assert target.read_bytes()==saved+b'\n# unknown edit\n'
   target.write_bytes(saved);run('undo',str(backup));assert all((root/n).read_bytes()==raw for n,raw in before.items())
   for n in b.chosen_paths():
    if n not in before:assert not (root/n).exists()
   target=root/'service.py';target.write_bytes(target.read_bytes()+b'\n# unknown code\n');saved=target.read_bytes()
   run('check',okay=False);run('apply',okay=False);assert target.read_bytes()==saved
   results.append({'label':label,'passed':True,'commands':9,'protected_paths_unchanged':True});print(label+' PASS',flush=True)
 with gzip.open(OUT/'DELIVERY_TESTS.json.gz','wt',encoding='utf-8') as f:json.dump(transcript,f,ensure_ascii=False)
 (OUT/'VALIDATION.json').write_bytes(b.encoded({'variants':results,'txt_commands':sum(v['commands'] for v in results),'run_txt_sha256':b.sha(RUN.read_bytes()),'model_calls':0,'GENOS_deployed':False}))
if __name__=='__main__':main()
