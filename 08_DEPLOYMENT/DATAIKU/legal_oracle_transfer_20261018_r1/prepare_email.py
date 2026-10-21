"""Seal tested data-only artifacts and prepare the explicitly requested Samsung email."""
from pathlib import Path
import base64
import hashlib
import html
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

from build_delivery import HERE, ROOT, PACKAGE, ZIP, NAMES, seal

AUDIT = ROOT / '09_ARTIFACTS/AUDITS/oracle_transfer_20261018_r1'
report = ET.parse(AUDIT / 'junit.xml').getroot()
suites = list(report.iter('testsuite'))
assert sum(int(s.attrib.get('failures', 0)) + int(s.attrib.get('errors', 0)) for s in suites) == 0
count = sum(int(s.attrib['tests']) for s in suites)
assert count == 21

# Compile both the complete cells and their embedded implementations on the field Python major/minor.
compiler = Path('/home/jin/.local/bin/python3.11')
code = r'''
import ast, base64, json, pathlib, sys, zlib
root=pathlib.Path(sys.argv[1]); checked=[]
for p in sorted(root.rglob('*.py'))+sorted(root.glob('LEGAL_ORACLE_0[234]_*.txt')):
    text=p.read_text(); tree=ast.parse(text); compile(text,str(p),'exec')
    checked.append(str(p.relative_to(root)))
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>1000 and node.value.startswith('eN'):
            raw=zlib.decompress(base64.b64decode(node.value)); compile(raw,str(p)+' embedded','exec')
            checked.append(str(p.relative_to(root))+' embedded')
print(json.dumps({'version':sys.version,'executable':sys.executable,'compiled':checked}))
'''
compiled = subprocess.run([str(compiler), '-c', code, str(PACKAGE)], check=True, text=True, capture_output=True)
tested = {str(p.relative_to(PACKAGE)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in sorted(PACKAGE.rglob('*')) if p.is_file() and p.name not in {'SHA256SUMS.txt', 'VALIDATION.json'}}
validation = {
    'status': 'LOCAL_PASS', 'tests_passed': count,
    'environment': 'Real temporary SQLite, synthetic data, simulated ORDS. No internal network or model calls.',
    'pytest_python': sys.version, 'field_python_compile': json.loads(compiled.stdout),
    'junit': str((AUDIT / 'junit.xml').relative_to(ROOT)),
    'coverage': [
        'Exact attached cells: existing sample rows -> full source run -> full verify -> assets -> complete release.',
        'Re-execution without duplicate writes and source file hashes unchanged.',
        'Read-only verify detects changed remote row, unverified receipt prevents publication.',
        'Denied writes and lost commit responses: failure then explicit resume; no premature COMPLETE.',
        'Large Unicode CLOB, empty CLOB/NULL, source/target mismatch, count mismatch, budgets and malformed responses.',
        'DDL table names/grants match writer contract; no deletion statements.'
    ],
    'setup_issue': 'Initial pytest base-directory parent was missing; preserved junit_setup_failure.xml. Created parent then all 21 passed.',
    'not_validated': ['Oracle SQL engine DDL/PLSQL', 'GENOS field full transfer', 'Field throughput', 'MAIN/serving deployment'],
    'tested_files_sha256': tested,
}
(PACKAGE / 'VALIDATION.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n')
seal()

subject = '[법규 RAG] 추가 2테이블 SQL + 원문·색인 전체 이관 묶음 (2026-10-18 R1)'
body = '''<p>요청하신 추가 테이블 SQL과 데이터 이관 코드를 한 묶음으로 보냅니다.</p>
<p><b>이번 첨부의 01 → 02 → 03 → 04 → 05 순서로 사용하세요.</b> 이전 메일에서 셀을 따로 찾아 조합할 필요 없습니다.
기존 데이터와 샘플 행은 보존하며, 동일한 행은 재사용합니다.</p>
<ol>
<li><b>01 TABLES — Dataiku AIDP SQL 노트북:</b> SIDDA.LEGAL_RAG_ASSET_PART_A와 SIDDA.LEGAL_RAG_RELEASE_A를 추가합니다.
CREATE 2문장을 각각 실행하고, GRANT 2문장은 권한 담당자가 실행합니다. BAIP04APP의 SELECT/INSERT가 필요합니다.</li>
<li><b>02 SOURCE_RUN — GENOS R6 노트북 새 Code 셀:</b> 원문 3테이블 전체 이관. SOURCE_COMPLETE까지 실행합니다.</li>
<li><b>03 SOURCE_VERIFY — 같은 커널 새 Code 셀:</b> 쓰기 없이 모든 원문 행/열과 건수를 다시 대조합니다. VERIFIED까지 확인합니다.</li>
<li><b>04 ASSETS — 같은 커널 새 Code 셀:</b> 기존 탐색·전문검색 색인과 용어집/캐시를 업로드합니다. COMPLETE와 DP_RELEASE_ID를 보관합니다.</li>
<li><b>05 CHECK_SQL — Dataiku:</b> 원문 버전별 건수와 완료 버전을 확인합니다.</li>
</ol>
<p>GENOS의 성공한 R6 연결 desk를 그대로 사용합니다. client ID/secret은 첨부에 없습니다.
원본은 /nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation/store.sqlite 입니다.</p>
<p>02/04는 PAUSED 후 같은 셀로 이어갈 수 있습니다. 03 전체 대조는 기본 6시간이며 중단 후 재실행하면 처음부터 검사합니다.
세부 한도와 복구 방법은 GUIDE_UTF8.txt에 적었습니다.</p>
<p>ZIP을 업로드한 실제 TRANSFER 폴더에서 다음 명령으로 풉니다.</p>
<pre>python3 -m zipfile -e ./LEGAL_ORACLE_TRANSFER_20261018_R1.zip ./LEGAL_ORACLE_TRANSFER_20261018_R1</pre>
<p>02~04 TXT는 Python 노트북 셀에 붙여넣는 코드입니다. bash로 실행하지 않습니다.
모든 실행 TXT는 ZIP 안과 별도 첨부에 같은 내용으로 들어 있습니다.</p>
<p>이 묶음의 전체 이관 범위는 선택한 RAG generation의 원문과 선언된 검색 자산입니다.
NFS 전체 파일·과거 세대·대화/피드백 DB 이관은 포함하지 않습니다.
이번 메일은 데이터 이관용이며 MAIN 코드 패치나 서빙 전환을 실행하지 않습니다.</p>
<p>실제 임시 SQLite와 모의 Oracle/ORDS로 21검사 통과, Python 3.11.15 문법 컴파일 확인.
현장 Oracle SQL 엔진·전체 건수·속도와 실제 서빙 동작은 현장 실행으로 확인해야 합니다.</p>'''
attachments = [ZIP, *[PACKAGE / n for n in NAMES.values()], PACKAGE / 'GUIDE_UTF8.txt']
metadata = [{'filename': p.name, 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in attachments]
parts = [{'mime_type': 'text/html', 'charset': 'UTF-8', 'body': {'content': body}}]
for p in attachments:
    parts.append({'mime_type': 'application/zip' if p.suffix == '.zip' else 'text/plain',
                  'filename': p.name, 'content_disposition': 'attachment',
                  'body': {'base64_url_content': base64.urlsafe_b64encode(p.read_bytes()).decode()}})
args = {'to': 'hyungjininfocz.son@partner.samsung.com', 'subject': subject,
        'payload': {'mime_type': 'multipart/mixed', 'parts': parts},
        'response_fields': ['id', 'thread_id', 'label_ids']}
(HERE / 'EMAIL_ARGS.json').write_text(json.dumps(args, ensure_ascii=False))
(HERE / 'EMAIL_BODY.html').write_text(body)
(HERE / 'EMAIL_ATTACHMENTS.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'subject': subject, 'attachments': metadata, 'args_bytes': (HERE / 'EMAIL_ARGS.json').stat().st_size}, ensure_ascii=False))
