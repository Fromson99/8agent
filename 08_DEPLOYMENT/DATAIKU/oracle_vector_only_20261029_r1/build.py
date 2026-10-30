"""Overlay only the two Dataiku entry files on the verified six-column R3."""
from pathlib import Path
import hashlib
import json
import zipfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'vector_silver_20261029_r3'
archive = BASE / 'VECTOR_SILVER_CODE_20261029_R3.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'bae9c8a74764396cea16ef6fc33d2576c1ea8c4139a8c427d2abdbf9533c4b4d'
with zipfile.ZipFile(archive) as z:
    original = json.loads(z.read('CODE_MANIFEST.json'))
    files = {n: z.read(n) for n in original['files']}
assert all(hashlib.sha256(b).hexdigest() == original['files'][n] for n, b in files.items())
for name in ('vector_silver/install.py', 'vector_silver/runtime.py', 'LEGACY_BOOTSTRAP.txt'):
    files[name] = (HERE / name).read_bytes()
# Replace the inherited guide so the archive cannot give conflicting entry instructions.
files['GUIDE.txt'] = (HERE / 'GUIDE.txt').read_bytes()
manifest = {**original, 'format': 'oracle-vector-only-dataiku-v1',
            'scope': 'Oracle completed source -> existing R4 vector recipe; no upstream load recipe',
            'parent_zip_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files': {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}}
payload = HERE / 'payload'
for name, body in files.items():
    target = payload / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    if name.endswith('.py'):
        compile(body, name, 'exec')
files['CODE_MANIFEST.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
(payload / 'CODE_MANIFEST.json').write_bytes(files['CODE_MANIFEST.json'])
code_name = 'ORACLE_VECTOR_ONLY_CODE_20261029_R1.zip'
with zipfile.ZipFile(HERE / code_name, 'w', zipfile.ZIP_DEFLATED) as z:
    for name, body in sorted(files.items()):
        z.writestr(name, body)
zip_hash = hashlib.sha256((HERE / code_name).read_bytes()).hexdigest()
bootstrap = (BASE / 'BOOTSTRAP.py').read_text().replace('VECTOR_SILVER_CODE_20261029_R3.zip', code_name)
bootstrap = bootstrap.replace('bae9c8a74764396cea16ef6fc33d2576c1ea8c4139a8c427d2abdbf9533c4b4d', zip_hash)
(HERE / 'BOOTSTRAP.py').write_text(bootstrap)
cell = '''# LEGAL_RAG 새 Python 노트북 커널. 먼저 코드 ZIP을 기존 ehA8dpVm 폴더에 업로드.
# 기존 00~03/벡터 작업이 실행 중이면 종료를 확인한 뒤 설치합니다.
# QUERY_RELEASE_ID: 01_ORACLE_STATUS.sql의 COMPLETE 조회 판본 ID (최신 날짜 자동 선택 없음).
QUERY_RELEASE_ID = ""
# 이미 프로젝트 변수에 LEGAL_VECTOR_PROFILE이 있으면 아래 공란 유지.
EMBED_MODEL = ""
EMBED_REVISION = ""
EMBED_DIMENSIONS = 0
'''
cell += bootstrap
cell += '\nfrom vector_silver.install import install\nVECTOR_CFG = install(dataiku.api_client().get_default_project(), ' + repr(bootstrap) + ',\n query_release_id=QUERY_RELEASE_ID, model=EMBED_MODEL, revision=EMBED_REVISION, dimensions=EMBED_DIMENSIONS)\n'
cell += 'print("설치 완료. DATAIKU_RUN.txt의 check 실행 후 기존 R4 레시피를 Run 하세요.")\n'
compile(cell, 'DATAIKU_INSTALL.txt', 'exec')
(HERE / 'DATAIKU_INSTALL.txt').write_text(cell)
(HERE / 'DATAIKU_RUN.txt').write_text('''# 설치와 동일한 노트북의 다음 셀. 실제 DB 검사는 check, 임베딩/적재는 build.
ACTION = "check"
from vector_silver.runtime import run
RESULT = run(VECTOR_CFG, action=ACTION)
print(RESULT)
# check 통과 뒤 Flow LEGAL_04_VECTOR_SILVER_R4만 Run 하거나 ACTION="build"로 실행.
# 기존 source/embedding 설정을 그대로 사용하며 00~03 재실행은 필요 없습니다.
''')
receipt = {'parent_zip_sha256': manifest['parent_zip_sha256'], 'code_zip_sha256': zip_hash,
           'changed_python': ['vector_silver/install.py', 'vector_silver/runtime.py'],
           'base_backend_identical': all(files[n] == (BASE/'payload'/n).read_bytes()
                                         for n in original['files'] if n.startswith('02_BACKEND/')),
           'field_applied': False, 'main_changed': False, 'model_calls': 0}
(HERE / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
