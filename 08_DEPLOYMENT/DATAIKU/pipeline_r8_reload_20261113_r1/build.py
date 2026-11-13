"""R8 재적재 전달본 만들기 — R7 Flow ZIP + 내용 기준 행 번호 + 재적재 Flow(레시피 4개, S3 읽기만).

R7 ZIP에서 정확히 한 번씩 나오는 줄만 바꾼다(부모가 다르면 멈춤). GENOS 코드는 바꾸지 않는다.
"""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R7 = ROOT/'08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1'
R7_FLOW = 'DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip'
R7_FLOW_SHA = 'd69a6ae3e097858b9c45bdff10e009f32b28290b48ab27b230e71057882929d2'
FLOW = 'DATAIKU_ZIP_R8_RELOAD_R5.zip'
SETUP = 'DATAIKU_SETUP_R8_RELOAD_R5.txt'
# 같은 노트북 커널에서 이전 판 셀을 돌렸으면 그 판 모듈이 sys.modules에 남아 새 판 대신 쓰인다(11-13 현장 R4).
PURGE = ("import sys\n"
         "def _r8_old(v):\n"
         "    try:\n"
         "        return 'agent-flow-code-' in str(getattr(v, '__file__', None) or '')+str(list(getattr(v, '__path__', None) or []))\n"
         "    except Exception:\n"
         "        return False   # 살펴볼 수 없는 모듈은 이 설치기 것이 아님\n"
         "for _m in [k for k, v in list(sys.modules.items()) if _r8_old(v)]:\n"
         "    del sys.modules[_m]\n"
         "sys.path[:] = [p for p in sys.path if 'agent-flow-code-' not in p]\n")
PUBLISH = 'engine/vendor/02_BACKEND/lawrag/pipeline/oracle_query_publish.py'
REDUCED = 'engine/reduced_export.py'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(obj): return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError('PARENT_SOURCE_CHANGED:'+old[:90])
    return text.replace(old, new)


def stable_rows_patch(text, definition):
    """두 _asset_rows(전체·축소 모드)에 같은 변경: 일반 표·뷰 → 내용 키, 본문 검색 → 단위 키."""
    text = replace(text, definition,
                   definition+'    from stable_rows import plain_rows, plain_key, length_key, posting_key\n')
    text = replace(text,
                   "        rows = db.execute('SELECT '+','.join(_name(c) for c in columns)+' FROM '+_name(table))\n"
                   "        for ordinal, row in enumerate(rows):\n",
                   "        for ordinal, (repeat, row) in enumerate(plain_rows(db, table, columns)):\n")
    text = replace(text, "key=[ordinal, value], **_lookups(value))", "key=plain_key(value, repeat), **_lookups(value))")
    text = replace(text, "value,key=row['rowid'],lookup_id=str(row['logical_id']),",
                   "value,key=length_key(unit_index,row['rowid'],row['logical_id']),lookup_id=str(row['logical_id']),")
    text = replace(text, "value, key=[doc,column,token],",
                   "value, key=posting_key(unit_index,doc,column,token,logical_id),")
    return text


def flow_files():
    raw = (R7/R7_FLOW).read_bytes()
    if sha(raw) != R7_FLOW_SHA:
        raise ValueError('PARENT_ZIP_HASH')
    with zipfile.ZipFile(R7/R7_FLOW) as z:
        flow = {n: z.read(n) for n in z.namelist()}
    flow['engine/stable_rows.py'] = (HERE/'stable_rows.py').read_bytes()
    flow['reload_runtime.py'] = (HERE/'reload_runtime.py').read_bytes()
    flow['reload_install.py'] = (HERE/'reload_install.py').read_bytes()

    flow[PUBLISH] = stable_rows_patch(flow[PUBLISH].decode(), 'def _asset_rows(db, relative):\n').encode()
    flow[REDUCED] = stable_rows_patch(flow[REDUCED].decode(),
                                      'def _asset_rows(db, relative, *, excluded_tables=()):\n').encode()

    prod = flow['prod_pipeline.py'].decode()
    prod = replace(prod, "    query['gold_projection'] = {'version': 'gold-zip-flow-full-v1',\n"
                         "                                'sha256': base.file_hash(Path(__import__('fast_export').__file__))}\n",
                   "    query['gold_projection'] = {'version': 'gold-zip-flow-full-v2-content-rows',\n"
                   "                                'sha256': base.file_hash(Path(__import__('fast_export').__file__)),\n"
                   "                                'row_key_sha256': base.file_hash(Path(__import__('stable_rows').__file__))}\n")
    flow['prod_pipeline.py'] = prod.encode()

    code = json.loads(flow['engine/CODE_MANIFEST.json'])
    for name in ('vendor/02_BACKEND/lawrag/pipeline/oracle_query_publish.py', 'reduced_export.py'):
        if name not in code['files']:
            raise ValueError('CODE_MANIFEST_ENTRY_MISSING:'+name)
        code['files'][name] = sha(flow['engine/'+name])
    code['files']['stable_rows.py'] = sha(flow['engine/stable_rows.py'])
    code['version'] = code['version']+'-r8-content-rows'
    flow['engine/CODE_MANIFEST.json'] = encode(code)

    flow.pop('FLOW_MANIFEST.json')
    flow['FLOW_MANIFEST.json'] = encode({'files': {n: sha(b) for n, b in flow.items()}})
    return flow


def pack(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for n, raw in sorted(files.items()):
            if Path(n).suffix.lower() in {'.zip', '.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('NESTED_OR_JS_MEMBER')
            z.writestr(zipfile.ZipInfo(n), raw, compress_type=zipfile.ZIP_DEFLATED)
    return sha(path.read_bytes())


def setup_txt(flow_sha):
    text = (R7/'DATAIKU_SETUP_R7.txt').read_text()
    boot = next(l for l in text.splitlines() if l.startswith('BOOTSTRAP = '))
    boot = replace(boot, R7_FLOW, FLOW)
    boot = replace(boot, R7_FLOW_SHA, flow_sha)
    params = {
        'CODE_FOLDER_ID': 'LGL_R8_CODE',   # 이 ZIP을 올린 OBS 폴더의 이름 또는 ID
        'INPUT_FOLDER_ID': 'LGL_R8_PARTS', # 구조화 세대 ZIP 조각 폴더의 이름 또는 ID — 없으면 OBS에 새로 만든다(읽기만)
        'WRITE_FOLDER_ID': '',             # 결과 폴더를 만들 쓰기 연결의 폴더 (비우면 코드 폴더와 같은 연결·버킷)
        'FOLDER_PATH': '',                 # 비우면 코드 폴더(LGL_R8_CODE)의 경로 규칙(개발계 /dataiku/${projectKey}/${odbId})
        'EXPECTED_ARCHIVE': 'genos-rag-data-20261007T002029Z-7c0b050f.zip',
        'EXPECTED_PARTS': 34,
        'ORIGINAL_SHA_FILE': '',     # 비우면 입력 폴더의 ORIGINAL.sha256
        'PARTS_SHA_FILE': '',        # 비우면 입력 폴더의 PARTS.sha256
        'SELECTION_CHANNEL': '',     # ZIP에 판본 선택이 없을 때 같은 세대를 서빙 중인 채널 이름 (점검 P01)
        'TARGET_CONNECTION': 'AIDP', 'EXPECTED_DB_USER': 'PIDD2APP',
        'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1', 'EMBED_DIMENSIONS': 1024,
        'STATS_DEGREE': 4,
    }
    head = ('# R8 재적재 설치 셀 R5 — 구조화 세대 ZIP 조각 → 새 행 번호로 Gold에 새 세대 (S3는 쓰지 않음).\n'
            '# R5: 설치가 쓰는 폴더마다 작은 파일을 써 보고, 막혀 있으면 경로를 LGL_R8_CODE와 같은 규칙(/dataiku/...)으로 바꾼다.\n'
            '#     (개발계 OBS는 /dataiku/ 밑에만 쓸 수 있어 R3·R4가 만든 폴더 5개가 404.) 같은 노트북에서 다시 돌려도 이전 판\n'
            '#     모듈을 먼저 지우므로 커널 재시작은 필요 없다. R3·R4가 설치된 프로젝트에서는 폴더 경로를 고치고 레시피를 R5로 바꾼다.\n'
            '# 새 프로젝트: 변수 LGL_GOLD_OWNER(개발계 "SIDDS", 운영 "SIDDG") → OBS 폴더 LGL_R8_CODE 에 '+FLOW+' 업로드 →\n'
            '# 이 셀을 Python 노트북에 그대로 붙여 실행(조각 폴더 LGL_R8_PARTS 가 없으면 OBS에 만들어 줌) →\n'
            '# LGL_R8_PARTS 에 조각·ORIGINAL.sha256·PARTS.sha256 업로드 → Scenarios > LGL_R8_RELOAD_RUN_ALL > RUN.\n'
            '# 조각 이름·개수가 다르면 EXPECTED_ARCHIVE / EXPECTED_PARTS 를 고칩니다. 지금 서빙 채널은 바뀌지 않습니다.\n')
    body = ('PARAMS = '+json.dumps(params, ensure_ascii=False, indent=1)+'\n'+PURGE+boot+
            '\nexec(BOOTSTRAP)\nfrom reload_install import install_reload\ncfg = install_reload(PARAMS, BOOTSTRAP)\n')
    compile(body, SETUP, 'exec')
    return head+body


def main():
    flow = flow_files()
    flow_sha = pack(HERE/FLOW, flow)
    (HERE/SETUP).write_text(setup_txt(flow_sha), encoding='utf-8')
    print(FLOW, flow_sha, len(flow), 'files')


if __name__ == '__main__':
    main()
