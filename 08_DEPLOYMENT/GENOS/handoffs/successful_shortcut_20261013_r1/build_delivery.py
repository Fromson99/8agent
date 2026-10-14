"""Apply reviewed exact-context edits to sealed field variants, retaining all other bytes."""
import ast,base64,difflib,gzip,hashlib,importlib.util,json,subprocess,zlib
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
NAME='GENOS_SUCCESSFUL_SHORTCUT_20261013_R1'
PARENT=OUT.with_name('ad_request_logs_20261013_r2')
sha=lambda b:hashlib.sha256(b).hexdigest()
encoded=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def transform(raw,before,after,name):
    if raw==before:return after
    a,b=before.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True)
    result=raw.decode()
    for tag,i,j,k,l in reversed(difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes()):
        if tag=='equal':continue
        old,new=''.join(a[i:j]),''.join(b[k:l])
        if old:
            if result.count(old)!=1:raise ValueError('changed block not unique/found: '+name+' '+repr(old[:180]))
            result=result.replace(old,new,1)
        else:
            applied=False
            for count in (3,2,1):
                before=''.join(a[max(0,i-count):i]);after=''.join(a[i:i+count])
                if before and result.count(before)==1:
                    result=result.replace(before,before+new,1);applied=True;break
                if after and result.count(after)==1:
                    result=result.replace(after,new+after,1);applied=True;break
            if not applied and name.endswith('shortcut_repository.py') and 'check_knowledge(self,value)' in new:
                # Pre-core field variant has no optional curated/core block.
                # Its hash guard is the same authority boundary.
                anchor="        if digest(value)!=row['hash']: raise MemoryError('knowledge hash mismatch')\n"
                assert result.count(anchor)==1
                result=result.replace(anchor,anchor+new+"        if value.get('core_evidence_route'):\n            from .core_evidence_route import current\n            current(self,value,principal)\n",1)
                applied=True
            if not applied:raise ValueError('insertion anchor not unique/found: '+name+' '+repr(a[max(0,i-3):i+3]))
    if name.endswith('shortcut_repository.py') and '    def knowledge_scopes(' not in result:
        # Old private-only repositories predate the core module's scope helper.
        # Preserve private-only visibility instead of enabling common catalogue.
        anchor='    def _event('
        assert result.count(anchor)==1
        result=result.replace(anchor,"    def knowledge_scopes(self, principal, *, include_common=True):\n        return [self.scope(principal)]\n\n"+anchor,1)
    return result.encode()


def repin(payload,updates,additions):
    """Preserve existing key order and append new pins in installer order."""
    result={**payload,**updates}
    pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for entry in pipeline['engines'].values():
        path=entry['manifest'];engine=json.loads(payload[path])
        for target in set(engine['files']) & set(updates):
            engine['files'][target]=sha(result[target])
        for target in additions.get(path,[]):
            engine['files'][target]=sha(result[target])
        result[path]=encoded(engine);entry['sha256']=sha(result[path])
    result['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
    return result


def predecessors():
    old=load('ad_logs_parent_builder',PARENT.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    installer=load('ad_logs_parent_installer',PARENT/'apply_patch.py')
    spec=json.loads(gzip.decompress((PARENT/'PATCH_SPEC.json.gz').read_bytes()))
    for label,payload,budget in old.predecessors():
        base=dict(payload);manifest=json.loads(base.pop('CODE_MANIFEST.json'))
        state=spec['signatures'][installer.signature(base,manifest,spec)]
        updates={n:base64.b64decode(spec['blobs'][p['after_sha256']]) for n,p in state['patches'].items()}
        final=old.repin(base,updates,spec['engine_additions'])
        assert installer.signature(final,manifest,spec)==state['output_signature']
        manifest['files']=[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(final.items())]
        final['CODE_MANIFEST.json']=encoded(manifest)
        yield label+'/ad-logs-r2',final,budget


def build():
    assert not (OUT/(NAME+'.zip')).exists(),'Preserve sealed handoff'
    installer=load('ad_logs_installer',OUT/'apply_patch.py')
    source=json.loads((OUT/'WORKING_INTEGRATION.json').read_text())['files']
    assert all(sha((ROOT/n).read_bytes())==h for n,h in source.items()),'source changed; rebind verified inputs'
    spec={'revision':NAME,'signatures':{},'blobs':{},'engine_additions':{}}
    bindings=[];variants={};patch_cache={}
    for label,before,budget in predecessors():
        manifest=json.loads(before['CODE_MANIFEST.json']);updates={}
        for n in source:
            key=(n,sha(before[n]) if n in before else None)
            if key not in patch_cache:
                local=(OUT/'preimage'/n)
                if local.exists():
                    try:patched=transform(before[n],local.read_bytes(),(ROOT/n).read_bytes(),n)
                    except Exception:
                        (OUT/'FAILED_VARIANT.py').write_bytes(before[n]);(OUT/'FAILED_LABEL.txt').write_text(label);raise
                else:
                    assert n not in before,n
                    patched=(ROOT/n).read_bytes()
                ast.parse(patched,feature_version=(3,10))
                patch_cache[key]=patched
            updates[n]=patch_cache[key]
            variants.setdefault(n,{})[key[1] or 'NEW']=sha(updates[n])
        additions={e['manifest']:[n for n in updates if n not in before]
                   for e in json.loads(before['00_SYSTEM/PIPELINE.json'])['engines'].values()
                   if '02_BACKEND/semantic_runtime/legal_agent/gateway.py' in json.loads(before[e['manifest']])['files']}
        assert not spec['engine_additions'] or spec['engine_additions']==additions
        spec['engine_additions']=additions;spec['budget_policy']=budget
        after=repin(before,updates,additions);installer.verify_bindings(after)
        patches={}
        for n,raw in updates.items():
            digest=sha(raw);spec['blobs'][digest]=base64.b64encode(raw).decode()
            patches[n]={'before_sha256':sha(before[n]) if n in before else None,'after_sha256':digest}
        key=installer.signature(before,manifest,spec);output=installer.signature(after,manifest,spec)
        spec['signatures'][key]={'label':label,'patches':patches,'output_signature':output}
        bindings.append({'label':label,'input_signature':key,'output_signature':output})
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
    (OUT/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(encoded(bindings),mtime=0))
    (OUT/'SOURCE_BINDING.json').write_bytes(encoded({'source_files':source,'field_variants':variants,
        'known_predecessors':len(bindings),'prior_delivery':str(PARENT.relative_to(ROOT)),
        'field_status':'NOT_VERIFIED','model_calls':0,'local_active_release_changed':False}))
    for (n,_),raw in patch_cache.items():
        path=OUT/'reviewed'/n/(sha(raw)+'.py');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    bundle=encoded({'code':base64.b64encode((OUT/'apply_patch.py').read_bytes()).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    py=('import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'+
        "bundle=json.loads(raw);module=types.ModuleType('ad_request_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    old=(PARENT/'GENOS_AD_REQUEST_LOGS_20261013_R2_RUN.txt').read_text()
    header=old[:old.index('python3 - "$@"')].replace('ad-request-logs-r2','successful-shortcut-r1').replace('AD_REQUEST_LOGS','SUCCESSFUL_SHORTCUT')
    (OUT/(NAME+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'AD_REQUEST_LOGS_PY\'\n'+py+'AD_REQUEST_LOGS_PY\n')
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    print(json.dumps({'inventories':len(bindings),'variants':{n:len(v) for n,v in variants.items()},'run_bytes':(OUT/(NAME+'_RUN.txt')).stat().st_size}))


if __name__=='__main__':build()
