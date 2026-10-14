"""Seal standalone-SSE R10 over frozen predecessors without replacing CM/budget/error code."""
import ast
import base64
from contextlib import redirect_stdout
from datetime import datetime, timezone
import gzip
from functools import lru_cache
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
PRIOR=OUT.with_name('rag_progress_graph_20261008_r4')
SYSTEM=OUT.with_name('system_logging_20261007_r1')
NAME='GENOS_RAG_PROGRESS_GRAPH_20261008_R5'
OWN=('02_BACKEND/semantic_runtime/progress.py','02_BACKEND/semantic_runtime/chat_adapter.py',
 '08_DEPLOYMENT/GENOS/stream_app.py','08_DEPLOYMENT/GENOS/start_sse.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py',
 '07_DOCS/REFERENCE/OPERATIONS/GENOS_STANDALONE_JUDGMENT_SVG_20261008.md',
 'genos_diagnostics.py','genos_log_runner.py','main_workflow.py','06_TOOLS/COMMANDS/code_ship.py')
sha=lambda raw:hashlib.sha256(raw).hexdigest()
encoded=lambda obj:(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
signature=lambda pins:sha(json.dumps(pins,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def write_payload(root,payload):
 for name,raw in payload.items():
  path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

@lru_cache(maxsize=1)
def source_material():
 build=load('frozen_r4_builder',PRIOR/'build_delivery.py')
 catalogue,bases,cm=build.source_material()
 hand=json.loads((PRIOR/'HANDOFF.json').read_bytes());archive=PRIOR/(hand['version']+'.zip')
 assert sha(archive.read_bytes())==hand['code_zip_sha256']
 with zipfile.ZipFile(archive) as z:
  spec=json.loads(gzip.decompress(z.read('PATCH_SPEC.json.gz')))
  assert z.read('apply_display.py')==(PRIOR/'apply_display.py').read_bytes()
 install=load('frozen_r4_installer',PRIOR/'apply_display.py')
 assert set(bases)==set(spec['signatures'])
 for state in list(bases.values()):
  payload={n:catalogue[p] for n,p in state['pins'].items()};payload['CODE_MANIFEST.json']=state['manifest']
  if state.get('config'):payload[install.CONFIG]=state['config']
  with TemporaryDirectory(prefix='r5-frozen-r4-') as td,redirect_stdout(io.StringIO()):
   root=Path(td);write_payload(root,payload);_,_,changes,_=install.prepared(root,spec)
  final={**payload,**changes};pins=install.normalized_inventory(final,json.loads(final['CODE_MANIFEST.json']),spec)
  for raw in final.values():catalogue.setdefault(sha(raw),raw)
  bases.setdefault(signature(pins),{'label':state['label']+'/applied-display-r4','pins':pins,
     'manifest':final['CODE_MANIFEST.json'],'config':state.get('config')})
 return catalogue,bases,cm

def states():
 catalogue,bases,_=source_material()
 for state in bases.values():
  payload={n:catalogue[p] for n,p in state['pins'].items()};payload['CODE_MANIFEST.json']=state['manifest']
  if state.get('config'):payload['00_SYSTEM/GENOS_SERVING_PATHS.json']=state['config']
  yield state['label'],payload,None

def main():
 assert not (OUT/(NAME+'.zip')).exists(),'Use a new revision after sealing'
 apply=load('standalone_r5_installer',OUT/'apply_display.py');catalogue,bases,cm=source_material()
 owned={n:(ROOT/n).read_bytes() for n in OWN}
 system=json.loads((SYSTEM/'HANDOFF.json').read_bytes())
 with zipfile.ZipFile(SYSTEM/(system['version']+'.zip')) as z:
  for n in ('genos_diagnostics.py','genos_log_runner.py'):owned[n]=z.read(n)
 operations=json.loads((OUT/'LOG_OPERATIONS.json').read_bytes())
 spec={'revision':NAME,'signatures':{},'blobs':{},'budget_policy':cm['investigation_budget_overlay']['spec']}
 bindings=[]
 for key,state in bases.items():
  before={n:catalogue[p] for n,p in state['pins'].items()};before['CODE_MANIFEST.json']=state['manifest']
  if state.get('config'):before[apply.CONFIG]=state['config']
  final={**before,**owned}
  for name,changes in operations.items():
   text=before[name].decode()
   for op in changes:
    assert text.count(op['before'])==1,(state['label'],name,op['before'][:100])
    text=text.replace(op['before'],op['after'],1)
   if name.endswith('readable_log.py') and '전체 오류·복구 기록 (생략 없음)' not in text:
    prefix="def render_detail(label, value):\n"
    guard=("    error_kind = label.removeprefix('AGENT ').replace(' ', '_')\n"
      "    if (label.startswith('AGENT ') and (error_kind.endswith(('_FAILED', '_REJECTED')) or error_kind in {'LAW_DECISION_RETRY','LAW_DECISION_PATCH_PROPOSED','OUTPUT_SCHEMA_INVALID','INVESTIGATION_BOUNDED_STOP'})) or label in {'WORKFLOW REPAIR','SEMANTIC REPAIR'}:\n"
      "        return '전체 오류·복구 기록 (생략 없음)\\n'+json.dumps(value,ensure_ascii=False,indent=2,default=str)\n")
    assert text.count(prefix)==1
    text=text.replace(prefix,prefix+guard,1)
   final[name]=text.encode()
  base=before['02_BACKEND/semantic_runtime/legal_agent/unified_rag.py']
  old=b'        payload=super().stage(stage,state,parts,utterance,format)\n'
  replacement=(b'        from .corrected_memory import Reenter\n        try:\n            payload=super().stage(stage,state,parts,utterance,format)\n'
   b"        except Reenter as recovery:\n            self.s.work.event('CASE_STAGE_REENTRY', {'from_stage':stage,'stage':recovery.stage,\n"
   b"                'gaps':recovery.payload.get('gaps',[]),'reason':recovery.reason})\n            raise\n")
  if b'CASE_STAGE_REENTRY' not in base:
   assert base.count(old)==1;final['02_BACKEND/semantic_runtime/legal_agent/unified_rag.py']=base.replace(old,replacement)
  changed={n for n,v in final.items() if n!='CODE_MANIFEST.json' and v!=before.get(n)}
  pipeline=json.loads(before['00_SYSTEM/PIPELINE.json'])
  for entry in pipeline['engines'].values():
   name=entry['manifest'];engine=json.loads(before[name])
   for target in set(engine['files'])&changed:engine['files'][target]=sha(final[target])
   final[name]=encoded(engine);entry['sha256']=sha(final[name])
  final['00_SYSTEM/PIPELINE.json']=encoded(pipeline);apply.verify_bindings(final)
  patches={};engine_paths={entry['manifest'] for entry in pipeline['engines'].values()}
  for name,raw in final.items():
   if name=='CODE_MANIFEST.json' or raw==before.get(name) or name=='00_SYSTEM/PIPELINE.json' or name in engine_paths:continue
   if name.endswith('.py'):ast.parse(raw,feature_version=(3,10))
   pin=sha(raw);spec['blobs'][pin]=base64.b64encode(raw).decode()
   patches[name]={'before_sha256':sha(before[name]) if name in before else None,'after_sha256':pin}
  output=signature(apply.normalized_inventory(final,json.loads(state['manifest']),spec))
  spec['signatures'][key]={'label':state['label'],'patches':patches,'output_signature':output}
  assert apply.signature(before,json.loads(state['manifest']),spec)==key
  protected=('service.py','02_BACKEND/lawrag/pipeline/shortcut_package.py','02_BACKEND/semantic_runtime/legal_agent/law_navigation.py')
  assert all(final.get(n)==before.get(n) for n in protected)
  assert (final.get(apply.CONFIG)==before.get(apply.CONFIG))
  bindings.append({'basis':state['label'],'before_signature':key,'after_signature':output,
    'modified_paths':sorted(patches),'service_sha256':sha(before['service.py']),
    'config_preserved':True,'narrow_log_operations':True,'static_hash_and_contracts_passed':True})
 code=(OUT/'apply_display.py').read_bytes();bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
 packed=base64.b64encode(zlib.compress(bundle,9)).decode();embed=load('frozen_logging_embed',SYSTEM/'build_delivery.py')
 python=('import base64,hashlib,json,os,sys,types,zlib\nfrom pathlib import Path\n'
  +embed.embedded_module('genos_diagnostics',owned['genos_diagnostics.py'])
  +embed.embedded_module('genos_log_runner',owned['genos_log_runner.py'])
  +f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
  +"bundle=json.loads(raw);module=types.ModuleType('r5_display_installer')\n"
  +"exec(compile(base64.b64decode(bundle['code']),'apply_display.py','exec'),module.__dict__)\n"
  +"if os.environ.get('GENOS_DISPLAY_CHILD')=='1':\n raise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_DISPLAY_DEV'],*sys.argv[2:]]))\n"
  +"os.environ['GENOS_DISPLAY_CHILD']='1'\nos.environ.setdefault('GENOS_SYSTEM_LOG_DIR','/nfs-root/diamo/8-agent/logs/system')\n"
  +"os.environ.setdefault('GENOS_LOG_RUN_ID','display-r5-'+sys.modules['genos_diagnostics'].uuid.uuid4().hex[:16])\n"
  +"raise SystemExit(sys.modules['genos_log_runner'].main(['--phase','display-r5-deploy','--','bash',sys.argv[1],*sys.argv[2:]]))\n")
 prior_run=(PRIOR/'GENOS_RAG_PROGRESS_GRAPH_20261008_R4_RUN.txt').read_text()
 run=prior_run[:prior_run.index("python3 - \"${BASH_SOURCE[0]}\"")].replace('R4','R5').replace('display-r4','display-r5').replace('graph-r4','graph-r5')
 run+='python3 - "${BASH_SOURCE[0]}" "$@" <<\'RAG_DISPLAY_PY\'\n'+python+'RAG_DISPLAY_PY\n'
 workflow=('import base64,hashlib,os,sys,types,zlib\nfrom pathlib import Path\n'
  +embed.embedded_module('genos_diagnostics',owned['genos_diagnostics.py'])+owned['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'].decode())
 ast.parse(workflow,feature_version=(3,10));ast.parse(python,feature_version=(3,10))
 (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
 (OUT/(NAME+'_RUN.txt')).write_text(run);(OUT/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_text(workflow)
 subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
 for name,raw in owned.items():
  path=OUT/'payload'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
 (OUT/'SOURCE_BINDING.json').write_bytes(encoded({'variants':bindings,'prior_zip_sha256':sha((PRIOR/'GENOS_RAG_PROGRESS_GRAPH_20261008_R4.zip').read_bytes()),'model_calls':0}))
 pointer=ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
 record={'version':NAME,'created_at':datetime.now(timezone.utc).isoformat(),'working_root':str(ROOT),
  'working_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'known_code_signatures':len(bindings),'run_txt_sha256':sha(run.encode()),'workflow_txt_sha256':sha(workflow.encode()),
  'display_revision':'judgment-evidence-svg-20261008-r10','progress_revision':'rag-current-judgment-20261008-r2',
  'judgment_log_revision':'sse-current-judgment-20261008-r1','execution_mode':'separate-sse-server','asgi_app':'stream_app:app',
  'source_sha256':{n:sha(v) for n,v in owned.items()},'local_active_pointer_sha256':sha(pointer.read_bytes()),
  'local_active_pointer_changed':False,'field_generation':None,'field_generation_manifest_sha256':None,
  'field_git_commit':None,'field_code_serving_revision':None,'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT'}
 (OUT/'HANDOFF.json').write_bytes(encoded(record))
 print(json.dumps({'states':len(bindings),'run_bytes':len(run.encode()),'spec_bytes':(OUT/'PATCH_SPEC.json.gz').stat().st_size}))

if __name__=='__main__':main()
