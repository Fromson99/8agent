"""Bind qualified display repairs onto known field inventories after gap-action R2."""
import ast,base64,gzip,hashlib,importlib.util,json,subprocess,zlib
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_PUBLIC_FAILURE_GUIDANCE_20261014_R1'
G=O.with_name('assessment_gap_action_20261013_r2');P=O.with_name('ad_request_logs_20261013_r2')
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 assert not (O/(N+'.zip')).exists(),'sealed package exists'
 field=load('guidance_field_transform',O/'field_transform.py')
 old=load('guidance_old_builder',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
 prior=load('guidance_ad_installer',P/'apply_patch.py');ps=json.loads(gzip.decompress((P/'PATCH_SPEC.json.gz').read_bytes()))
 si=load('guidance_success_installer',O.with_name('successful_shortcut_20261013_r1')/'apply_patch.py');ss=json.loads(gzip.decompress((O.with_name('successful_shortcut_20261013_r1')/'PATCH_SPEC.json.gz').read_bytes()))
 gi=load('guidance_gap_installer',G/'apply_patch.py');gs=json.loads(gzip.decompress((G/'PATCH_SPEC.json.gz').read_bytes()))
 code=(G/'apply_patch.py').read_text().replace('GENOS_ASSESSMENT_GAP_ACTION_20261013_R2',N).replace('assessment-gap-action-r2','public-failure-guidance-r1').replace("'assessment_gap_action'","'public_failure_guidance'").replace('Source gap action correction; exact original gaps and source verification preserved','ADR-0775 public-display-v4 qualified source; field adaptations preserve existing transport')
 code=code.replace('Install source gap action correction while preserving the verified code and budget overlay.','Install public failure guidance while preserving the verified code and budget overlay.')
 marker="assert 'ModelEventStream'"
 i=code.index(marker)
 code=code[:i]+'''from semantic_runtime import chat_adapter
v=chat_adapter.views()
assert v.DISPLAY_POLICY_REVISION=='public-display-v4'
for status in (401,403,409,413,429,500,502,503,504):
 text=v.render(v.public_failure('install-check',status=status))
 assert text.startswith('현재 충분한 법률 검토를 하지 못했습니다.') and '('+str(status)+')' in text
assert '(timeout)' in v.render(v.public_failure('install-check',exc=TimeoutError('private')))
assert 'private' not in v.render(v.public_failure('install-check',exc=ValueError('private')))
''' +code[i:]
 (O/'apply_patch.py').write_text(code);installer=load('guidance_installer',O/'apply_patch.py')
 names=['main_workflow.py','02_BACKEND/semantic_runtime/app.py','02_BACKEND/semantic_runtime/chat_adapter.py','08_DEPLOYMENT/GENOS/stream_app.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
 active=json.loads((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes());selected=json.loads((R/active['manifest_path']).read_bytes());assert active['generation']==61
 baseline=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0775-public-failure-main/artifacts/design/baseline.json').read_bytes())['manifest'];files={n:sha((R/n).read_bytes()) for n in names}
 for n,h in files.items():
  assert h==selected['files'][n]==sha((R/selected['code_root']/n).read_bytes())
  p=O/'preimage'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((R/baseline['code_root']/n).read_bytes())
 spec={'revision':N,'signatures':{},'blobs':{},'engine_additions':{},'budget_policy':gs['budget_policy']};bindings=[];variants={};cache={}
 def patched(before,manifest,inst,sp):
  state=sp['signatures'][inst.signature(before,manifest,sp)];changes={n:base64.b64decode(sp['blobs'][p['after_sha256']]) for n,p in state['patches'].items()}
  out=old.repin(before,changes,sp['engine_additions']);assert inst.signature(out,manifest,sp)==state['output_signature'];return out
 for label,payload,budget in old.predecessors():
  base=dict(payload);manifest=json.loads(base.pop('CODE_MANIFEST.json'));ad=patched(base,manifest,prior,ps);success=patched(ad,manifest,si,ss)
  for tag,pre in [('stream-fix-r1',base),('ad-request-logs-r2',ad),('successful-shortcut-r1',success)]:
   before=patched(pre,manifest,gi,gs);updates={}
   for n in names:
    p=O/'field-preimage'/n/(sha(before[n])+'.py');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(before[n])
   for n in names:
    key=n,sha(before[n])
    if key not in cache:
     cache[key]=field.transform(before[n],(O/'preimage'/n).read_bytes(),(R/n).read_bytes(),n)
     ast.parse(cache[key],feature_version=(3,10))
    updates[n]=cache[key];spec['blobs'][sha(updates[n])]=base64.b64encode(updates[n]).decode();variants.setdefault(n,{})[key[1]]=sha(updates[n])
   after=old.repin(before,updates,{});installer.verify_bindings(after)
   key=installer.signature(before,manifest,spec);out=installer.signature(after,manifest,spec)
   spec['signatures'][key]={'label':label+'/'+tag+'/gap-action-r2','patches':{n:{'before_sha256':sha(before[n]),'after_sha256':sha(raw)} for n,raw in updates.items()},'output_signature':out}
   bindings.append({'label':label+'/'+tag+'/gap-action-r2','input_signature':key,'output_signature':out})
 (O/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(spec),mtime=0));(O/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(enc(bindings),mtime=0))
 (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files':files,'field_variants':variants,'known_predecessors':len(spec['signatures']),'field_status':'NOT_VERIFIED','model_calls':0,'local_active_release':active['release_id'],'local_active_generation':61}))
 for (n,_),raw in cache.items():
  p=O/'reviewed'/n/(sha(raw)+'.py');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 bundle=enc({'code':base64.b64encode(code.encode()).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py='import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
 py+="bundle=json.loads(raw);module=types.ModuleType('guidance_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
 header=(G/'GENOS_ASSESSMENT_GAP_ACTION_20261013_R2_RUN.txt').read_text().split('python3 - "$@"',1)[0].replace('assessment-gap-action-r2','public-failure-guidance-r1').replace('ASSESSMENT_GAP_ACTION','PUBLIC_FAILURE_GUIDANCE')
 (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'PUBLIC_GUIDANCE_PY\'\n'+py+'PUBLIC_GUIDANCE_PY\n');subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
 diag=(R/'genos_diagnostics.py').read_bytes();packed=base64.b64encode(zlib.compress(diag,9)).decode()
 editor='import base64 as _b64, hashlib as _hash, sys as _sys, types as _types, zlib as _zlib\n'+f'_raw=_zlib.decompress(_b64.b64decode({packed!r}))\nassert _hash.sha256(_raw).hexdigest()=={sha(diag)!r}\n'
 editor+="_module=_types.ModuleType('genos_diagnostics');_module.__file__='<embedded genos_diagnostics>'\nexec(compile(_raw,_module.__file__,'exec'),_module.__dict__);_sys.modules['genos_diagnostics']=_module\n"
 editor+='\n'+(R/names[-1]).read_text();ast.parse(editor,feature_version=(3,10));(O/(N+'_PASTE_ALL.txt')).write_text(editor)
 print(json.dumps({'inventories':len(spec['signatures']),'variants':{n:len(v) for n,v in variants.items()},'run_bytes':(O/(N+'_RUN.txt')).stat().st_size}))
if __name__=='__main__':main()
