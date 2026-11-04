# 기존 개발계 프로젝트의 Python 노트북에서 셀 하나로 실행합니다.
# 아래 폴더에 DATAIKU_GOLD_ONECLICK_SAMPLE_20261104_R1.zip 하나만 올려두세요.
PARAMS = {
    'CODE_FOLDER_ID': '',         # 이미 업로드/저장이 되는 기존 Managed Folder ID
    'ORACLE_CONNECTION': 'AIDP',  # 기존 값. 실제 개발계 연결명과 다르면 변경
    'EXPECTED_DB_USER': 'PIDD2APP',# 기존 값. 실제 개발계 접속 계정과 다르면 변경
    'GOLD_OWNER': '',             # 테스트 테이블을 생성할 실제 개발계 스키마
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,
    'WORK_DIR': '',               # 기본 자동 지정. 중단 후 재개하려면 이 작업 경로 보존
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

ZIP_NAME = 'DATAIKU_GOLD_ONECLICK_SAMPLE_20261104_R1.zip'
ZIP_SHA256 = 'd1c32fb5eb0c9c65679100c01c9fc7d7ef83b69b9f22b9c5d4cd2030285fec0b'


def open_package():
    folder = dataiku.Folder(PARAMS['CODE_FOLDER_ID'])
    names = [p for p in folder.list_paths_in_partition() if PurePosixPath(p).name == ZIP_NAME]
    if len(names) != 1: raise ValueError('UPLOAD_ONE_CODE_ZIP:'+ZIP_NAME)
    with folder.get_download_stream(names[0]) as stream: raw = stream.read(16*1024**2+1)
    if len(raw)>16*1024**2 or hashlib.sha256(raw).hexdigest()!=ZIP_SHA256: raise ValueError('CODE_ZIP_HASH')
    root = Path(tempfile.gettempdir()) / ('gold-oneclick-code-'+ZIP_SHA256[:16])
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

# A prior failed Flow installer is harmless: this launcher uses separate module names.
# If another loader already ran in this kernel, keep its state separate.
for _name in ("oneclick","oneclick_config","oneclick_pipeline","oneclick_db","oneclick_guard",
              "oneclick_storage","oneclick_state","oneclick_panel","run_full","gold_io",
              "fast_loader","fast_insert","vector_stage","jdbc_transport","mesh_embedding"):
    _loaded=sys.modules.get(_name)
    if _loaded is not None and FLOW_PACKAGE.resolve() not in Path(getattr(_loaded,"__file__","")).resolve().parents:
        raise RuntimeError("RESTART_KERNEL_OTHER_LOADER:"+_name)

from oneclick import run
RESULT = run(PARAMS)
