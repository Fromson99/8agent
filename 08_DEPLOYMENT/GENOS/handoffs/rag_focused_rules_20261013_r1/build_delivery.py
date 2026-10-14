"""Compose MAIN53 RAG modules over immutable GENOS handoff inventories."""
import ast,base64,gzip,hashlib,importlib.util,io,json,subprocess,zlib,zipfile
from contextlib import redirect_stdout
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3];PRIOR=OUT.with_name('rag_progress_graph_20261008_r5')
NAME='GENOS_RAG_FOCUSED_RULES_20261013_R1'
NEW=ROOT/'08_DEPLOYMENT/RELEASES/focused-rules-20261013-r1/code'
BASE=ROOT/'08_DEPLOYMENT/RELEASES/session-runtime-v6-20261007-r1/code'
sha=lambda b:hashlib.sha256(b).hexdigest()
encoded=lambda o:(json.dumps(o,ensure_ascii=False,indent=2)+'\n').encode()
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def write_payload(root,payload):
 for n,raw in payload.items():p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
@lru_cache(maxsize=1)
def source_material():
 cache=OUT/'BUILD_INPUTS.json.gz'
 if cache.exists():
  obj=json.loads(gzip.decompress(cache.read_bytes()));return {h:base64.b64decode(v) for h,v in obj['blobs'].items()},obj['states'],obj['budget_policy']
 b=load('frozen_r5_builder',PRIOR/'build_delivery.py');catalogue,bases,_=b.source_material()
 a=load('frozen_r5_apply',PRIOR/'apply_display.py');spec=json.loads(gzip.decompress((PRIOR/'PATCH_SPEC.json.gz').read_bytes()))
 for state in list(bases.values()):
  payload={n:catalogue[h] for n,h in state['pins'].items()};payload['CODE_MANIFEST.json']=state['manifest']
  if state.get('config'):payload[a.CONFIG]=state['config']
  with TemporaryDirectory(prefix='focused-r5-') as td,redirect_stdout(io.StringIO()):
   root=Path(td);write_payload(root,payload);_,_,changes,_=a.prepared(root,spec)
  final={**payload,**changes};pins=a.normalized_inventory(final,json.loads(final['CODE_MANIFEST.json']),spec)
  for v in final.values():catalogue.setdefault(sha(v),v)
  bases.setdefault(b.signature(pins),{'label':state['label']+'/applied-display-r5','pins':pins,'manifest':final['CODE_MANIFEST.json'],'config':state.get('config')})
 states=[]
 for state in bases.values():
  catalogue.setdefault(sha(state['manifest']),state['manifest'])
  pins={**state['pins'],'CODE_MANIFEST.json':sha(state['manifest'])}
  if state.get('config'):catalogue.setdefault(sha(state['config']),state['config']);pins[a.CONFIG]=sha(state['config'])
  states.append({'label':state['label'],'pins':pins})
 cache.write_bytes(gzip.compress(encoded({'blobs':{h:base64.b64encode(v).decode() for h,v in catalogue.items()},'states':states,'budget_policy':spec['budget_policy']}),mtime=0))
 return catalogue,states,spec['budget_policy']
def states():
 c,s,_=source_material()
 for row in s:yield row['label'],{n:c[h] for n,h in row['pins'].items()}

def chosen_paths():
 # Transport/provider, cache, CM storage and workflow editor remain field-owned.
 exclude={'local_gemma.py','transport.py','core_evidence_route.py','shortcut_repository.py','knowledge_repository.py','wiki_execution.py','shortcut_cases.py','repository.py','readable_log.py','investigation_diagnostics.py','workflow_tiers_policy.py'}
 return [p.relative_to(NEW).as_posix() for p in sorted((NEW/'02_BACKEND/semantic_runtime/legal_agent').glob('*.py')) if p.name not in exclude and (not (BASE/p.relative_to(NEW)).exists() or (BASE/p.relative_to(NEW)).read_bytes()!=p.read_bytes())]+['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json','02_BACKEND/semantic_runtime/execution_metrics.py','02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py']

@lru_cache(maxsize=None)
def merged(n,field):
 if n.endswith('/core_evidence_route.py') and field is not None:return field
 reviewed=OUT/'reviewed'/(Path(n).name+'.'+sha(field)+'.py') if field else None
 if reviewed and reviewed.exists():return reviewed.read_bytes()
 new=(NEW/n).read_bytes();old=(BASE/n).read_bytes() if (BASE/n).exists() else None
 if field is None or field==old or field==new:return new
 if old is None:raise ValueError('New module collides '+n)
 with TemporaryDirectory(prefix='focused-merge-') as td:
  d=Path(td);(d/'field').write_bytes(field);(d/'base').write_bytes(old);(d/'new').write_bytes(new)
  p=subprocess.run(['git','merge-file','-p','--diff3',str(d/'field'),str(d/'base'),str(d/'new')],capture_output=True)
  if p.returncode:
   conflict=OUT/'merge-review'/f'{Path(n).name}.{sha(field)[:12]}.txt';conflict.parent.mkdir(exist_ok=True);conflict.write_bytes(p.stdout)
   raise ValueError('Review required '+str(conflict))
  return p.stdout

def main():
 catalogue,bases,budget=source_material();paths=chosen_paths();issues=[];results={}
 for n in paths:
  for h in {state['pins'].get(n) for state in bases}:
   try:results[(n,h)]=merged(n,catalogue[h] if h else None)
   except ValueError as e:issues.append(str(e))
 (OUT/'MERGE_REVIEW.json').write_bytes(encoded({'paths':paths,'variants':len(results),'issues':issues,'states':len(bases)}))
 print(json.dumps({'paths':len(paths),'variants':len(results),'issues':issues,'states':len(bases)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()

def build():
 assert not (OUT/(NAME+'.zip')).exists(),'Preserve sealed delivery'
 app=load('focused_apply',OUT/'apply_patch.py');catalogue,bases,budget=source_material();paths=chosen_paths()
 release=json.loads((NEW.parent/'release.json').read_bytes())
 for n,h in release['files'].items():assert sha((NEW/n).read_bytes())==h,n
 selected_pipeline=json.loads((NEW/'00_SYSTEM/PIPELINE.json').read_bytes())
 additions={entry['manifest']:[n for n in json.loads((NEW/entry['manifest']).read_bytes())['files'] if n in paths] for entry in selected_pipeline['engines'].values()}
 spec={'revision':NAME,'signatures':{},'blobs':{},'budget_policy':budget,'engine_additions':additions}
 bindings=[];deltas=set();newpins={}
 for state in bases:
  before={n:catalogue[h] for n,h in state['pins'].items()};manifest=json.loads(before['CODE_MANIFEST.json'])
  final=dict(before);patches={}
  for n in paths:
   raw=merged(n,before.get(n))
   if raw==before.get(n):continue
   if n.endswith('.py'):ast.parse(raw,feature_version=(3,10))
   final[n]=raw;h=sha(raw);spec['blobs'][h]=base64.b64encode(raw).decode();newpins.setdefault(n,set()).add(h)
   patches[n]={'before_sha256':sha(before[n]) if n in before else None,'after_sha256':h}
  pipeline=json.loads(before['00_SYSTEM/PIPELINE.json'])
  for entry in pipeline['engines'].values():
   n=entry['manifest'];engine=json.loads(before[n])
   for target in set(engine['files'])&set(patches):engine['files'][target]=sha(final[target])
   for target in additions.get(n,[]):engine['files'][target]=sha(final[target])
   final[n]=encoded(engine);entry['sha256']=sha(final[n])
  final['00_SYSTEM/PIPELINE.json']=encoded(pipeline);app.verify_bindings(final)
  key=app.signature(before,manifest,spec);output=app.signature(final,manifest,spec)
  spec['signatures'][key]={'label':state['label'],'patches':patches,'output_signature':output}
  protected=['service.py',app.CONFIG,'02_BACKEND/semantic_runtime/runtime_cache.py','02_BACKEND/semantic_runtime/resident_data.py','02_BACKEND/semantic_runtime/legal_agent/transport.py','02_BACKEND/semantic_runtime/progress.py','02_BACKEND/semantic_runtime/chat_adapter.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','02_BACKEND/semantic_runtime/legal_agent/core_evidence_route.py']
  assert all(final.get(n)==before.get(n) for n in protected if n in before)
  for n in paths:
   if final[n]!= (NEW/n).read_bytes():deltas.add(n)
  bindings.append({'label':state['label'],'before_signature':key,'after_signature':output,'modified_paths':sorted(patches),'protected_paths_unchanged':True})
 for n,pins in newpins.items():
  for h in pins:
   raw=base64.b64decode(spec['blobs'][h]);p=OUT/'payload'/h/Path(n).name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
 (OUT/'SOURCE_BINDING.json').write_bytes(encoded({'source_release':'focused-rules-20261013-r1','source_release_sha256':sha((NEW.parent/'release.json').read_bytes()),'source_files':{n:sha((NEW/n).read_bytes()) for n in paths},'field_composition_differences':sorted(deltas),'variants':bindings,'model_calls':0,'field_validation':'NOT_RUN'}))
 code=(OUT/'apply_patch.py').read_bytes();bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py=("import base64,hashlib,json,os,sys,types,zlib\n"+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'+"bundle=json.loads(raw);module=types.ModuleType('focused_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
 run='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
export GENOS_PATCH_DEV="${GENOS_DEV_ROOT:-${GENOS_DEV:-$HOME/DEV}}"
task_logs="$GENOS_PATCH_DEV/TRANSFER/rag-focused-rules-r1/bootstrap-logs"
if ! mkdir -p -- "$task_logs"; then task_logs="${TMPDIR:-/tmp}/8-agent-focused-rules-$(id -u)"; mkdir -p -- "$task_logs"; fi
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "FOCUSED_RAG_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_log.exit"' EXIT
printf 'FOCUSED_RAG_LOG=%s\\n' "$task_log"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
if [[ $# -eq 0 ]]; then set -- apply; fi
python3 - "$@" <<'FOCUSED_RAG_PY'
'''+py+'FOCUSED_RAG_PY\n'
 (OUT/(NAME+'_RUN.txt')).write_text(run);subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
 (OUT/'HANDOFF.json').write_bytes(encoded({'version':NAME,'transfer_only':True,'source_release':'focused-rules-20261013-r1','source_release_manifest_sha256':sha((NEW.parent/'release.json').read_bytes()),'source_selected_code_root':str(NEW),'source_git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'known_code_signatures':len(bindings),'run_txt_sha256':sha(run.encode()),'local_active_pointer_sha256':sha((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()),'field_code_root':'~/DEV','field_generation':None,'field_generation_manifest_sha256':None,'field_git_commit':None,'field_code_serving_revision':None,'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT','rebuild_required':False,'workflow_editor_change_required':False}))
 print(json.dumps({'states':len(bindings),'patched_module_variants':len(spec['blobs']),'run_bytes':len(run.encode()),'field_differences':sorted(deltas)}),flush=True)

if __name__=='__main__':build()
