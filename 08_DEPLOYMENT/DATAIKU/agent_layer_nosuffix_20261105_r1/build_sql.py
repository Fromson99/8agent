"""Create the requested suffixless SIDDA SQL from the preserved Agent DDL."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json
import re

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = OUT.parent / 'agent_gold_layer_20261105_r1'
PACKAGE = OUT / 'package'
PACKAGE.mkdir(exist_ok=True)
sha = lambda value: hashlib.sha256(value).hexdigest()
files = {}
source_hashes = {}
for path in sorted((SOURCE / 'package').glob('*.sql')):
    original = path.read_bytes()
    name = path.name.replace('_A_1', '_A')
    text = original.decode().replace('_A_1', '_A')
    assert '_A_1' not in text and not text.rstrip().endswith(';')
    assert text.startswith(('SELECT ', 'WITH ', 'CREATE TABLE ', 'CREATE INDEX '))
    assert not re.search(r'\b(?:DROP|ALTER|TRUNCATE|GRANT|INSERT|UPDATE|DELETE)\b', text)
    (PACKAGE / name).write_text(text)
    files[name] = sha(text.encode())
    source_hashes[path.name] = sha(original)
assert len(files) == 14
header = '''-- SIDDA Agent 테이블 4개: 접미사 _1 없는 이름으로 생성·검증합니다.
-- Dataiku SQL 노트북의 별도 Query마다 한 SQL문씩 실행합니다.
-- 이 TXT 전체를 한 Query에 붙이지 않습니다. 문장 끝 세미콜론은 없습니다.
-- 00 존재 확인 → 없는 표의 01~04 → 없는 인덱스의 05~11 → 12/13 검증.
-- 기존 객체가 있으면 해당 CREATE를 제외하고 12/13으로 구조부터 확인합니다.
-- 기존 객체 변경·삭제·권한 부여·기존 기록 이관 SQL은 포함하지 않습니다.

'''
combined = header + '\n\n'.join('-- ' + name + '\n' + (PACKAGE / name).read_text() for name in files)
(OUT / 'SIDDA_AGENT_NO1_RUN_R1.txt').write_text(combined)
with ZipFile(OUT / 'SIDDA_AGENT_NO1_SQL_20261105_R1.zip', 'w', ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(PACKAGE / name, name)
source_build = json.loads((SOURCE / 'BUILD.json').read_text())
tables = json.loads(json.dumps(source_build['tables']).replace('_A_1', '_A'))
build = {'tables': tables, 'sql_files': files, 'source_sql_files': source_hashes,
         'change': 'Only _A_1 object identifiers changed to _A; columns, types and constraints retained.',
         'source_package': str(SOURCE.relative_to(ROOT)), 'source_main': 142}
(OUT / 'BUILD.json').write_text(json.dumps(build, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'sql_files': len(files), 'tables': len(tables), 'zip_sha256': sha((OUT / 'SIDDA_AGENT_NO1_SQL_20261105_R1.zip').read_bytes())}))
