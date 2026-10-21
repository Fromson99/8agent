from pathlib import Path
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from build import HERE, ROOT, PACKAGE, NAME, R6

AUDIT = ROOT / '09_ARTIFACTS/AUDITS/oracle_notebook_20261019_r1'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


first = ET.parse(AUDIT / 'junit.xml').getroot()
second = ET.parse(AUDIT / 'junit_structure.xml').getroot()
passed = {c.attrib['name'] for c in first.iter('testcase') if c.find('failure') is None and c.find('error') is None}
assert len(passed) == 8
passed |= {c.attrib['name'] for c in second.iter('testcase') if c.find('failure') is None and c.find('error') is None}
assert len(passed) == 9

compile_code = r'''
import ast,base64,json,pathlib,sys,zlib
root=pathlib.Path(sys.argv[1]); book=json.loads(next(root.glob('*.ipynb')).read_text()); total=0
payloads=[]
for c in book['cells']:
 if c['cell_type']=='code':
  source=''.join(c['source']); compile(source,c['id'],'exec');total+=1
  for n in ast.walk(ast.parse(source)):
   if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_load':
    raw=zlib.decompress(base64.b64decode(ast.literal_eval(n.args[1])))
    compile(raw,ast.literal_eval(n.args[0]),'exec');total+=1
    payloads.append(raw.decode())
compile(next(root.glob('*_RUN.txt')).read_text(),'RUN.txt','exec');total+=1
old=json.loads(pathlib.Path(sys.argv[2]).read_text())
for i in (8,10):
 value=ast.literal_eval(ast.parse(''.join(old['cells'][i]['source'])).body[0].value)
 assert value and not any(value in p for p in payloads), 'Credential literal copied'
print(json.dumps({'python':sys.version,'executable':sys.executable,'compiled':total,'credentials_scan':'PASS'}))
'''
compiled = subprocess.run(['/home/jin/.local/bin/python3.11', '-c', compile_code, str(PACKAGE), str(R6)],
                          capture_output=True, text=True, check=True)
validation = {
    'status': 'LOCAL_PASS', 'tests_passed': len(passed), 'tests': sorted(passed),
    'field_python_compile': json.loads(compiled.stdout),
    'runtime': 'Real synthetic SQLite plus fake genos.ords SDK; exact delivered notebook cells from empty namespace.',
    'restart': 'Fresh namespace reconnects and reuses on-disk source/publication receipts, original deadline and cumulative calls.',
    'max_test_rss_kib': 283696,
    'resource_policy': 'Single sequential pytest process; no model calls or internal network access.',
    'initial_test_failure': '8 functional checks passed; nbformat package missing for structure check. Used official v5.10.4 JSON schema with installed jsonschema; re-ran only structure check, passed.',
    'schema_url': 'https://raw.githubusercontent.com/jupyter/nbformat/v5.10.4/nbformat/v4/nbformat.v4.5.schema.json',
    'schema_sha256': sha(HERE / 'validation/nbformat.v4.5.schema.json'),
    'baseline_environment_issue': 'WSL/Linux/Git configuration passed; pre-existing 00_SYSTEM/ARCHITECTURE.md:431 trailing blank line. Unrelated file left unchanged.',
    'notebook_sha256': sha(PACKAGE / (NAME + '.ipynb')),
    'run_txt_sha256': sha(PACKAGE / (NAME + '_RUN.txt')),
    'field_not_verified': ['Oracle SQL engine/privileges', 'Actual full transfer counts/throughput', 'GENOS RAG serving switch'],
    'main_or_source_modified': False,
}
(PACKAGE / 'VALIDATION.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n')
guide = f'''법규 Oracle 전체 이관 통합 노트북 — 2026-10-19 R1

이번에는 {NAME}.ipynb 하나를 열어 사용합니다.
이전 R6 노트북이나 2026-10-18의 여러 TXT 셀을 붙여넣을 필요 없습니다.
같은 파일이 ZIP 안에도 있습니다. RUN.txt는 전체 코드의 별도 보관본입니다.

1. 기존 R6가 있던 같은 Jupyter 폴더에 ipynb를 업로드합니다. 기존 로그 폴더는 보존합니다.
2. Python 3 커널에서 00~08 셀을 차례로 실행합니다.
3. 01 설정의 LOG_DIR는 기존 ./ords_stepwise_r6_logs를 가리켜야 합니다.
   다른 폴더에 업로드했다면 기존 로그 폴더의 절대경로로 지정합니다.
4. 02 입력창에 승인된 client ID와 secret을 입력합니다. 파일에는 인증값이 없습니다.
5. 03 연결, 04 점검, 05 원문 이관, 06 전체 대조, 07 색인·용어집 게시, 08 완료 결과입니다.
   성공 상태를 확인한 뒤 다음 셀로 갑니다. 추가 2테이블 SQL은 노트북 맨 아래에 있습니다.
6. 같은 커널이면 실패/PAUSED한 셀부터 다시 실행합니다.
   새 커널이면 00~03 이후 진행하던 셀로 갑니다. 06 대조는 처음부터 다시 합니다.

기존 이관 기록을 재사용하므로 PREFIX/TIMEOUT/인증/LOG_DIR를 임의로 바꾸지 않습니다.
이전 값과 다르면 PRIOR_BINDING으로 멈춥니다. 기존 작업의 7일 기한과 누적 호출 한도를 초기화하지 않습니다.
기존 동일 행/색인 조각을 재사용하며 삭제·덮어쓰기는 하지 않습니다.

ZIP을 쓰는 경우 실제 업로드한 TRANSFER 폴더에서:
python3 -m zipfile -e ./{NAME}.zip ./{NAME}
풀린 폴더의 ipynb를 기존 R6가 있던 Jupyter 폴더로 옮겨 열거나, LOG_DIR를 기존 절대경로로 지정합니다.
별도 ~/DEV 설치가 필요하지 않습니다.
RUN.txt는 같은 코드를 Python으로 일괄 실행하는 보관본입니다. 평소에는 ipynb를 사용합니다.
터미널 사용 시: python3 ./{NAME}_RUN.txt

범위: 선택한 compact-v2 generation의 원문 3테이블과 선언된 탐색/전문검색/용어집 자산.
총 5테이블 계약이며 NFS 전체/과거 세대/대화·피드백 DB/최종 그래프 직접질의 스키마는 별도입니다.
이관 완료와 MAIN 코드 배포·Oracle RAG 서빙 전환·워크플로우 성공은 별도로 확인합니다.
로컬 모의 SDK/실제 임시 SQLite 검사 9건, Python 3.11.15 컴파일과 ipynb 공식 스키마 검사를 통과했습니다.
GENOS/Oracle 실제 내부망에는 접속하지 않았습니다.
'''
(PACKAGE / 'READ_FIRST.txt').write_text(guide)
files = sorted(p for p in PACKAGE.iterdir() if p.is_file() and p.name != 'SHA256SUMS.txt')
(PACKAGE / 'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files))
archive = HERE / (NAME + '.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(PACKAGE.iterdir()):
        if p.is_file(): z.write(p, p.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert not any(Path(n).suffix.lower() in {'.js', '.jsx', '.mjs', '.cjs'} for n in z.namelist())
    assert z.read(NAME + '.ipynb') == (PACKAGE / (NAME + '.ipynb')).read_bytes()

# Completed synthetic fixtures only: stream to a lossless archive and verify before cleanup.
temp = AUDIT / 'tmp'
if temp.exists():
    fixtures = {str(p.relative_to(AUDIT)): sha(p) for p in temp.rglob('*') if p.is_file() and not p.is_symlink()}
    packed = AUDIT / 'completed-fixtures.tar.gz'
    with tarfile.open(packed, 'w:gz', compresslevel=6) as t:
        t.add(temp, arcname='tmp')
    with tarfile.open(packed, 'r:gz') as t:
        restored = {}
        for m in t:
            if m.isfile():
                h = hashlib.sha256()
                with t.extractfile(m) as f:
                    while chunk := f.read(1024 * 1024): h.update(chunk)
                restored[m.name] = h.hexdigest()
        assert restored == fixtures
    (AUDIT / 'FIXTURE_ARCHIVE.json').write_text(json.dumps({'archive_sha256': sha(packed), 'files_sha256': fixtures,
        'restore': 'tar -xzf completed-fixtures.tar.gz', 'synthetic_only': True, 'test_process_exited': True}, indent=2) + '\n')
    shutil.rmtree(temp)

subject = '[법규 RAG] 새로 올리는 전체 이관 통합 ipynb — 연결부터 색인 업로드까지 (2026-10-19 R1)'
body = f'''<p>전체 이관을 <b>{NAME}.ipynb 하나</b>로 다시 정리해서 보냅니다.</p>
<p><b>이전 여러 TXT를 붙여넣는 대신, 이번 ipynb를 새로 업로드해서 사용하세요.</b>
이전 노트북을 실행해 두지 않아도 됩니다. 인증 입력·연결 확인부터 코드가 모두 포함되어 있습니다.</p>
<ol><li>기존 R6 노트북이 있던 같은 Jupyter 폴더에 이번 ipynb를 업로드합니다. 기존 로그 폴더는 보존합니다.</li>
<li>Python 3 커널에서 <b>00 → 01 → … → 08</b> 순서로 셀을 실행합니다.</li>
<li>02 입력창에 승인된 client ID/secret을 입력합니다. 인증값은 첨부에 넣지 않았습니다.</li>
<li>03 연결 → 04 점검 → 05 원문 이관 → 06 전체 대조 → 07 색인·용어집 업로드 → 08 완료 결과입니다.</li></ol>
<p>추가 테이블 SQL도 노트북 맨 아래에 모았습니다. 이미 생성했다면 다시 만들 필요 없습니다.
완료 시 DP_RELEASE_ID와 이관/게시 기록 경로를 보관하세요.</p>
<p>기존 작업을 이어갈 때는 01의 LOG_DIR가 기존 ords_stepwise_r6_logs 폴더를 가리켜야 합니다.
다른 위치에 업로드했다면 기존 로그 폴더 절대경로를 지정하세요. 기존 동일 행은 재사용하고, 이전 기록과 예산을 유지합니다.</p>
<p>05/07이 PAUSED면 해당 셀부터 이어 실행하며, 06 전체 대조는 다시 처음부터 확인합니다.
커널을 재시작했으면 00~03 후 진행하던 셀로 이동하면 됩니다.</p>
<p>ipynb를 직접 첨부했고 같은 내용의 ZIP과 완전한 Python 실행 TXT도 함께 첨부합니다.
평소에는 ipynb만 사용하면 됩니다. ZIP 사용 시 실제 업로드한 TRANSFER 폴더에서:</p>
<pre>python3 -m zipfile -e ./{NAME}.zip ./{NAME}</pre>
<p>로컬 합성 검사 9건, Python 3.11.15 컴파일 및 공식 ipynb 구조 검사 통과.
실제 내부망 전체 이관·SQL 엔진·속도·서빙 전환은 현장 실행으로 확인해야 합니다.
이 노트북은 선택한 RAG 원문과 색인 자산의 이관용이며 MAIN 코드 배포나 서빙 설정을 변경하지 않습니다.</p>'''
paths = [PACKAGE / (NAME + '.ipynb'), archive, PACKAGE / (NAME + '_RUN.txt')]
parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
attachments = []
for p in paths:
    mime = 'application/zip' if p.suffix == '.zip' else 'application/x-ipynb+json' if p.suffix == '.ipynb' else 'text/plain'
    parts.append({'mime_type': mime, 'filename': p.name, 'content_disposition': 'attachment',
                  'body': {'base64_url_content': base64.urlsafe_b64encode(p.read_bytes()).decode()}})
    attachments.append({'filename': p.name, 'bytes': p.stat().st_size, 'sha256': sha(p)})
args = {'to': 'hyungjininfocz.son@partner.samsung.com', 'subject': subject,
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts}, 'response_fields': ['id', 'thread_id', 'label_ids']}
(HERE / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=False))
(HERE / 'EMAIL_BODY.html').write_text(body)
(HERE / 'ATTACHMENTS.json').write_text(json.dumps(attachments, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'attachments': attachments, 'args_bytes': (HERE / 'EMAIL_ARGS.json').stat().st_size,
                  'tests_passed': len(passed), 'compile': json.loads(compiled.stdout)}, ensure_ascii=False))
