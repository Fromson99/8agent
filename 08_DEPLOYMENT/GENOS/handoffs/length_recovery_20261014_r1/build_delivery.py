"""Cumulative sealed tool-recovery inventories plus bounded length correction."""
import ast,base64,gzip,hashlib,importlib.util,json,subprocess,zipfile,zlib
from copy import deepcopy
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];P=O.with_name('tool_recovery_20261014_r1');V=O.with_name('tool_availability_20261014_r1');N='GENOS_LENGTH_RECOVERY_20261014_R1'
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 assert not (O/(N+'.zip')).exists()
 parent=load('length_parent',V/'build_delivery.py');prior=load('length_prior',P/'apply_patch.py');availability=load('length_availability',V/'apply_patch.py');installer=load('length_installer',O/'apply_patch.py');t=load('length_transform',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
 old=json.loads(gzip.decompress((P/'PATCH_SPEC.json.gz').read_bytes()));av=json.loads(gzip.decompress((V/'PATCH_SPEC.json.gz').read_bytes()));oldsrc=json.loads((P/'SOURCE_BINDING.json').read_bytes())['source_files']
 newnames=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('bounded_source_session','law_candidates')]
 newnames+=['02_BACKEND/PIPELINE/engine_host.py','00_SYSTEM/SCHEMAS/pipeline-v1.schema.json','00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json','00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']
 source={n:(P/'payload'/n).read_bytes() for n in oldsrc};source.update({n:(R/n).read_bytes() for n in newnames})
 # Field inventories intentionally predate optional wiki catalogue metadata.
 # Keep known fields typed/closed when present; do not activate missing features.
 schema_name='00_SYSTEM/SCHEMAS/pipeline-v1.schema.json'
 field_schema=json.loads(source[schema_name]);shortcut=field_schema['properties']['shortcut_v4']
 shortcut['required']=[k for k in shortcut['required'] if k not in ('core_route_contract','common_catalogue','bounded_recall')]
 features=shortcut['properties']['features'];features['required']=[k for k in features['required'] if k not in ('core_evidence_route','bounded_recall')]
 source[schema_name]=enc(field_schema)
 base=R/'08_DEPLOYMENT/RELEASES/tool-recovery-20261014-r1/code'
 baseline={n:(base/n).read_bytes() for n in newnames if (base/n).exists()}
 spec={'revision':N,'signatures':{},'blobs':{},'engine_additions':{}};variants={};bindings=[];fixtures=[];seen=set();cache={}
 def manifest_for(before,after,mf):
  m=deepcopy(mf);prior.rebind(m,{n:(sha(before[n]),sha(raw)) for n,raw in after.items() if n in before and raw!=before[n]})
  m['files']=[{'path':n,'sha256':sha(raw),'bytes':len(raw)} for n,raw in sorted(after.items())];m['id']='GENOS_TOOL_RECOVERY_20261014_R1';return m
 for label,pre,mf,budget in parent.predecessors():
  avstate=av['signatures'][availability.signature(pre,mf,av)]
  avupdates={n:base64.b64decode(av['blobs'][r['after_sha256']]) for n,r in avstate['patches'].items()}
  avmid=t.repin(pre,avupdates,av['engine_additions']);avmf=manifest_for(pre,avmid,mf)
  for tag,before,manifest in [(label,pre,mf),(label+'/tool-availability-r1',avmid,avmf)]:
   key=prior.signature(before,manifest,old)
   if key in seen:continue
   seen.add(key);state=old['signatures'][key]
   if len(seen)%100==0:print('verified predecessor',len(seen),flush=True)
   oldupdates={n:base64.b64decode(old['blobs'][r['after_sha256']]) for n,r in state['patches'].items()}
   middle=t.repin(before,oldupdates,old['engine_additions']);assert prior.signature(middle,manifest,old)==state['output_signature']
   midmf=manifest_for(before,middle,manifest)
   updates=dict(oldupdates)
   for n in newnames:
    key2=(n,sha(middle[n]) if n in middle else None)
    if key2 not in cache:
     if n.endswith('profile-unified-v6.json'):
      value=json.loads(middle[n]);value['candidate_navigation']['length_recovery_max_tokens']=12800;raw=enc(value)
     elif '/SCHEMAS/' in n:raw=source[n]
     else:raw=t.transform(middle[n],baseline[n],source[n],n)
     if n.endswith('.py'):ast.parse(raw,feature_version=(3,10))
     cache[key2]=raw
    updates[n]=cache[key2]
   spec['budget_policy']=budget
   for entry in json.loads(before['00_SYSTEM/PIPELINE.json'])['engines'].values():
    path=entry['manifest'];pins=json.loads(before[path])['files'];added=list(old['engine_additions'].get(path,[]))
    if '02_BACKEND/PIPELINE/engine_host.py' in pins:added+=['00_SYSTEM/SCHEMAS/pipeline-v1.schema.json','00_SYSTEM/SCHEMAS/pipeline-engine-v1.schema.json']
    spec['engine_additions'][path]=sorted(set(added))
   for raw in updates.values():spec['blobs'][sha(raw)]=base64.b64encode(raw).decode()
   for name,start,man in [(tag,before,manifest),(tag+'/tool-recovery-r1',middle,midmf)]:
    k=installer.signature(start,man,spec)
    if k in spec['signatures']:continue
    after=t.repin(start,updates,spec['engine_additions']);installer.verify_bindings(after)
    spec['signatures'][k]={'label':name,'output_signature':installer.signature(after,man,spec),'patches':{n:{'before_sha256':sha(start[n]) if n in start else None,'after_sha256':sha(raw)} for n,raw in updates.items()}}
    bindings.append({'label':name,'input_signature':k,'output_signature':spec['signatures'][k]['output_signature']})
    for n,raw in updates.items():variants.setdefault(n,{})[sha(start[n]) if n in start else 'ABSENT']=sha(raw)
    kind='query_latency_20261007_r3' if name.startswith('GENOS_QUERY_LATENCY_20261007_R3/') and not name.endswith(('/tool-availability-r1','/tool-recovery-r1')) else None
    if '/GENOS_QUERY_LATENCY_20261007_R4/' in name and '/applied-display-r5/' in name and name.endswith('/tool-recovery-r1'):kind='query_latency_20261007_r4'
    if kind and kind not in [r['kind'] for r in fixtures]:
     path=O/'fixtures'/('predecessor-'+kind+'.zip');path.parent.mkdir(exist_ok=True)
     with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
      z.writestr('CODE_MANIFEST.json',enc(man))
      for n,raw in start.items():z.writestr(n,raw)
     fixtures.append({'kind':kind,'label':name,'path':str(path.relative_to(O)),'sha256':sha(path.read_bytes())})
 assert len(fixtures)==2
 for folder,files in [('payload',source),('preimage',baseline)]:
  for n,raw in files.items():p=O/folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 for name,value in [('PATCH_SPEC.json.gz',spec),('INVENTORY_BINDINGS.json.gz',bindings)]: (O/name).write_bytes(gzip.compress(enc(value),mtime=0))
 (O/'FIXTURES.json').write_bytes(enc(fixtures))
 (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files':{n:sha(b) for n,b in source.items()},'working_source_files':{n:sha((R/n).read_bytes()) for n in source},'field_variants':variants,'known_predecessors':len(bindings),'prerequisite':['GENOS_SCHEMA_RECOVERY_20261014_R1 or supported later cumulative inventory'],'cumulative_prior_fixes':True,'field_policy_variants_preserved':True,'genos_field_status':'NOT_VERIFIED'}))
 bundle=enc({'code':base64.b64encode((O/'apply_patch.py').read_bytes()).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py='import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
 py+="bundle=json.loads(raw);module=types.ModuleType('length_recovery_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
 header=(P/'GENOS_TOOL_RECOVERY_20261014_R1_RUN.txt').read_text().split('python3 - "$@"',1)[0].replace('tool-recovery','length-recovery').replace('TOOL_RECOVERY','LENGTH_RECOVERY')
 (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'LENGTH_RECOVERY_PY\'\n'+py+'LENGTH_RECOVERY_PY\n')
 subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
 print(json.dumps({'inventories':len(bindings),'source_files':len(source),'run_bytes':(O/(N+'_RUN.txt')).stat().st_size}))
if __name__=='__main__':main()
