# Dataiku LEGAL_RAG 새 Python 노트북. 이번 ZIP을 ehA8dpVm에 업로드합니다.
# 이 코드는 Flow 설치만 수행합니다. 실행 중인 적재가 종료된 뒤 Scenario를 실행하세요.
ZIP_NAME='__ZIP_NAME__'
ZIP_SHA256='__ZIP_SHA256__'
LANDING_ID='ehA8dpVm'
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile
import dataiku

def open_package():
    if dataiku.default_project_key()!='LEGAL_RAG':raise ValueError('LEGAL_RAG_PROJECT_REQUIRED')
    folder=dataiku.Folder(LANDING_ID)
    names=[p for p in folder.list_paths_in_partition() if PurePosixPath(p).name==ZIP_NAME]
    if len(names)!=1:raise ValueError('이번 ZIP을 관리 폴더 ehA8dpVm에 정확히 한 개 업로드하세요.')
    with folder.get_download_stream(names[0]) as stream:raw=stream.read(16*1024**2+1)
    if len(raw)>16*1024**2 or hashlib.sha256(raw).hexdigest()!=ZIP_SHA256:raise ValueError('FLOW_ZIP_HASH')
    root=Path(tempfile.gettempdir())/('legal-gold-flow-'+ZIP_SHA256[:16]);root.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=z.namelist();manifest=json.loads(z.read('FLOW_MANIFEST.json'))
        if len(names)!=len(set(names)) or set(names)!=set(manifest['files'])|{'FLOW_MANIFEST.json'} or sum(i.file_size for i in z.infolist())>32*1024**2:
            raise ValueError('FLOW_ZIP_CONTENTS')
        for item in z.infolist():
            p=PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in item.filename or item.is_dir() or stat.S_ISLNK(item.external_attr>>16):raise ValueError('FLOW_ZIP_PATH')
            path=root.joinpath(*p.parts)
            if root.resolve() not in path.resolve().parents:raise ValueError('FLOW_ZIP_ESCAPE')
            content=z.read(item)
            if item.filename!='FLOW_MANIFEST.json' and hashlib.sha256(content).hexdigest()!=manifest['files'][item.filename]:raise ValueError('FLOW_FILE_HASH')
            if path.exists():
                if path.read_bytes()!=content:raise ValueError('FLOW_CODE_CHANGED')
            else:
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
    sys.path.insert(0,str(root))
    return root

FLOW_PACKAGE=open_package()
