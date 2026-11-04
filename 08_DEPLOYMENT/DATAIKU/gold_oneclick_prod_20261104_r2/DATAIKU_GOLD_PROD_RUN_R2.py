# 운영계 Dataiku: 아래 설정을 확인하고 이 TXT 전체를 Python 노트북 셀 하나에서 실행합니다.
# 코드 ZIP + 기존 데이터 34조각 + PARTS.sha256 + ORIGINAL.sha256을 업로드합니다.
# CODE_FOLDER_ID는 표시 이름이 아니라 실제 Managed Folder ID입니다.
PARAMS = {
    'CODE_FOLDER_ID': '',          # 필수: 정상 업로드/다운로드되는 기존 폴더 ID
    'INPUT_FOLDER_ID': '',         # 같은 폴더면 빈 값. 별도 데이터 폴더면 그 ID
    'ORACLE_CONNECTION': 'AIDP',    # 기존 운영계 Oracle 연결 이름
    'EXPECTED_DB_USER': 'PIDD2APP', # Oracle 접속 계정. owner와 구분
    'GOLD_OWNER': 'SIDDS',          # 사용자 확인값. 운영 등록 테이블도 SIDDS인지 확인
    'TABLE_PREFIX': 'IDD_B003_LGL_',
    'TABLE_NAMES': {},             # 등록명이 다른 경우에만 {'DOC_VER':'실제이름', ...}
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,
    'WORK_DIR': '',                # 선택: DSS에서 쓰기 가능한 영속 Linux 절대경로(기준 폴더)
}

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile
import dataiku

ZIP_NAME = 'DATAIKU_GOLD_ONECLICK_PROD_20261104_R2.zip'
ZIP_SHA256 = '7148f3dc0e1c9dc5a1127114e3a646679ec3ea9ad708435f594ae8ef66f6db31'


def open_package():
    folder = dataiku.Folder(PARAMS['CODE_FOLDER_ID'])
    names = [p for p in folder.list_paths_in_partition() if PurePosixPath(p).name == ZIP_NAME]
    if len(names) != 1: raise ValueError('UPLOAD_ONE_CODE_ZIP:'+ZIP_NAME)
    with folder.get_download_stream(names[0]) as stream: raw = stream.read(16*1024**2+1)
    if len(raw)>16*1024**2 or hashlib.sha256(raw).hexdigest()!=ZIP_SHA256: raise ValueError('CODE_ZIP_HASH')
    root = Path(tempfile.gettempdir()) / ('gold-oneclick-prod-code-'+ZIP_SHA256[:16])
    root.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist(); manifest = json.loads(z.read('FLOW_MANIFEST.json'))
        if len(names)!=len(set(names)) or set(names)!=set(manifest['files'])|{'FLOW_MANIFEST.json'}:
            raise ValueError('CODE_ZIP_MEMBERS')
        if sum(i.file_size for i in z.infolist())>32*1024**2: raise ValueError('CODE_ZIP_SIZE')
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in item.filename or item.is_dir() or stat.S_ISLNK(item.external_attr>>16):
                raise ValueError('CODE_ZIP_PATH')
            dest = root.joinpath(*p.parts)
            if dest.is_symlink() or root.resolve() not in dest.resolve().parents: raise ValueError('CODE_PATH_ESCAPE')
            content = z.read(item)
            if item.filename!='FLOW_MANIFEST.json' and hashlib.sha256(content).hexdigest()!=manifest['files'][item.filename]:
                raise ValueError('CODE_FILE_HASH')
            if dest.exists():
                if dest.read_bytes()!=content: raise ValueError('EXTRACTED_CODE_CHANGED')
            else:
                dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(content)
    sys.path.insert(0,str(root))
    return root


FLOW_PACKAGE = open_package()

# Restart the kernel once if a previous Flow/sample loader was imported.
for _name in ("prod_run","prod_config","prod_pipeline","prod_guard","prod_storage","prod_state","prod_panel",
              "run_full","gold_io","fast_loader","fast_insert","vector_stage","jdbc_transport","mesh_embedding"):
    _loaded=sys.modules.get(_name)
    if _loaded is not None and FLOW_PACKAGE.resolve() not in Path(getattr(_loaded,"__file__","")).resolve().parents:
        raise RuntimeError("RESTART_KERNEL_OTHER_LOADER:"+_name)

from prod_run import run
RESULT = run(PARAMS)
