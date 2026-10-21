"""Bind current tool eligibility fixes to sealed schema/dependency field bases."""
import ast,base64,gzip,hashlib,importlib.util,json,subprocess,zipfile,zlib
from copy import deepcopy
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];P=O.with_name('dependency_recovery_20261014_r1')
N='GENOS_TOOL_AVAILABILITY_20261014_R1';A=R/'09_ARTIFACTS/AUDITS/20261014-tool-availability'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def predecessors():
 parent=load('availability_previous_builder',P/'build_delivery.py')
 installer=load('availability_previous_installer',P/'apply_patch.py')
 transform=load('availability_repin',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
 spec=json.loads(gzip.decompress((P/'PATCH_SPEC.json.gz').read_bytes()))
 for label,before,manifest,budget in parent.predecessors():
  yield label,before,manifest,budget
  state=spec['signatures'][installer.signature(before,manifest,spec)]
  updates={n:base64.b64decode(spec['blobs'][row['after_sha256']]) for n,row in state['patches'].items()}
  after=transform.repin(before,updates,spec['engine_additions'])
  assert installer.signature(after,manifest,spec)==state['output_signature']
  mf=deepcopy(manifest);installer.rebind(mf,{n:(sha(before[n]),sha(raw)) for n,raw in after.items() if n in before and raw!=before[n]})
  mf['files']=[{'path':n,'sha256':sha(raw),'bytes':len(raw)} for n,raw in sorted(after.items())];mf['id']='GENOS_DEPENDENCY_RECOVERY_20261014_R1'
  yield label+'/dependency-recovery-r1',after,mf,budget

def main():
 assert not (O/(N+'.zip')).exists(),'Preserve sealed delivery'
 installer=load('availability_installer',O/'apply_patch.py');transform=load('availability_transform',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
 receipt=json.loads((A/'regression-final-result.json').read_bytes())
 assert receipt['exit_code']==0 and receipt['product_unchanged'] and receipt['test_files_unchanged']
 source={n:(R/n).read_bytes() for n in receipt['product_sha256']}
 assert all(sha(b)==receipt['product_sha256'][n] for n,b in source.items())
 selected=R/'08_DEPLOYMENT/RELEASES/schema-recovery-20261014-r1/code'
 baseline={n:(selected/n).read_bytes() for n in source if (selected/n).exists()}
 diagnostic='02_BACKEND/semantic_runtime/legal_agent/investigation_diagnostics.py'
 source[diagnostic]=(R/diagnostic).read_bytes();working=dict(source)
 previous=json.loads((P/'SOURCE_BINDING.json').read_bytes())
 diagnostic_map={before:base64.b64decode(json.loads(gzip.decompress((P/'PATCH_SPEC.json.gz').read_bytes()))['blobs'][after]) for before,after in previous['field_variants'][diagnostic].items()}
 diagnostic_map.update({sha(b):b for b in list(diagnostic_map.values())})
 baseline[diagnostic]=(P/'preimage'/diagnostic).read_bytes()
 spec={'revision':N,'signatures':{},'blobs':{},'engine_additions':{}}
 variants={};cache={};bindings=[];fixtures=[]
 for label,before,manifest,budget in predecessors():
  spec['budget_policy']=budget;updates={}
  for n,target in source.items():
   pre=sha(before[n]) if n in before else 'ABSENT';key=n,pre
   if key not in cache:
    if n==diagnostic:raw=diagnostic_map[pre]
    elif n.endswith('/shortcut_cases.py'):
     anchor=b'        self.admit(command,context)\n'
     guard=(b"        # The resolver's exhausted-repair result is a terminal clarification,\n"
            b'        # not a full executable command. Match Memory._execute\'s consumer.\n'
            b"        if command['action']=='CLARIFY':\n"
            b"            return {'status':'CLARIFY','answer':None,'reason':command['reason']}\n")
     assert target.count(guard)==1 and before[n].count(anchor)==1
     raw=before[n].replace(anchor,guard+anchor)
     assert raw.replace(guard,b'')==before[n], 'Preserve all field routing policies'

    elif n not in before:assert n not in baseline;raw=target
    elif before[n]==target:raw=target
    elif n in ('02_BACKEND/semantic_runtime/legal_agent/law_navigation.py','02_BACKEND/semantic_runtime/legal_agent/investigation_scope.py','02_BACKEND/semantic_runtime/legal_agent/output_contract.py','02_BACKEND/semantic_runtime/legal_agent/case_repository.py') and label.endswith('/dependency-recovery-r1'):
     raw=transform.transform(before[n],(P/'payload'/n).read_bytes(),target,n)
    else:raw=transform.transform(before[n],baseline[n],target,n)
    ast.parse(raw,feature_version=(3,10));cache[key]=raw
   updates[n]=cache[key];variants.setdefault(n,{})[pre]=sha(cache[key]);spec['blobs'][sha(cache[key])]=base64.b64encode(cache[key]).decode()
  new='02_BACKEND/semantic_runtime/legal_agent/tool_availability.py'
  for entry in json.loads(before['00_SYSTEM/PIPELINE.json'])['engines'].values():
   mf=entry['manifest']
   if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in json.loads(before[mf])['files']:spec['engine_additions'][mf]=[new]
  after=transform.repin(before,updates,spec['engine_additions']);installer.verify_bindings(after)
  key=installer.signature(before,manifest,spec);output=installer.signature(after,manifest,spec)
  assert key not in spec['signatures']
  spec['signatures'][key]={'label':label,'output_signature':output,'patches':{n:{'before_sha256':sha(before[n]) if n in before else None,'after_sha256':sha(raw)} for n,raw in updates.items()}}
  bindings.append({'label':label,'input_signature':key,'output_signature':output})
  kind='query_latency_20261007_r3' if label.startswith('GENOS_QUERY_LATENCY_20261007_R3/') and not label.endswith('/dependency-recovery-r1') else None
  if '/GENOS_QUERY_LATENCY_20261007_R4/' in label and '/applied-display-r5/' in label and label.endswith('/dependency-recovery-r1') and before[diagnostic]==working[diagnostic]:kind='query_latency_20261007_r4'
  if kind and kind not in [r['kind'] for r in fixtures]:
   path=O/'fixtures'/('predecessor-'+kind+'.zip');path.parent.mkdir(exist_ok=True)
   with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    z.writestr('CODE_MANIFEST.json',enc(manifest))
    for n,b in before.items():z.writestr(n,b)
   fixtures.append({'kind':kind,'label':label,'path':str(path.relative_to(O)),'sha256':sha(path.read_bytes())})
 assert len(fixtures)==2 and len(bindings)==660,(len(fixtures),len(bindings))
 assert all(set(variants[n].values())=={sha(source[n])} for n in source if n!=diagnostic and not n.endswith('/shortcut_cases.py')),variants
 for kind,files in [('payload',source),('preimage',baseline)]:
  for n,b in files.items():p=O/kind/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 for name,value in [('PATCH_SPEC.json.gz',spec),('INVENTORY_BINDINGS.json.gz',bindings)]: (O/name).write_bytes(gzip.compress(enc(value),mtime=0))
 (O/'FIXTURES.json').write_bytes(enc(fixtures))
 (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files':{n:sha(b) for n,b in source.items()},'working_source_files':{n:sha(b) for n,b in working.items()},'field_variants':variants,'known_predecessors':len(bindings),'nine_fix_files_identical_to_tested_working_code':True,'shortcut_guard_identical_to_working_code':True,'shortcut_other_bytes_preserved':True,'field_consumer_bridge':'Preserve field traceback policy while restoring existing MAIN62 diagnostics consumer; copy identical terminal clarification guard into field shortcut variants without changing routing/hint policies','prerequisite':['GENOS_SCHEMA_RECOVERY_20261014_R1','GENOS_DEPENDENCY_RECOVERY_20261014_R1'],'local_active_generation':62,'local_main_promoted':False,'genos_field_status':'NOT_VERIFIED','working_verification':str(A.relative_to(R))+'/regression-final-result.json'}))
 bundle=enc({'code':base64.b64encode((O/'apply_patch.py').read_bytes()).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py='import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
 py+="bundle=json.loads(raw);module=types.ModuleType('tool_availability_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
 header=(P/'GENOS_DEPENDENCY_RECOVERY_20261014_R1_RUN.txt').read_text().split('python3 - "$@"',1)[0].replace('dependency-recovery','tool-availability').replace('DEPENDENCY_RECOVERY','TOOL_AVAILABILITY')
 (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'TOOL_AVAILABILITY_PY\'\n'+py+'TOOL_AVAILABILITY_PY\n')
 subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
 print(json.dumps({'inventories':len(bindings),'files':len(source),'fixtures':fixtures,'run_bytes':(O/(N+'_RUN.txt')).stat().st_size}),flush=True)
if __name__=='__main__':main()
