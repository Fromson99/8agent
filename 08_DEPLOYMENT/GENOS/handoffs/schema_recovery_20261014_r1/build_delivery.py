"""Bind qualified recovery bytes to preserved, exact TLS field inventories."""
import ast,base64,gzip,hashlib,importlib.util,itertools,json,subprocess,tempfile,zipfile,zlib
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];N='GENOS_SCHEMA_RECOVERY_20261014_R1'
A=R/'04_EXPERIMENTS/ADR/ADR-0777-schema-recovery-main/artifacts'
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def predecessors():
    folder=O.with_name('urllib_tls_20261014_r1')
    old=load('schema_prior',folder/'build_delivery.py');ins=load('schema_tls_installer',folder/'apply_patch.py')
    spec=json.loads(gzip.decompress((folder/'PATCH_SPEC.json.gz').read_bytes()))
    transform=load('schema_repin',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    for label,before,manifest,budget in old.predecessors():
        if not label.endswith('/success/guidance/metrics'):continue
        state=spec['signatures'][ins.signature(before,manifest,spec)]
        updates={n:base64.b64decode(spec['blobs'][row['after_sha256']]) for n,row in state['patches'].items()}
        final=transform.repin(before,updates,spec['engine_additions'])
        assert ins.signature(final,manifest,spec)==state['output_signature']
        yield label+'/tls',final,manifest,budget
def main():
    assert not (O/(N+'.zip')).exists(),'Preserve sealed handoff'
    old=load('schema_transform',O.with_name('ad_request_logs_20261013_r1')/'build_delivery.py')
    ins=load('schema_installer',O/'apply_patch.py')
    changes=json.loads((A/'working-integration-receipt.json').read_bytes())['changes']
    source={r['path']:(R/r['path']).read_bytes() for r in changes if r['path'].startswith('02_BACKEND/semantic_runtime/')}
    assert all(sha(source[r['path']])==r['after'] for r in changes if r['path'] in source)
    with zipfile.ZipFile(A/'working-preintegration.zip') as z:baseline={n:z.read(n) for n in source if n in z.namelist()}
    # Query inventories omit the build-only provider and reference resolver.
    inventories=iter(predecessors());head=next(inventories);first=head[1]
    excluded=[n for n in source if n not in first and n in baseline]
    source={n:b for n,b in source.items() if n not in excluded}
    for group,files in [('payload',source),('preimage',{n:b for n,b in baseline.items() if n in source})]:
        for n,b in files.items():
            p=O/group/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    spec={'revision':N,'signatures':{},'blobs':{},'engine_additions':{}}
    cache={};variants={};bindings=[]
    for label,before,manifest,budget in itertools.chain([head],inventories):
        updates={}
        for n,target in source.items():
            key=n,sha(before[n]) if n in before else None
            if key not in cache:
                if n in baseline:
                    assert n in before,n
                    if n.endswith('/request_entry.py') and b'wiki_recall' not in before[n]:
                        def outside_run(raw):
                            tree=ast.parse(raw);tree.body=[node for node in tree.body if not isinstance(node,ast.FunctionDef) or node.name!='run']
                            return ast.dump(tree,include_attributes=False)
                        assert outside_run(before[n])==outside_run(baseline[n]),'Unreviewed field entry difference'
                        # The older field entry has no wiki-recall feature. Preserve that boundary.
                        raw=target.decode()
                        raw=raw.replace('    from . import wiki_recall\n', '')
                        raw=raw.replace("    memory=wiki_recall.offer(repo.executor,repo._entry_principal,context['utterance'],scope,work.event)", '    memory=None')
                        raw=raw.replace('    data,request_schema=wiki_recall.augment(data,request_schema,memory)\n','')
                        raw=raw.replace("    recall_prompt=wiki_recall.PROMPT if memory else ''", "    recall_prompt=''")
                        raw=raw.replace("    if memory:wiki_recall.choose(repo.executor,prepared['history_ids'] if intent is not None else [],work.event)\n",'')
                        assert 'wiki_recall' not in raw
                        raw=raw.encode();ast.parse(raw);cache[key]=raw
                    # Some sealed field inventories intentionally omit duplicate raw tracebacks.
                    # Keep that presentation choice; only add the typed contract diagnostic.
                    if n.endswith('/investigation_diagnostics.py'):
                        anchor="    if getattr(exc, 'diagnostics', None) is not None:"
                        addition="    from .output_contract import diagnostics\n    out['output_contract'] = diagnostics(exc)\n"
                        assert before[n].decode().count(anchor)==1
                        assert 'output_contract' not in before[n].decode()
                        raw=before[n].decode().replace(anchor,addition+anchor).encode()
                        ast.parse(raw);cache[key]=raw
                    try:
                        if key in cache:pass
                        else:raw=old.transform(before[n],baseline[n],target,n)
                    except ValueError:
                        with tempfile.TemporaryDirectory() as td:
                            paths=[Path(td)/x for x in ('field','base','candidate')]
                            for path,content in zip(paths,(before[n],baseline[n],target)):path.write_bytes(content)
                            merge=subprocess.run(['git','merge-file','-p',*map(str,paths)],capture_output=True)
                            if merge.returncode:
                                failed=O/'failures'/('merge-'+n.rsplit('/',1)[-1]);failed.write_bytes(merge.stdout)
                                raise ValueError('Field merge conflict; preserved for review: '+n)
                            raw=merge.stdout
                            review=O/'merges'/n/(sha(before[n])+'.json');review.parent.mkdir(parents=True,exist_ok=True)
                            review.write_bytes(enc({'field':sha(before[n]),'baseline':sha(baseline[n]),'candidate':sha(target),
                                'merged':sha(raw),'method':'conflict-free three-way merge; installed tests required'}))
                else:
                    assert n not in before,n
                    raw=target
                ast.parse(raw,feature_version=(3,10));cache[key]=raw
            updates[n]=cache[key];spec['blobs'][sha(cache[key])]=base64.b64encode(cache[key]).decode()
            variants.setdefault(n,{})[key[1] or 'NEW']=sha(cache[key])
        new=[n for n in updates if n not in before]
        additions={e['manifest']:new for e in json.loads(before['00_SYSTEM/PIPELINE.json'])['engines'].values()
            if '02_BACKEND/semantic_runtime/legal_agent/gateway.py' in json.loads(before[e['manifest']])['files']}
        assert not spec['engine_additions'] or spec['engine_additions']==additions
        spec['engine_additions']=additions;spec['budget_policy']=budget
        after=old.repin(before,updates,additions);ins.verify_bindings(after)
        key,out=ins.signature(before,manifest,spec),ins.signature(after,manifest,spec)
        spec['signatures'][key]={'label':label,'patches':{n:{'before_sha256':sha(before[n]) if n in before else None,
            'after_sha256':sha(raw)} for n,raw in updates.items()},'output_signature':out}
        bindings.append({'label':label,'input_signature':key,'output_signature':out})
    for (n,_),raw in cache.items():
        p=O/'reviewed'/n/(sha(raw)+'.py');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    (O/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(enc(spec),mtime=0))
    (O/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(enc(bindings),mtime=0))
    (O/'SOURCE_BINDING.json').write_bytes(enc({'source_files':{n:sha(b) for n,b in source.items()},'field_variants':variants,
        'known_predecessors':len(spec['signatures']),'engine_helper_pins':len(additions),'build_only_excluded':excluded,
        'qualified_source':'ADR0777/recovery','genos_field_status':'NOT_VERIFIED','local_active_generation':62}))
    bundle=enc({'code':base64.b64encode((O/'apply_patch.py').read_bytes()).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    py='import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'
    py+="bundle=json.loads(raw);module=types.ModuleType('schema_recovery_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n"
    prior=O.with_name('urllib_tls_20261014_r1')/'GENOS_URLLIB_TLS_20261014_R1_RUN.txt'
    header=prior.read_text().split('python3 - "$@"',1)[0].replace('urllib-tls-r1','schema-recovery-r1').replace('URLLIB_TLS','SCHEMA_RECOVERY')
    (O/(N+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'SCHEMA_RECOVERY_PY\'\n'+py+'SCHEMA_RECOVERY_PY\n')
    subprocess.run(['bash','-n',str(O/(N+'_RUN.txt'))],check=True)
    print(json.dumps({'inventories':len(spec['signatures']),'files':len(source),'variants':{n:len(v) for n,v in variants.items()},'excluded':excluded}))
if __name__=='__main__':main()
