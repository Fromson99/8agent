"""Compose P1-P3 onto sealed schema/dependency/availability inventories."""
import ast,base64,gzip,hashlib,importlib.util,json,subprocess,zipfile,zlib
from copy import deepcopy
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];P=O.with_name('tool_availability_20261014_r1');N='GENOS_TOOL_RECOVERY_20261014_R1'
sha=lambda b:hashlib.sha256(b).hexdigest();enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 assert not (O/(N+'.zip')).exists(),'Preserve sealed delivery'
 parent=load('recovery_parent',P/'build_delivery.py');prior=load('recovery_prior_installer',P/'apply_patch.py');installer=load('recovery_installer',O/'apply_patch.py');t=load('recovery_transform',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
 prev=json.loads(gzip.decompress((P/'PATCH_SPEC.json.gz').read_bytes()));oldsrc=json.loads((P/'SOURCE_BINDING.json').read_text())['source_files']
 delta=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0779-tool-recovery-main/artifacts/design/working-delta.json').read_text())['changes']
 names=sorted({r['path'] for r in delta if r['path'].startswith('02_BACKEND/semantic_runtime/')}|set(oldsrc))
 names=[n for n in names if not n.endswith('/wiki_recall.py')]
 source={n:(R/n).read_bytes() for n in names}
 base=R/'08_DEPLOYMENT/RELEASES/schema-recovery-20261014-r1/code'
 baseline={n:(P/'payload'/n).read_bytes() if n in oldsrc else (base/n).read_bytes() for n in names if n in oldsrc or (base/n).exists()}
 spec={'revision':N,'signatures':{},'blobs':{},'engine_additions':{}};variants={};cache={};bindings=[];fixtures=[]
 for label,pre,mf,budget in parent.predecessors():
  state=prev['signatures'][prior.signature(pre,mf,prev)]
  oldupdates={n:base64.b64decode(prev['blobs'][r['after_sha256']]) for n,r in state['patches'].items()}
  mid=t.repin(pre,oldupdates,prev['engine_additions']);assert prior.signature(mid,mf,prev)==state['output_signature']
  middle_manifest=deepcopy(mf);prior.rebind(middle_manifest,{n:(sha(pre[n]),sha(raw)) for n,raw in mid.items() if n in pre and raw!=pre[n]})
  middle_manifest['files']=[{'path':n,'sha256':sha(raw),'bytes':len(raw)} for n,raw in sorted(mid.items())];middle_manifest['id']='GENOS_TOOL_AVAILABILITY_20261014_R1'
  updates={}
  for n,target in source.items():
   key=(n,sha(mid[n]) if n in mid else 'ABSENT')
   if key not in cache:
    if n not in mid:assert n not in baseline;raw=target
    elif mid[n]==target:raw=target
    elif n.endswith('/investigation_diagnostics.py'):
     anchor=b"    out['output_contract'] = diagnostics(exc)\n"
     tail=b"    if getattr(exc, 'diagnostics', None) is not None:\n"
     addition=target.split(anchor,1)[1].split(tail,1)[0]
     assert baseline[n].split(anchor,1)[1].startswith(tail) and mid[n].count(anchor)==1
     raw=mid[n].replace(anchor,anchor+addition,1)
     assert raw.replace(anchor+addition,anchor,1)==mid[n]
    elif n.endswith('/readable_log.py'):
     anchor=b"    if isinstance(value.get('investigation'),dict):rows.extend(diagnostic_rows(value['investigation']))\n"
     tail=b"    if value.get('traceback'):"
     addition=target.split(anchor,1)[1].split(tail,1)[0]
     assert baseline[n].split(anchor,1)[1].startswith(tail) and mid[n].count(anchor)==1
     raw=mid[n].replace(anchor,anchor+addition,1)
     assert raw.replace(anchor+addition,anchor,1)==mid[n]
    else:raw=t.transform(mid[n],baseline[n],target,n)
    ast.parse(raw,feature_version=(3,10));cache[key]=raw
   updates[n]=cache[key];spec['blobs'][sha(cache[key])]=base64.b64encode(cache[key]).decode()
  new=['02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ('tool_availability','tool_outcome','tool_policy','tool_execution_receipt')]
  for entry in json.loads(pre['00_SYSTEM/PIPELINE.json'])['engines'].values():
   if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' in json.loads(pre[entry['manifest']])['files']:spec['engine_additions'][entry['manifest']]=new
  spec['budget_policy']=budget
  for tag,before,manifest in [(label,pre,mf),(label+'/tool-availability-r1',mid,middle_manifest)]:
   key=installer.signature(before,manifest,spec)
   if key in spec['signatures']:continue
   after=t.repin(before,updates,spec['engine_additions']);installer.verify_bindings(after);output=installer.signature(after,manifest,spec)
   spec['signatures'][key]={'label':tag,'output_signature':output,'patches':{n:{'before_sha256':sha(before[n]) if n in before else None,'after_sha256':sha(raw)} for n,raw in updates.items()}}
   bindings.append({'label':tag,'input_signature':key,'output_signature':output})
   for n,raw in updates.items():variants.setdefault(n,{})[sha(before[n]) if n in before else 'ABSENT']=sha(raw)
   kind='query_latency_20261007_r3' if tag.startswith('GENOS_QUERY_LATENCY_20261007_R3/') and not tag.endswith('/tool-availability-r1') else None
   if '/GENOS_QUERY_LATENCY_20261007_R4/' in tag and '/applied-display-r5/' in tag and tag.endswith('/tool-availability-r1'):kind='query_latency_20261007_r4'
   if kind and kind not in [r['kind'] for r in fixtures]:
    path=O/'fixtures'/('predecessor-'+kind+'.zip');path.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
     z.writestr('CODE_MANIFEST.json',enc(manifest))
     for n,raw in before.items():z.writestr(n,raw)
    fixtures.append({'kind':kind,'label':tag,'path':str(path.relative_to(O)),'sha256':sha(path.read_bytes())})
 assert len(fixtures)==2
 for folder,files in [('payload',source),('preimage',baseline)]:
  for n,raw in files.items():p=O/folder/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 for name,value in [('PATCH_SPEC.json.gz',spec),('INVENTORY_BINDINGS.json.gz',bindings)]: (O/name).write_bytes(gzip.compress(enc(value),mtime=0))
 (O/'FIXTURES.json').write_bytes(enc(fixtures))
 (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files':{n:sha(b) for n,b in source.items()},'working_source_files':{n:sha(b) for n,b in source.items()},'field_variants':variants,'known_predecessors':len(bindings),'prerequisite':['GENOS_SCHEMA_RECOVERY_20261014_R1','GENOS_DEPENDENCY_RECOVERY_20261014_R1','GENOS_TOOL_AVAILABILITY_20261014_R1'],'cumulative_prior_fixes':True,'field_policy_variants_preserved':True,'unshipped_working_change':{'02_BACKEND/semantic_runtime/legal_agent/wiki_recall.py':'Existing field inventory omits this module and disables wiki recall; preserve that policy, do not activate it'},'genos_field_status':'NOT_VERIFIED'}))
 bundle=enc({'code':base64.b64encode((O/'apply_patch.py').read_bytes()).decode(),'spec':spec});packed=base64.b64encode(zlib.compress(bundle,9)).decode()
 py='import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
 py+="bundle=json.loads(raw);module=types.ModuleType('tool_recovery_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
 header=(P/'GENOS_TOOL_AVAILABILITY_20261014_R1_RUN.txt').read_text().split('python3 - "$@"',1)[0].replace('tool-availability','tool-recovery').replace('TOOL_AVAILABILITY','TOOL_RECOVERY')
 (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'TOOL_RECOVERY_PY\'\n'+py+'TOOL_RECOVERY_PY\n')
 subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
 print(json.dumps({'inventories':len(bindings),'files':len(source),'variant_counts':{n:len(set(v.values())) for n,v in variants.items()},'run_bytes':(O/(N+'_RUN.txt')).stat().st_size}),flush=True)
if __name__=='__main__':main()
