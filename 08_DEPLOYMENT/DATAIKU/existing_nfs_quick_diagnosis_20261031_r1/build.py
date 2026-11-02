import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ZIP_NAME = 'DATAIKU_NFS_QUICK_DIAG_20261031_R1.zip'
TXT_NAME = 'DATAIKU_NFS_QUICK_DIAG_RUN_R1.txt'
source = (HERE / 'quick_diagnosis.py').read_bytes()
compile(source, 'quick_diagnosis.py', 'exec')
ast.parse(source.decode(), feature_version=(3, 8))
with zipfile.ZipFile(HERE / ZIP_NAME, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    info = zipfile.ZipInfo('quick_diagnosis.py', (2026, 10, 31, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    z.writestr(info, source)
blob = (HERE / ZIP_NAME).read_bytes()
digest = hashlib.sha256(blob).hexdigest()
text = '''# Dataiku LEGAL_RAG 별도 조회용 Python 노트북에서 전체를 한 번 실행하세요.
# 적재 중인 커널은 중단/재시작하지 않습니다. ZIP은 ehA8dpVm에 압축 그대로 업로드합니다.
# 출력: 요약15줄 + 상세9줄(제목 포함). DB SQL, 적재/재개, 파일 쓰기 없음.
SHOW_DETAIL = True  # False이면 요약15줄만 표시
DIAG_JOB_DIR = None  # 기본값 유지: 기존 LEGAL_PIPELINE_SCRATCH 경로에서 자동 조회

def _run_quick_diagnosis():
    import hashlib
    import io
    import zipfile
    import dataiku
    name = __ZIP_NAME__
    expected = __SHA256__
    expected_bytes = __SIZE__
    folder = dataiku.Folder('ehA8dpVm')
    with folder.get_download_stream('/' + name) as stream:
        raw = stream.read(expected_bytes + 1)
    if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('DIAG_ZIP_HASH')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != ['quick_diagnosis.py']:
            raise ValueError('DIAG_ZIP_MEMBERS')
        code = archive.read('quick_diagnosis.py')
    namespace = {'__name__': 'quick_diagnosis_handoff'}
    exec(compile(code, 'quick_diagnosis.py', 'exec'), namespace)
    namespace['main'](job_dir=DIAG_JOB_DIR, detail=SHOW_DETAIL)

try:
    _run_quick_diagnosis()
except Exception as _diag_error:
    print('[빠른 진단 R1] 실행 준비 실패:', type(_diag_error).__name__)
    print('ZIP을 ehA8dpVm에 압축 그대로 올렸는지 확인하세요. 기존 적재는 건드리지 않았습니다.')
'''.replace('__ZIP_NAME__', repr(ZIP_NAME)).replace('__SHA256__', repr(digest)).replace('__SIZE__', str(len(blob)))
compile(text, TXT_NAME, 'exec')
ast.parse(text, feature_version=(3, 8))
(HERE / TXT_NAME).write_text(text, encoding='utf-8')
with zipfile.ZipFile(HERE / ZIP_NAME) as z:
    assert z.namelist() == ['quick_diagnosis.py']
    assert z.read('quick_diagnosis.py') == source
    assert not any(n.lower().endswith(('.zip', '.js', '.jsx', '.mjs', '.cjs')) for n in z.namelist())
files = [ZIP_NAME, TXT_NAME, 'GUIDE.txt']
record = {'files': {n: {'bytes': (HERE / n).stat().st_size,
                       'sha256': hashlib.sha256((HERE / n).read_bytes()).hexdigest()} for n in files},
          'zip_members': ['quick_diagnosis.py'], 'nested_archives': False, 'javascript_members': False,
          'field_execution': False}
(HERE / 'BUILD.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(record, ensure_ascii=False, indent=2))
