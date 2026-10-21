from pathlib import Path
import ast
import base64
import hashlib
import json
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREVIOUS = ROOT / '08_DEPLOYMENT/DATAIKU/legal_oracle_transfer_20261018_r1/package'
R6 = ROOT / '09_ARTIFACTS/HANDOFFS/dataiku_ords_sdk_default_20261014_r6/package/01_DATAIKU_ORDS_STEP_BY_STEP_R6.ipynb'
NAME = 'LEGAL_ORACLE_FULL_TRANSFER_20261019_R1'
PACKAGE = HERE / 'package'
PACKAGE.mkdir(exist_ok=True)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def build():
    # Only the definitions cell is reused. Credential/value/output cells are never copied.
    book = json.loads(R6.read_text())
    core = ''.join(book['cells'][2]['source'])
    tree = ast.parse(core)
    assert isinstance(tree.body[-1], ast.Expr) and isinstance(tree.body[-1].value, ast.Call)
    assert ast.unparse(tree.body[-1].value.func) == 'print'
    core = '\n'.join(core.splitlines()[:tree.body[-1].lineno - 1]) + '\n'
    modules = [('_legal19_core', core, str(R6.relative_to(ROOT)) + '#cell-2-definitions')]
    imports = {'from semantic_runtime.oracle_dp_io import': 'from _legal19_io import',
               'from .oracle_dp_io import': 'from _legal19_io import',
               'from semantic_runtime.oracle_dp_assets import': 'from _legal19_assets import',
               'from .oracle_migration import': 'from _legal19_migration import'}
    for filename, module in [('oracle_dp_io.py', '_legal19_io'), ('oracle_dp_assets.py', '_legal19_assets'),
                             ('oracle_migration.py', '_legal19_migration'), ('oracle_publish.py', '_legal19_publish')]:
        source = (PREVIOUS / 'sources' / filename).read_text()
        for old, new in imports.items():
            source = source.replace(old, new)
        modules.append((module, source, str((PREVIOUS / 'sources' / filename).relative_to(ROOT))))
    modules.append(('_legal19_flow', (HERE / 'notebook_flow.py').read_text(), str((HERE / 'notebook_flow.py').relative_to(ROOT))))
    bootstrap = '''# 공통 코드 준비: 수정할 필요 없습니다. 이 셀은 DB에 접속하지 않습니다.
import base64 as _b, hashlib as _h, zlib as _z, types as _t, sys as _s
def _load(name, encoded, sha):
    if name in _s.modules:
        if getattr(_s.modules[name], '_delivery_sha', None) != sha:
            raise RuntimeError('다른 버전이 같은 커널에 있습니다. 커널 재시작 후 이 노트북을 실행하세요.')
        return _s.modules[name]
    raw = _z.decompress(_b.b64decode(encoded))
    if _h.sha256(raw).hexdigest() != sha:
        raise RuntimeError('노트북 코드 해시가 다릅니다. 첨부 원본을 다시 올리세요.')
    module = _t.ModuleType(name)
    _s.modules[name] = module
    exec(compile(raw, name + '.py', 'exec'), module.__dict__)
    module._delivery_sha = sha
    return module
'''
    origins = {}
    for name, text, origin in modules:
        raw = text.encode()
        compile(raw, name + '.py', 'exec')
        bootstrap += f'{name} = _load({name!r}, {base64.b64encode(zlib.compress(raw, 9)).decode()!r}, {digest(raw)!r})\n'
        origins[name] = {'origin': origin, 'embedded_sha256': digest(raw)}
    bootstrap += 'print("준비 완료. 01 설정 → 02 인증 → 03 연결 → 04 점검 → 05 이관 → 06 대조 → 07 게시 → 08 결과 순서입니다.")\n'
    cells = []
    def add(kind, source, step=None, hidden=False):
        c = {'cell_type': kind, 'id': f'legal-{len(cells):03d}', 'metadata': {}, 'source': source.splitlines(keepends=True)}
        if step: c['metadata']['legal_step'] = step
        if hidden: c['metadata']['jupyter'] = {'source_hidden': True}
        if kind == 'code': c.update(execution_count=None, outputs=[])
        cells.append(c)
    def section(title, detail, code, step):
        add('markdown', '## ' + title + '\n\n' + detail + '\n')
        add('code', code.strip() + '\n', step)
    add('markdown', '''# 법규 데이터 Oracle 전체 이관 — 새 통합 노트북 R1

**이 파일 하나를 GENOS Jupyter에 새로 올리고 위에서부터 실행하세요. 이전 노트북·TXT 셀을 붙일 필요 없습니다.**

원문 3테이블 → 전체 대조 → 탐색/전문검색 색인·용어집 업로드까지 포함합니다.
기존 Oracle 데이터는 동일 값이면 재사용하며 다른 값은 덮어쓰지 않습니다.

1. 기존 R6 노트북이 있던 **같은 Jupyter 폴더**에 이 파일을 올립니다. 기존 로그 폴더는 보존합니다.
2. Python 3 커널에서 **00 → 01 → … → 08** 순서로 셀을 하나씩 실행합니다.
3. 02에서 승인받은 client ID/secret을 입력합니다. 환경변수에 있으면 재사용하며 값은 출력·저장하지 않습니다.
4. 오류/PAUSED가 나오면 해당 셀에서 멈춥니다. 안내를 확인한 뒤 해당 셀을 다시 실행합니다.

Oracle의 기존 원문 3개와 추가 자산 2개, 총 5테이블이 필요합니다.
추가 2개가 아직 없으면 **맨 아래 ‘추가 테이블 SQL’**을 먼저 Dataiku AIDP SQL 노트북에서 실행하고
BAIP04APP의 SELECT/INSERT 권한을 받으세요. 이미 만든 테이블은 다시 만들지 않습니다.

이관 범위: 지정한 generation의 원문·선언된 검색 자산. NFS 전체/대화 DB/과거 세대는 포함하지 않습니다.
이 파일은 데이터 이관용입니다. MAIN 코드 설치·서빙 환경변수 변경·워크플로우 검증은 별도입니다.
''')
    add('markdown', '## 00 · 공통 코드 준비\n\n아래 접힌 셀을 한 번 실행하세요. 수정하지 않습니다. 코드가 모두 포함되어 있어 별도 Python 파일 설치가 필요 없습니다.\n')
    add('code', bootstrap, 'bootstrap', True)
    section('01 · 원본과 기록 폴더',
            '원본 경로는 이전에 확인한 값입니다. **LOG_DIR는 이전 R6와 같은 폴더**를 사용하세요. '
            '다른 위치에 노트북을 올렸다면 LOG_DIR에 기존 로그 폴더의 절대경로를 넣습니다. '
            'SCHEMA는 ORDS 별칭 b04이며 테이블 소유자 SIDDA와 다릅니다.', '''
SOURCE_SQLITE = "/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation/store.sqlite"
LOG_DIR = "./ords_stepwise_r6_logs"
SCHEMA = "b04"
EXPECTED_LOGIN_USER = "BAIP04APP"
# 이전 R6 기록과 연결하기 위한 값입니다. R6에서 바꿨다면 같은 값을 사용합니다.
PREFIX = "DKU_POC_S5C581378E"
TIMEOUT = 30
REENTER_CREDENTIALS = False   # 인증을 다시 입력하려면 True
TRANSFER_SECONDS = 3600      # 원문 이관: 1시간 후 PAUSED면 이어 실행
VERIFY_SECONDS = 21600       # 전체 대조: 6시간, 중단 후에는 처음부터 대조
PUBLISH_SECONDS = 3600       # 색인 게시: 1시간 후 PAUSED면 이어 실행
SETTINGS = dict(schema=SCHEMA, prefix=PREFIX, timeout=TIMEOUT, log_dir=LOG_DIR)
print("원본:", SOURCE_SQLITE)
print("기록 폴더:", LOG_DIR)
print("주소: 기존 성공한 SDK 기본 설정 사용")
''', 'settings')
    section('02 · 인증 입력',
            '실행하면 입력창이 뜹니다. client ID와 secret을 붙여넣고 각각 Enter를 누르세요. '
            '코드에 직접 적을 필요가 없습니다. 인증값 오타라면 01의 REENTER_CREDENTIALS=True 후 01→02→03을 실행합니다.', '''
if "desk" not in globals():
    desk = _legal19_core.NotebookDesk(SETTINGS)
else:
    desk.settings = SETTINGS
_legal19_flow.safe(desk, lambda: desk.credentials(replace=REENTER_CREDENTIALS))
print("인증값 준비 완료. 값은 출력하지 않습니다.")
''', 'credentials')
    section('03 · Oracle 연결 확인',
            '여기서 처음 접속합니다. BAIP04APP 연결 완료가 나오면 다음으로 갑니다. 인증 실패 시 아래 단계는 실행하지 않습니다.', '''
CONNECTION_RESULT = _legal19_flow.safe(desk, lambda: _legal19_flow.connect(desk, EXPECTED_LOGIN_USER))
''', 'connect')
    section('04 · 원본·5테이블 점검 — 쓰기 없음',
            '추가 2개 테이블의 접근 여부와 원문 3개 구조, 원본 건수를 확인합니다. '
            'CHECKED_NO_WRITES이면 다음 단계로 갑니다. SELECT 성공만으로 INSERT 권한이 확인된 것은 아닙니다.', '''
CHECK_RESULT = _legal19_flow.safe(desk, lambda: _legal19_flow.source_stage(desk, SOURCE_SQLITE, "check", 300))
''', 'check')
    section('05 · 원문 전체 이관',
            '**실제 INSERT 단계입니다.** SOURCE_COMPLETE까지 실행합니다. PAUSED면 이 셀을 다시 실행하면 이어갑니다. '
            '기존 샘플과 같은 행은 재사용합니다. 기록 경로와 SOURCE_COUNTS를 보관하세요.', '''
LEGAL_FULL_TRANSFER_RESULT = _legal19_flow.safe(desk, lambda: _legal19_flow.source_stage(desk, SOURCE_SQLITE, "run", TRANSFER_SECONDS))
''', 'run')
    section('06 · 원문 전체 대조',
            'Oracle에 쓰지 않고 모든 원문 행·열·긴 CLOB·건수를 다시 확인합니다. **VERIFIED**이면 다음 단계로 갑니다. '
            'PAUSED 후 재실행은 처음부터 대조합니다. 필요하면 01의 VERIFY_SECONDS를 늘립니다. 기존 7일/누적 호출 한도는 유지됩니다.', '''
LEGAL_FULL_TRANSFER_RESULT = _legal19_flow.safe(desk, lambda: _legal19_flow.source_stage(desk, SOURCE_SQLITE, "verify", VERIFY_SECONDS))
''', 'verify')
    section('07 · 색인·용어집 업로드',
            '검증 기록을 디스크에서 찾아 기존 탐색/전문검색/용어집 파일을 압축 분할 업로드합니다. '
            '재색인·재임베딩하지 않습니다. PAUSED면 이 셀을 다시 실행합니다. **COMPLETE와 DP_RELEASE_ID**를 확인하세요.', '''
LEGAL_DP_PUBLISH_RESULT = _legal19_flow.safe(desk, lambda: _legal19_flow.publish(desk, SOURCE_SQLITE, PUBLISH_SECONDS))
print(LEGAL_DP_PUBLISH_RESULT)
''', 'publish')
    section('08 · 완료 결과 확인',
            'Oracle의 완료 버전을 다시 읽어 이관 기록과 비교합니다. 결과의 DP_RELEASE_ID와 두 receipt 경로를 보관하세요. '
            'Dataiku Explore는 샘플을 새로고침해야 새 행이 보일 수 있습니다.', '''
FINAL_RESULT = _legal19_flow.safe(desk, lambda: _legal19_flow.summary(desk, SOURCE_SQLITE))
''', 'summary')
    add('markdown', '''## 중단 후 다시 시작할 때

- 커널이 살아 있으면 실패/PAUSED한 셀만 다시 실행합니다. 자동 네트워크 재시도는 하지 않습니다.
- 새 커널이면 **00~03을 다시 실행**한 다음, 진행 중이던 **05 / 06 / 07 / 08** 셀로 갑니다.
  같은 원본·접속 설정·기록 폴더를 유지하면 디스크의 기존 기록과 예산을 사용합니다.
- 05는 배치, 07은 자산 분할 위치부터 이어갑니다. 06 대조는 처음부터 다시 합니다.
- PRIOR_BINDING: 이전 이관과 인증·설정 등이 다릅니다. 이전 값을 확인하며 새 로그 폴더로 우회하지 않습니다.
- R6_RECOVERY: 이전 R6 쓰기 보류가 남았습니다. 기존 기록을 확인해야 하며 자동으로 보류를 지우지 않습니다.
- 원문 값 충돌·해시 불일치·권한 오류는 원인을 확인한 뒤 재개합니다. 기존 행/기록을 삭제하지 않습니다.
- 최초 작업의 7일 기한과 누적 SQL 100만 회 한도는 재개해도 유지됩니다.
- source-v2 원문 한 값 64MiB 초과 또는 별도 vectors 자산이 선언된 세대는 이 계약에서 중단합니다.
- 기록 폴더 디스크 256MiB, 가용 RAM 512MiB 미만이면 추가 작업을 시작하지 않습니다.
  무거운 이관/색인 작업은 이 노트북 하나씩 실행합니다.

## 추가 테이블 SQL — Dataiku에서 실행

CREATE 두 문장과 GRANT 두 문장을 각각 별도 Query로 실행합니다. GRANT는 소유자/권한 담당자가 수행합니다.
이미 만든 테이블은 재생성하지 않습니다. 이 노트북은 테이블 삭제·자동 생성 SQL을 실행하지 않습니다.

```sql
''' + (PREVIOUS / 'LEGAL_ORACLE_01_TABLES_20261018_R1.txt').read_text() + '\n```\n')
    add('markdown', '''## Dataiku 확인용 SQL

아래 SELECT는 Dataiku AIDP SQL 노트북에서 각각 실행합니다.

```sql
''' + (PREVIOUS / 'LEGAL_ORACLE_05_CHECK_SQL_20261018_R1.txt').read_text() + '\n```\n')
    notebook = {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                 'language_info': {'name': 'python', 'version': '3.11'}, 'legal_delivery': NAME}, 'nbformat': 4, 'nbformat_minor': 5}
    (PACKAGE / (NAME + '.ipynb')).write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n')
    # Complete code counterpart; users normally open the ipynb, not separate snippets.
    txt = '# Python 3 전체 실행본. 평소에는 같은 이름의 ipynb를 열어 셀별로 실행하세요.\n# 터미널 일괄 실행: python3 ./' + NAME + '_RUN.txt\n'
    for c in cells:
        source = ''.join(c['source'])
        if c['cell_type'] == 'markdown':
            txt += '\n# %% [markdown]\n' + ''.join('# ' + line + '\n' for line in source.splitlines())
        else:
            txt += '\n# %%\n' + source
    (PACKAGE / (NAME + '_RUN.txt')).write_text(txt)
    (PACKAGE / 'SOURCE_BINDING.json').write_text(json.dumps({'name': NAME, 'modules': origins,
        'scope': 'Standalone notebook; original source/asset migration engines unchanged; no MAIN deployment',
        'credentials_included': False, 'previous_log_compatibility': 'R6 exact binding + log directory',
        'notebook_cells': len(cells), 'code_cells': sum(c['cell_type'] == 'code' for c in cells)}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'notebook': str(PACKAGE / (NAME + '.ipynb')), 'cells': len(cells), 'code_cells': sum(c['cell_type'] == 'code' for c in cells)}))


if __name__ == '__main__':
    build()
