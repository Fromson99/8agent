"""Bind the transport fix to every sealed narrative R2 predecessor inventory."""
import ast
import base64
import gzip
import hashlib
import importlib.util
import json
import subprocess
import zlib
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
NAME='GENOS_MODEL_STREAM_FIX_20261013_R1'
PARENT=OUT.with_name('rag_narrative_stream_20261013_r2')
TRANSPORT='02_BACKEND/semantic_runtime/legal_agent/transport.py'
HELPER='02_BACKEND/semantic_runtime/legal_agent/model_stream.py'
sha=lambda b:hashlib.sha256(b).hexdigest()
encoded=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def repin(payload, patches, additions):
    result={**payload,**patches}
    pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for entry in pipeline['engines'].values():
        path=entry['manifest'];engine=json.loads(payload[path])
        for target in (set(engine['files'])&set(patches))|set(additions.get(path,[])):
            engine['files'][target]=sha(result[target])
        result[path]=encoded(engine);entry['sha256']=sha(result[path])
    result['00_SYSTEM/PIPELINE.json']=encoded(pipeline)
    return result


def predecessors():
    old=load('stream_fix_parent_builder',PARENT/'build_delivery.py')
    installer=load('stream_fix_parent_installer',PARENT/'apply_patch.py')
    states,budget=old.source_material()
    spec=json.loads(gzip.decompress((PARENT/'PATCH_SPEC.json.gz').read_bytes()))
    for row in states:
        base=dict(row['payload']);manifest=json.loads(base.pop('CODE_MANIFEST.json'))
        state=spec['signatures'][installer.signature(base,manifest,spec)]
        patches={n:base64.b64decode(spec['blobs'][p['after_sha256']]) for n,p in state['patches'].items()}
        final=repin(base,patches,spec['engine_additions'])
        assert installer.signature(final,manifest,spec)==state['output_signature']
        installer.verify_bindings(final)
        manifest['files']=[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(final.items())]
        final['CODE_MANIFEST.json']=encoded(manifest)
        yield row['label']+'/narrative-r2',final,budget


def build():
    assert not (OUT/(NAME+'.zip')).exists(),'Preserve sealed handoff'
    app=load('stream_fix_installer',OUT/'apply_patch.py')
    rewrite=load('stream_fix_rewrite',OUT/'rewrite_transport.py').rewrite
    helper=(ROOT/HELPER).read_bytes()
    spec={'revision':NAME,'signatures':{},'blobs':{},'engine_additions':{}}
    bindings=[];transports={}
    for label,before,budget in predecessors():
        manifest=json.loads(before['CODE_MANIFEST.json']);spec['budget_policy']=budget
        patched=rewrite(before[TRANSPORT]);ast.parse(patched,feature_version=(3,10))
        updates={TRANSPORT:patched,HELPER:helper}
        additions={e['manifest']:[HELPER] for e in json.loads(before['00_SYSTEM/PIPELINE.json'])['engines'].values()
                   if TRANSPORT in json.loads(before[e['manifest']])['files']}
        assert not spec['engine_additions'] or spec['engine_additions']==additions
        spec['engine_additions']=additions
        after=repin(before,updates,additions);app.verify_bindings(after)
        patches={}
        for n,raw in updates.items():
            digest=sha(raw);spec['blobs'][digest]=base64.b64encode(raw).decode()
            patches[n]={'before_sha256':sha(before[n]) if n in before else None,'after_sha256':digest}
        key=app.signature(before,manifest,spec);output=app.signature(after,manifest,spec)
        spec['signatures'][key]={'label':label,'patches':patches,'output_signature':output}
        bindings.append({'label':label,'input_signature':key,'output_signature':output})
        transports[sha(before[TRANSPORT])]=sha(patched)
    (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
    (OUT/'INVENTORY_BINDINGS.json.gz').write_bytes(gzip.compress(encoded(bindings),mtime=0))
    (OUT/'SOURCE_BINDING.json').write_bytes(encoded({'source_files':{TRANSPORT:sha((ROOT/TRANSPORT).read_bytes()),HELPER:sha(helper)},
        'field_transport_variants':transports,'known_predecessors':len(bindings),'prior_delivery':str(PARENT.relative_to(ROOT)),
        'field_status':'NOT_VERIFIED','model_calls':0,'local_active_release_changed':False}))
    code=(OUT/'apply_patch.py').read_bytes()
    bundle=encoded({'code':base64.b64encode(code).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    py=('import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'+
        "bundle=json.loads(raw);module=types.ModuleType('model_stream_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    old=(PARENT/'GENOS_RAG_NARRATIVE_STREAM_20261013_R2_RUN.txt').read_text()
    header=old[:old.index('python3 - "$@"')].replace('rag-narrative-stream-r2','model-stream-fix-r1').replace('NARRATIVE_RAG','MODEL_STREAM_FIX')
    run=header+'python3 - "$@" <<\'MODEL_STREAM_FIX_PY\'\n'+py+'MODEL_STREAM_FIX_PY\n'
    (OUT/(NAME+'_RUN.txt')).write_text(run)
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    (OUT/'HANDOFF.json').write_bytes(encoded({'version':NAME,'field_code_root':'~/DEV',
        'field_git_commit':None,'field_generation':None,'field_generation_manifest_sha256':None,'field_code_serving_revision':None,
        'genos_applied':False,'genos_deployed':False,'workflow_test':'NOT_RUN','email_status':'NOT_SENT',
        'rebuild_required':False,'workflow_editor_change_required':False,'run_txt_sha256':sha(run.encode()),
        'known_narrative_r2_inventories':len(bindings),'implementation_files':2,'local_active_release_changed':False}))
    print(json.dumps({'inventories':len(bindings),'field_transport_variants':len(transports),'run_bytes':len(run.encode())}))


if __name__=='__main__':build()
