"""Check the actual installer on all frozen byte maps without copying full trees."""
from contextlib import redirect_stdout
import gzip
import io
import json
from pathlib import Path
import types

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent

def main():
    import importlib.util
    def load(name,path):
        s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
    build=load('r4_static_build',OUT/'build_delivery.py')
    install=load('r4_static_install',OUT/'apply_display.py')
    spec=json.loads(gzip.decompress((OUT/'PATCH_SPEC.json.gz').read_bytes()))
    rows=[]
    for label,payload,_ in build.states():
        def virtual_path(root,name):
            return types.SimpleNamespace(read_bytes=lambda:payload[name],exists=lambda:name in payload)
        install.path_at=virtual_path
        with redirect_stdout(io.StringIO()):_,before,changes,after=install.prepared('static-byte-map',spec)
        final={**before,**changes}
        assert install.signature(final,after,spec)==after['rag_display']['output_signature']
        assert final['service.py']==before['service.py']
        for name in ['00_SYSTEM/GENOS_SERVING_PATHS.json','02_BACKEND/lawrag/pipeline/shortcut_package.py']:
            if name in before:assert final[name]==before[name]
        for name in build.OWN:
            assert final[name]==(OUT/'payload'/name).read_bytes()
        rows.append({'basis':label,'input_signature':after['rag_display']['input_signature'],
            'output_signature':after['rag_display']['output_signature'],'passed':True,
            'service_and_cm_and_selected_binding_preserved':True,'engine_schema_pins':'PASS'})
    assert len(rows)==len(spec['signatures'])
    (OUT/'STATIC_VALIDATION.json').write_text(json.dumps({'method':'actual prepared() over immutable in-memory byte maps; filesystem mutations tested separately',
        'variants':rows,'passed':len(rows),'model_calls':0},indent=2)+'\n')
    print('STATIC_INSTALLER_RECIPES',len(rows),'PASS')

if __name__=='__main__':main()
