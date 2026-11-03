# Dataiku LEGAL_RAG / Oracle AIDP / 응답·배치 비교 R1을 실행한 Python 노트북의 새 셀.
# 먼저 첨부 G19_INDEX_JOIN_TEMP_CHECK_20261103_R2.zip을 관리 폴더 ehA8dpVm에 그대로 업로드.
# SELECT만 수행합니다. 기존 INSERT·비교 셀을 다시 실행하거나 Run All을 누르지 마세요.
COMPARISON_PATH = ''  # 같은 커널이면 자동 연결. 필요할 때만 기존 COMPARISON.json의 정확한 절대경로.

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile

_sqlcheck_hints=[]
_sqlcheck_previous=globals().get('_g19_comparison')
if getattr(_sqlcheck_previous,'OUTPUT',None):
    _sqlcheck_hints.append(str(_sqlcheck_previous.OUTPUT/'COMPARISON.json'))
_sqlcheck_saved=globals().get('_g19_comparison_result')
if isinstance(_sqlcheck_saved,dict) and _sqlcheck_saved.get('output'):
    _sqlcheck_hints.append(_sqlcheck_saved['output'])


def _sqlcheck_bootstrap():
    import dataiku
    folder=dataiku.Folder('ehA8dpVm')
    name='__ZIP_NAME__'
    matches=[p for p in folder.list_paths_in_partition() if PurePosixPath(p).name==name]
    if len(matches)!=1:raise ValueError('관리 폴더 ehA8dpVm에 '+name+'을 정확히 한 개 업로드하세요.')
    with folder.get_download_stream(matches[0]) as stream:raw=stream.read(1024**2+1)
    if len(raw)>1024**2 or hashlib.sha256(raw).hexdigest()!='__ZIP_SHA256__':raise ValueError('SQL_CHECK_ZIP_HASH')
    target=Path(tempfile.gettempdir())/'g19-index-join-temp-__ZIP_PREFIX__'
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest=json.loads(archive.read('MANIFEST.json'))
        names=archive.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(manifest['files'])|{'MANIFEST.json'}:raise ValueError('SQL_CHECK_ZIP_MEMBERS')
        if sum(i.file_size for i in archive.infolist())>512*1024:raise ValueError('SQL_CHECK_ZIP_SIZE')
        for item in archive.infolist():
            relative=PurePosixPath(item.filename)
            if relative.is_absolute() or '..' in relative.parts or item.is_dir() or (item.external_attr>>16)&0o170000==0o120000:raise ValueError('SQL_CHECK_ZIP_PATH')
            path=(target/item.filename).resolve()
            if target.resolve() not in path.parents:raise ValueError('SQL_CHECK_ZIP_ESCAPE')
            content=archive.read(item)
            if item.filename!='MANIFEST.json' and hashlib.sha256(content).hexdigest()!=manifest['files'][item.filename]:raise ValueError('SQL_CHECK_MEMBER_HASH')
            if path.exists():
                if path.read_bytes()!=content:raise ValueError('SQL_CHECK_EXTRACTED_CHANGED')
            else:
                with path.open('xb') as stream:stream.write(content)
    for key in list(sys.modules):
        if key.startswith('g19sql_'):del sys.modules[key]
    sys.path.insert(0,str(target))
    import g19sql_notebook
    return g19sql_notebook


_g19_sqlcheck=_sqlcheck_bootstrap()
_g19_sqlcheck_result=_g19_sqlcheck.run(COMPARISON_PATH,_sqlcheck_hints)


def SHOW_SQL_CHECK(name='요약',cursor=1):
    _g19_sqlcheck.show(name,cursor)  # 저장된 결과만 표시. SQL 재실행 없음.
