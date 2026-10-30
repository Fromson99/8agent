"""Ship a single notebook fix cell; no replacement package upload is needed."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_recipes_20261027_r1'
metadata=json.loads((BASE/'DELIVERY_MANIFEST.json').read_text())
for name,digest in metadata['files'].items():
    assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==digest,name
baseline=('LANDING_ID = "ehA8dpVm"\nPACKAGE_NAME = '+repr(metadata['package'])
          +'\nPACKAGE_SHA256 = '+repr(metadata['package_sha256'])
          +'\nPACKAGE_BYTES = '+str(metadata['package_bytes'])+'\n'+(BASE/'bootstrap.py').read_text())
with zipfile.ZipFile(BASE/metadata['package']) as z:
    assert z.read('bootstrap.py')==(BASE/'bootstrap.py').read_bytes()
    datasets=[v['name'] for v in json.loads(z.read('oracle_datasets.json'))]
adapter=(HERE/'input_selection.py').read_text()
reference={'baseline_bootstrap':baseline,'adapter_source':adapter,'datasets':datasets,
           'old_package_sha256':metadata['package_sha256']}
(HERE/'REFERENCE.json').write_text(json.dumps(reference,ensure_ascii=False,indent=2)+'\n')
script='''# LEGAL_RAG Python 노트북 한 셀에서 전체 실행. 실행 중인 01~03 배치가 없어야 합니다.
# S3 파일 이동/삭제/새 업로드 없이 기존 세 레시피의 입력 파일명만 명시합니다.
ACTION = 'apply'  # 원복할 때만 'rollback'
'''+(HERE/'update_recipes.py').read_text()+'''
import dataiku
if dataiku.default_project_key() != 'LEGAL_RAG':
    raise ValueError('LEGAL_RAG 프로젝트에서 실행하세요.')
'''+ 'BASELINE_BOOTSTRAP = '+repr(baseline)+'\nADAPTER_SOURCE = '+repr(adapter)+'\nOUTPUT_DATASETS = '+repr(datasets)+'''
if ACTION == 'apply':
    selected = {'RAW_INPUT.zip', 'RAW_INPUT.zip.receipt.json',
                'PIPELINE_SUPPORT.zip', 'PIPELINE_SUPPORT.zip.receipt.json'}
    paths = {p.lstrip('/') for p in dataiku.Folder('ehA8dpVm').list_paths_in_partition()}
    missing = sorted(selected - paths)
    if missing:
        raise ValueError('SELECTED_INPUT_MISSING: ' + ', '.join(missing))
    print('INPUT_FILES_PRESENT', sorted(selected))
FIX_RESULT = update(dataiku.api_client().get_project('LEGAL_RAG'), BASELINE_BOOTSTRAP,
                    ADAPTER_SOURCE, OUTPUT_DATASETS,
                    'legal_input_selection_20261027_r2_backup', action=ACTION)
'''
name='DATAIKU_INPUT_SELECTION_FIX_20261027_R2.txt'
compile(script,name,'exec')
(HERE/name).write_text(script)
archive='DATAIKU_INPUT_SELECTION_FIX_20261027_R2.zip'
members=[name,'input_selection.py','update_recipes.py','GUIDE.txt','WORK_CONTRACT.txt']
with zipfile.ZipFile(HERE/archive,'w',zipfile.ZIP_DEFLATED) as z:
    for member in members:
        info=zipfile.ZipInfo(member,(2026,10,27,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(HERE/member).read_bytes())
with zipfile.ZipFile(HERE/archive) as z:
    assert z.read(name)==(HERE/name).read_bytes()
    assert all(Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'} for n in z.namelist())
manifest={'revision':'named-inputs-20261027-r2','baseline_package_sha256':metadata['package_sha256'],
          's3_mutations':0,'worker_or_oracle_changes':False,
          'files':{n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in [name,archive,'GUIDE.txt']}}
(HERE/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'status':'BUILT','files':list(manifest['files'])}))
