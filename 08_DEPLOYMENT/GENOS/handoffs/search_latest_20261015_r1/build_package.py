"""Seal fixed reviewed payload; installer preserves the site's unrelated pins."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
NAME='GENOS_SEARCH_LATEST_20261015_R1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()


def main():
    previous=HERE.parent/'latest_internal_20261015_r1'
    base=json.loads((HERE/'PREIMAGES.json').read_bytes())
    for row in base:row['before']=[row['before']]
    for row in json.loads((previous/'PREIMAGES.json').read_bytes()):
        base.append({'path':row['path'],'before':[row['before']]})
    for path in ('02_BACKEND/semantic_runtime/search_selection.py','02_BACKEND/lawrag/pipeline/search_selection.py'):
        base.append({'path':path,'before':[None]})
    for row in base:row['after']=sha((ROOT/row['path']).read_bytes())
    dependencies=['02_BACKEND/semantic_runtime/contracts.py','02_BACKEND/semantic_runtime/resident_data.py',
        '02_BACKEND/semantic_runtime/folder_navigation.py','02_BACKEND/semantic_runtime/pipeline.py',
        '02_BACKEND/semantic_runtime/fulltext.py','02_BACKEND/semantic_runtime/unit_fulltext.py',
        '06_TOOLS/COMMANDS/genos_release_gate.py','06_TOOLS/COMMANDS/genos_generation_e2e.py',
        '02_BACKEND/lawrag/pipeline/genos_stages.py','02_BACKEND/lawrag/pipeline/structure_selection.py']
    manifest={'format':'8agent-code/1','scope':NAME,
        'files':[{'path':r['path'],'sha256':r['after'],'bytes':(ROOT/r['path']).stat().st_size} for r in base],
        'required_files':[{'path':p,'sha256':sha((ROOT/p).read_bytes())} for p in dependencies]}
    (HERE/'CODE_MANIFEST.json').write_bytes(encode(manifest))
    with zipfile.ZipFile(HERE/'CODE.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.writestr('CODE_MANIFEST.json',encode(manifest))
        for row in base:z.write(ROOT/row['path'],row['path'])
    spec={'version':NAME,'files':base,'manifest':manifest,'code_zip_sha256':sha((HERE/'CODE.zip').read_bytes())}
    (HERE/'PATCH_SPEC.json').write_bytes(encode(spec))
    members=['CODE.zip','CODE_MANIFEST.json','PATCH_SPEC.json','apply.py','run.py','smoke_check.py',
        NAME+'_RUN.txt','GUIDE_UTF8.txt','DESIGN.txt']
    with zipfile.ZipFile(HERE/(NAME+'.zip'),'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name in members:z.write(HERE/name,name)
    print(json.dumps({'files':len(base),'zip_bytes':(HERE/(NAME+'.zip')).stat().st_size,
                      'sha256':sha((HERE/(NAME+'.zip')).read_bytes())}))


if __name__=='__main__':main()
