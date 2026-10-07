"""Materialize research code pins without touching the frozen revision or MAIN."""
import hashlib,json,shutil
from pathlib import Path

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def materialize(source,output):
    source,output=Path(source).resolve(),Path(output).resolve()
    if output.exists():raise ValueError('research package output already exists')
    shutil.copytree(source,output,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    # Code bytes remain identical. Only engine and PIPELINE integrity metadata
    # bind the candidate instead of the original upstream implementation.
    pipeline=output/'00_SYSTEM/PIPELINE.json';config=json.loads(pipeline.read_text())
    changed=[]
    for entry in config['engines'].values():
        path=output/entry['manifest']
        if not path.is_file():continue
        m=json.loads(path.read_text())
        for name in m['files']:
            if (output/name).is_file():m['files'][name]=sha(output/name)
        if any('semantic_runtime/document_agent.py' in name or 'legal_agent/source_recall.py' in name for name in m['files']):
            for name in ['02_BACKEND/semantic_runtime/unit_fulltext.py','02_BACKEND/semantic_runtime/legal_agent/unit_reading.py','02_BACKEND/semantic_runtime/legal_agent/unit_selection.py','02_BACKEND/semantic_runtime/legal_agent/unit_relations.py','02_BACKEND/semantic_runtime/legal_agent/unit_dependencies.py']:
                if (output/name).exists():m['files'][name]=sha(output/name)
        path.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');entry['sha256']=sha(path)
        changed.append(str(path.relative_to(output)))
    pipeline.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
    allowed=set(changed)|{'00_SYSTEM/PIPELINE.json'}
    preserved={}
    for src in source.rglob('*'):
        if src.is_file() and '__pycache__' not in src.parts and src.suffix!='.pyc':
            rel=str(src.relative_to(source))
            if rel not in allowed:
                if sha(src)!=sha(output/rel):raise ValueError('research packaging changed implementation: '+rel)
                preserved[rel]=sha(src)
    receipt={'schema_version':'unit-candidate-package-v1','source':str(source),
        'metadata_changed':sorted(allowed),'implementation_bytes_unchanged':True,'implementation_hashes':preserved,
        'pipeline_sha256':sha(pipeline),'main_changed':False,'genos_deployed':False}
    (output/'package-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return output
