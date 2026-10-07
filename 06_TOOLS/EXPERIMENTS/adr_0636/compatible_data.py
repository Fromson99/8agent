"""Offline derived packaging: same approved sources, newly built current-code cache."""
import json
import subprocess
import sys
import time
from common import ROOT,ADR,DESIGN,read,put,sha

def main():
    assert not (DESIGN/'freeze.json').exists()
    b=read(DESIGN/'source-binding.json');source=ROOT/b['generation']
    target=ADR/'artifacts/research-generation'
    assert not target.exists()
    start=time.monotonic()
    subprocess.run(['cp','--reflink=auto','-a',str(source),str(target)],check=True)
    cp=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0636/v6-baseline/candidate.json'
    code=cp.parent/'snapshot'
    sys.path.insert(0,str(code/'02_BACKEND'))
    from semantic_runtime.full_glossary import Glossary
    assert sha(code/'02_BACKEND/semantic_runtime/full_glossary.py')==sha(ROOT/'02_BACKEND/semantic_runtime/full_glossary.py')
    manifest=read(target/'manifest.json');binding=manifest['glossary'];old=dict(binding)
    glossary=Glossary(target/binding['bundle'],target/binding['dictionary'],target/binding['cache'],manifest_sha256=binding['manifest_sha256'],allow_cache_build=True)
    compiler=glossary.binding['compiler_sha256'];glossary.close()
    matches=[p for p in (target/binding['cache']).glob('*.json') if read(p)['binding']['compiler_sha256']==compiler]
    assert len(matches)==1
    receipt=matches[0];binding['cache_receipt']=receipt.name;binding['cache_receipt_sha256']=sha(receipt)
    put(target/'manifest.json',manifest)
    # All source/search bytes remain the exact approved generation.
    invariant_files=['store.sqlite','navigation/manifest.json','fulltext/manifest.json']
    invariant_files += [str(p.relative_to(source)) for folder in ('navigation','fulltext') for p in (source/folder).rglob('*.sqlite')]
    assert all(sha(source/p)==sha(target/p) for p in invariant_files)
    put(DESIGN/'cache-rebuild-receipt.json',{'status':'COMPLETE','source_generation':str(source.relative_to(ROOT)),
        'derived_generation':str(target.relative_to(ROOT)),'old_glossary_binding':old,'new_glossary_binding':binding,
        'compiler_sha256':compiler,'cache_sqlite_sha256':read(receipt)['sha256'],'invariant_files':{p:sha(source/p) for p in invariant_files},
        'source_generation_manifest_unchanged_sha256':sha(source/'manifest.json'),'seconds':time.monotonic()-start,'model_calls':0,
        'source_identity_unchanged':True,'original_files_modified':False,'main_unchanged':True})
    b.update(original_source_generation=b['generation'],original_source_manifest_sha256=b['source_manifest_sha256'],
        generation=str(target.relative_to(ROOT)),source_manifest_sha256=sha(target/'manifest.json'),
        basis='Same authorized public source identity/store/docs; new isolated offline cache built by unchanged current v6 compiler, explicit lineage. User requested v6 experiment.')
    put(DESIGN/'source-binding.json',b)
    m=read(ADR/'실험/manifest.json')
    m['design']['data_compatibility']='ADR0635 original-data failure preserved. New research copy rebuilds glossary cache with identical current v6 compiler, rebinds receipt only; source identity/store/navigation/fulltext and export=false preserved. No data CURRENT activation.'
    m['design']['arms'][0]['changes']+='; both arms explicitly bind derived compatible-cache package'
    m['design']['arms'][1]['changes']+='; same derived compatible-cache package'
    m['dataset']['version']='v1-current-compiler-cache'
    put(ADR/'실험/manifest.json',m)
    print(json.dumps({'compatible_cache_built':True,'seconds':round(time.monotonic()-start,2),'model_calls':0}),flush=True)

if __name__=='__main__':main()
