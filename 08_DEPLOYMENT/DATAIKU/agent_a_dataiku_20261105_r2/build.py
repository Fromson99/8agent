"""Preserve the verified Agent DDL and add explicit DSS statement boundaries."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
OLD = OUT.parent / 'agent_a_unified_20261105_r1'
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261105-agent-a-dataiku-r2'
AUDIT.mkdir(parents=True, exist_ok=True)
previous = (OLD / 'AGENT_A_CREATE_ALL_R1.txt').read_text()
old_build = json.loads((OLD / 'BUILD.json').read_text())
assert hashlib.sha256(previous.encode()).hexdigest() == old_build['sql_sha256']
block = previous[previous.index('DECLARE\n'):].strip()
verify = (OLD / 'VERIFY_TABLES.sql').read_text().strip()
header = '''-- AGENT_A_CREATE_ALL_R2: Dataiku Oracle SQL notebook (AIDP1 / target SIDDA).
-- R1 대신 이 파일 전체를 Query 하나에 붙여넣고, 부분 선택을 해제한 뒤 RUN.
-- 파일 끝까지 복사하세요. 문장 구분용 주석 두 줄도 반드시 포함합니다.
-- 생성/검증 PL/SQL 1개 + 결과 조회 SQL 1개입니다. SQL*Plus / 는 붙이지 않습니다.
-- 완료: 오류 없이 결과 4행, COLUMNS_RESULT / PK_RESULT 모두 PASS, 컬럼 합계 26.
-- 생성 블록에서 조회 인덱스 7개의 소속/컬럼순서/상태도 검증합니다.
-- 기존 정상 객체/행은 유지하고 없는 테이블/인덱스만 생성합니다. A_1 이관 없음.
-- DDL은 문장별 커밋됩니다. 오류 시 원인 해결 후 이 파일 전체를 재실행하세요.
-- 현장 Dataiku 직접 실행은 미확인. 로컬 Oracle 검증과 구분합니다.
'''
delivery = header + block + '\n\n-- DKU_END_STATEMENT\n\n' + verify + '\n\n-- DKU_END_STATEMENT\n'
segments = [s.strip() for s in re.split(r'^-- DKU_END_STATEMENT\s*$', delivery, flags=re.M) if s.strip()]
assert len(segments) == 2 and segments[0].endswith('END;')
assert segments[1] == verify and not verify.endswith(';')
assert not re.search(r'^\s*/\s*$', delivery, re.M)
for ext in ('sql', 'txt'):
    (OUT / ('AGENT_A_CREATE_ALL_R2.' + ext)).write_text(delivery)
(OUT / 'VERIFY_TABLES.sql').write_text(verify + '\n')
build = {**old_build, 'schema_version': 'agent-a-dataiku-explicit-statements-v2',
         'source_reference': str(OLD.relative_to(ROOT)),
         'previous_sql_sha256': old_build['sql_sha256'],
         'sql_sha256': hashlib.sha256(delivery.encode()).hexdigest(),
         'block_sha256': hashlib.sha256(block.encode()).hexdigest(),
         'plsql_body_unchanged': True, 'explicit_statement_count': 2,
         'dataiku_documentation': 'https://doc.dataiku.com/dss/latest/code-recipes/sql.html#multiple-statements-handling'}
(OUT / 'BUILD.json').write_text(json.dumps(build, ensure_ascii=False, indent=2) + '\n')
active = (ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes()
(AUDIT / 'baseline.json').write_text(json.dumps({'active_sha256': hashlib.sha256(active).hexdigest(),
    'active': json.loads(active), 'delivery_sha256': build['sql_sha256']}, indent=2) + '\n')
print(json.dumps({'file': 'AGENT_A_CREATE_ALL_R2.txt', 'bytes': len(delivery.encode()),
                  'sha256': build['sql_sha256'], 'explicit_statements': 2, 'plsql_body_unchanged': True}))
