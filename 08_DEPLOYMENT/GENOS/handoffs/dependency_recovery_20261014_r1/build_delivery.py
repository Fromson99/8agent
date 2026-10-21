"""Bind tested fixes and their existing diagnostic consumer to exact field inventories."""
import ast, base64, gzip, hashlib, importlib.util, itertools, json, subprocess, zipfile, zlib
from copy import deepcopy
from pathlib import Path

O=Path(__file__).resolve().parent; R=O.parents[3]
N='GENOS_DEPENDENCY_RECOVERY_20261014_R1'
P=O.with_name('schema_recovery_20261014_r1')
A=R/'09_ARTIFACTS/AUDITS/20261014-dependency-recovery-fix'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def predecessors():
    parent=load('dependency_previous_builder',P/'build_delivery.py')
    installer=load('dependency_previous_installer',P/'apply_patch.py')
    transform=load('dependency_repin',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    spec=json.loads(gzip.decompress((P/'PATCH_SPEC.json.gz').read_bytes()))
    for label,before,manifest,budget in parent.predecessors():
        state=spec['signatures'][installer.signature(before,manifest,spec)]
        updates={n:base64.b64decode(spec['blobs'][row['after_sha256']]) for n,row in state['patches'].items()}
        after=transform.repin(before,updates,spec['engine_additions'])
        assert installer.signature(after,manifest,spec)==state['output_signature']
        manifest=deepcopy(manifest)
        installer.rebind(manifest,{n:(sha(before[n]),sha(raw)) for n,raw in after.items() if n in before and raw!=before[n]})
        manifest['files']=[{'path':n,'sha256':sha(raw),'bytes':len(raw)} for n,raw in sorted(after.items())]
        manifest['id']='GENOS_SCHEMA_RECOVERY_20261014_R1'
        yield label+'/schema-recovery-r1',after,manifest,budget

def main():
    assert not (O/(N+'.zip')).exists(),'Preserve sealed delivery'
    transform=load('dependency_transform',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    installer=load('dependency_installer',O/'apply_patch.py')
    receipt=json.loads((A/'regression-final-result.json').read_bytes())
    assert receipt['exit_code']==0 and receipt['product_unchanged'] and receipt['test_files_unchanged']
    source={n:(R/n).read_bytes() for n in receipt['product_sha256']}
    assert all(sha(raw)==receipt['product_sha256'][n] for n,raw in source.items())
    selected=R/'08_DEPLOYMENT/RELEASES/schema-recovery-20261014-r1/code'
    baseline={n:(selected/n).read_bytes() for n in source}
    working=dict(source)
    # Field packaging kept typed exception diagnostics but omitted SELECT's
    # rejected_decisions -> blockers wiring. Restore that existing MAIN62
    # consumer, while preserving its deliberate omission of raw tracebacks.
    diagnostic='02_BACKEND/semantic_runtime/legal_agent/investigation_diagnostics.py'
    raw=(R/diagnostic).read_bytes()
    assert raw==(selected/diagnostic).read_bytes()
    working[diagnostic]=raw
    trace=",\n        'traceback': ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}"
    assert raw.decode().count(trace)==1
    source[diagnostic]=raw
    diagnostic_without_trace=raw.decode().replace(trace,'}').encode()
    inventories=iter(predecessors());head=next(inventories)
    baseline[diagnostic]=head[1][diagnostic]
    assert b"for rejection in result.get('rejected_decisions', [])" not in baseline[diagnostic]
    spec={'revision':N,'signatures':{},'blobs':{},'engine_additions':{}}
    variants={};cache={};bindings=[];fixtures=[]
    for label,before,manifest,budget in itertools.chain([head],inventories):
        updates={};spec['budget_policy']=budget
        for name,target in source.items():
            key=name,sha(before[name])
            if key not in cache:
                if name==diagnostic:
                    if before[name]==working[diagnostic]:raw=before[name]
                    else:
                        assert before[name]==baseline[diagnostic],'Unreviewed diagnostic variant'
                        raw=diagnostic_without_trace
                else:raw=transform.transform(before[name],baseline[name],target,name)
                ast.parse(raw,feature_version=(3,10));cache[key]=raw
            updates[name]=cache[key]
            variants.setdefault(name,{})[key[1]]=sha(cache[key])
            spec['blobs'][sha(cache[key])]=base64.b64encode(cache[key]).decode()
        after=transform.repin(before,updates,{})
        installer.verify_bindings(after)
        key=installer.signature(before,manifest,spec);output=installer.signature(after,manifest,spec)
        assert key not in spec['signatures']
        spec['signatures'][key]={'label':label,'output_signature':output,
            'patches':{n:{'before_sha256':sha(before[n]),'after_sha256':sha(raw)} for n,raw in updates.items()}}
        bindings.append({'label':label,'input_signature':key,'output_signature':output})
        # Two distinct real field bases, with the second exercising its budget overlay.
        kind='query_latency_20261007_r3' if label.startswith('GENOS_QUERY_LATENCY_20261007_R3/') else None
        if ('/GENOS_QUERY_LATENCY_20261007_R4/' in label and '/applied-display-r5/' in label
                and before[diagnostic]==working[diagnostic]):kind='query_latency_20261007_r4'
        if kind and kind not in [r['kind'] for r in fixtures]:
            path=O/'fixtures'/('predecessor-'+kind+'.zip');path.parent.mkdir(exist_ok=True)
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
                z.writestr('CODE_MANIFEST.json',enc(manifest))
                for n,raw in before.items():z.writestr(n,raw)
            fixtures.append({'kind':kind,'label':label,'path':str(path.relative_to(O)),'sha256':sha(path.read_bytes())})
    assert len(fixtures)==2,fixtures
    # All deployed variants must exactly match these reviewed bytes.
    assert all(set(variants[n].values())=={sha(source[n])} for n in source if n!=diagnostic),variants
    assert set(variants[diagnostic].values())=={sha(source[diagnostic]),sha(diagnostic_without_trace)}
    for kind,files in [('payload',source),('preimage',baseline)]:
        for n,raw in files.items():
            p=O/kind/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    (O/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(spec),mtime=0))
    (O/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(enc(bindings),mtime=0))
    (O/'FIXTURES.json').write_bytes(enc(fixtures))
    (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files':{n:sha(b) for n,b in source.items()},
        'working_source_files':{n:sha(b) for n,b in working.items()},
        'field_variants':variants,'known_predecessors':len(bindings),'all_four_files_identical_to_tested_working_code':True,
        'field_consumer_bridge':{'path':diagnostic,'reason':'Restore existing MAIN62 rejection/stop_reason forwarding where missing; preserve each field inventory raw traceback policy'},
        'prerequisite':'GENOS_SCHEMA_RECOVERY_20261014_R1','local_active_generation':62,'local_main_promoted':False,
        'genos_field_status':'NOT_VERIFIED','working_verification':str(A.relative_to(R))+'/regression-final-result.json'}))
    bundle=enc({'code':base64.b64encode((O/'apply_patch.py').read_bytes()).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    py='import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
    py+="bundle=json.loads(raw);module=types.ModuleType('dependency_recovery_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
    header=(P/'GENOS_SCHEMA_RECOVERY_20261014_R1_RUN.txt').read_text().split('python3 - "$@"',1)[0]
    header=header.replace('schema-recovery-r1','dependency-recovery-r1').replace('SCHEMA_RECOVERY','DEPENDENCY_RECOVERY')
    header=header.replace('task_logs="$GENOS_PATCH_DEV/TRANSFER/dependency-recovery-r1/bootstrap-logs"','task_logs="$PWD/dependency-recovery-r1-logs"')
    header=header.replace('then set -- apply','then set -- check')
    (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'DEPENDENCY_RECOVERY_PY\'\n'+py+'DEPENDENCY_RECOVERY_PY\n')
    subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
    print(json.dumps({'inventories':len(bindings),'files':len(source),'fixtures':fixtures,'run_bytes':(O/(N+'_RUN.txt')).stat().st_size}),flush=True)

if __name__=='__main__':main()
