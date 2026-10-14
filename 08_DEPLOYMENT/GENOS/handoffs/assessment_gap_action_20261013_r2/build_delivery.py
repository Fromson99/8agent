"""Package only the reviewed gap-action repair over sealed GENOS predecessors."""
import ast,base64,gzip,hashlib,importlib.util,json,subprocess,zlib
from pathlib import Path
O=Path(__file__).resolve().parent
R=O.parents[3]
N='GENOS_ASSESSMENT_GAP_ACTION_20261013_R2'
P=O.with_name('ad_request_logs_20261013_r2')
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 assert not (O/(N+'.zip')).exists(),'sealed package exists'
 old=load('gap_prior_builder',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
 prior=load('gap_prior_installer',P/'apply_patch.py')
 prior_spec=json.loads(gzip.decompress((P/'PATCH_SPEC.json.gz').read_bytes()))
 code=(P/'apply_patch.py').read_text()
 code=code.replace('GENOS_AD_REQUEST_LOGS_20261013_R2',N).replace('ad-request-logs-r2','assessment-gap-action-r2')
 code=code.replace("'model_stream_fix'","'assessment_gap_action'")
 code=code.replace('AD request logs R1 identical implementation; budget-preserving installer R2','Source gap action correction; exact original gaps and source verification preserved')
 code=code.replace('Model stream fix','Assessment gap action').replace('MODEL_STREAM_FIX','ASSESSMENT_GAP_ACTION')
 start=code.index('from semantic_runtime.legal_agent.model_contract import structured_request')
 end=code.index("assert 'ModelEventStream'",start)
 code=code[:start]+'''from semantic_runtime.legal_agent import completion_v5,completion_v6
assert 'source_gap_actions' in inspect.getsource(completion_v5.prepare)
assert 'source_gap_actions' in inspect.getsource(completion_v6.prepare)
gap={'kind':'MISSING_SOURCE','issue_id':'Q1','suggested_action':'REQUEST_FACT','reason':'synthetic','material':True}
raw={'gaps':[gap]}
fixed,audit=cc.source_gap_actions(raw)
assert raw['gaps'][0]['suggested_action']=='REQUEST_FACT'
assert fixed['gaps'][0]['suggested_action']=='RESEARCH' and fixed['gaps'][0]['material']
assert audit[0]['from']=='REQUEST_FACT' and audit[0]['to']=='RESEARCH'
again,changes=cc.source_gap_actions(fixed)
assert again==fixed and not changes
''' + code[end:]
 code=code.replace('Install AD request logging while preserving the verified budget overlay.','Install source gap action correction while preserving the verified code and budget overlay.')
 (O/'apply_patch.py').write_text(code)
 installer=load('gap_installer',O/'apply_patch.py')
 files=json.loads((O/'WORKING_INTEGRATION.json').read_bytes())['source_files']
 assert all(sha((R/n).read_bytes())==h for n,h in files.items())
 spec={'revision':N,'signatures':{},'blobs':{},'engine_additions':{},'budget_policy':prior_spec['budget_policy']}
 bindings=[];variants={}
 success_path=O.with_name('successful_shortcut_20261013_r1')
 success_inst=load('gap_success_installer',success_path/'apply_patch.py')
 success_spec=json.loads(gzip.decompress((success_path/'PATCH_SPEC.json.gz').read_bytes()))
 for label,payload,budget in old.predecessors():
  base=dict(payload);manifest=json.loads(base.pop('CODE_MANIFEST.json'))
  state=prior_spec['signatures'][prior.signature(base,manifest,prior_spec)]
  changes={n:base64.b64decode(prior_spec['blobs'][p['after_sha256']]) for n,p in state['patches'].items()}
  ad=old.repin(base,changes,prior_spec['engine_additions'])
  assert prior.signature(ad,manifest,prior_spec)==state['output_signature']
  success_state=success_spec['signatures'][success_inst.signature(ad,manifest,success_spec)]
  success_changes={n:base64.b64decode(success_spec['blobs'][p['after_sha256']]) for n,p in success_state['patches'].items()}
  success=old.repin(ad,success_changes,success_spec['engine_additions'])
  assert success_inst.signature(success,manifest,success_spec)==success_state['output_signature']
  for tag,before in [('stream-fix-r1',base),('ad-request-logs-r2',ad),('successful-shortcut-r1',success)]:
   updates={n:old.transform(before[n],(O/'preimage'/n).read_bytes(),(R/n).read_bytes(),n) for n in files}
   for n,raw in updates.items():
    ast.parse(raw,feature_version=(3,10));spec['blobs'][sha(raw)]=base64.b64encode(raw).decode()
    variants.setdefault(n,{})[sha(before[n])]=sha(raw)
   after=old.repin(before,updates,{})
   installer.verify_bindings(after)
   key=installer.signature(before,manifest,spec);out=installer.signature(after,manifest,spec)
   spec['signatures'][key]={'label':label+'/'+tag,'patches':{n:{'before_sha256':sha(before[n]),'after_sha256':sha(raw)} for n,raw in updates.items()},'output_signature':out}
   bindings.append({'label':label+'/'+tag,'input_signature':key,'output_signature':out})
 (O/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(spec),mtime=0))
 (O/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(enc(bindings),mtime=0))
 (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files':files,'field_variants':variants,'known_predecessors':len(spec['signatures']),'field_status':'NOT_VERIFIED','model_calls':0,'local_active_release_changed':False}))
 bundle=enc({'code':base64.b64encode(code.encode()).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py='import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
 py+="bundle=json.loads(raw);module=types.ModuleType('gap_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
 header=(P/'GENOS_AD_REQUEST_LOGS_20261013_R2_RUN.txt').read_text().split('python3 - "$@"',1)[0]
 header=header.replace('ad-request-logs-r2','assessment-gap-action-r2').replace('AD_REQUEST_LOGS','ASSESSMENT_GAP_ACTION')
 (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'GAP_ACTION_PY\'\n'+py+'GAP_ACTION_PY\n')
 subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
 print(json.dumps({'inventories':len(spec['signatures']),'source_files':len(files),'variants':variants}))
if __name__=='__main__':main()
