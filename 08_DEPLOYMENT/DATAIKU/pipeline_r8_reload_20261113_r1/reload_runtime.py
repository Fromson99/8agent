"""R8 재적재 — S3의 구조화 세대 ZIP 조각 → 새 행 번호로 Gold에 새 세대 (2026-11-13).

GENOS를 거치지 않는다. 원문도 필요 없다(이미 만든 구조화 세대를 다시 넣음).
S3 입력 폴더는 읽기만 한다. 실행 기록은 쓰기 폴더(OBS)에, 작업 파일은 WORK_DIR에 둔다.
지금 서빙 채널은 손대지 않는다. 새 세대는 적재기가 만드는 고유 채널(g19_<세대 앞 24자>)에만 연결된다.

레시피 4개 (시나리오 RUN_ALL이 차례로):
  01_RESTORE  조각 해시 확인 → 합치기 → 세대 풀기 → 판본 선택 정보 확인(없으면 지정 채널 세대에서 가져옴)
  02_CHECK    DB 계정·Gold 13표 구조·INSERT 권한(실제 쓰기 없음)·지금 채널 목록
  03_LOAD     원문·검색 행(새 행 번호)·게시·벡터·벡터 연결·행 수 대조
  04_STATS    Gold 표 통계 갱신(채널 바꾸기 전에 해야 실행 계획이 맞음)
"""
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent
WORK_NAME = 'r8-reload'
STEPS = (('restore', '01_RESTORE'), ('check', '02_CHECK'), ('load', '03_LOAD'), ('stats', '04_STATS'))
GOLD_KEYS = ('DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRC_POST', 'SRCH_POST', 'SRCH_ROW', 'SRCH_CHNL',
             'ONTL_POST', 'ONTL_HEAD', 'ONTL_ANC', 'VCTR_POST', 'VCTR_ITEM', 'VCTR_HEAD')
# 행이 많이 바뀌는 표 — 통계를 다시 모은다(나머지는 행 수가 작거나 세대마다 1행).
STATS_KEYS = ('DOC_VER', 'DOC_UNIT', 'DOC_BLK', 'SRC_POST', 'SRCH_POST', 'SRCH_ROW', 'SRCH_CHNL',
              'VCTR_POST', 'VCTR_ITEM', 'VCTR_HEAD')


class Stop(RuntimeError):
    pass


def engine_path():
    for p in (ROOT/'engine/vendor/02_BACKEND', ROOT/'engine/vendor', ROOT/'engine'):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def log(phase, **fields):
    print(phase, json.dumps(fields, ensure_ascii=False, sort_keys=True, default=str)[:4000], flush=True)


def put(folder, path, record):
    from flow_runtime import put as put_receipt
    put_receipt(folder, path, record)


def gold_target(variables):
    from gold_owner import resolve
    return resolve(variables)


def prod_config(cfg, gold):
    engine_path()
    from prod_config import target
    params = dict(TARGET_MODE='GOLD', GOLD_OWNER=gold['GOLD_OWNER'], TABLE_PREFIX=gold['TABLE_PREFIX'],
                  ORACLE_CONNECTION=cfg['TARGET_CONNECTION'], EXPECTED_DB_USER=cfg['EXPECTED_DB_USER'],
                  EMBED_MODEL=cfg['EMBED_MODEL'], EMBED_DIMENSIONS=cfg['EMBED_DIMENSIONS'],
                  # 새 세대 전용 벡터 연결 1행만 넣는다(기존 연결은 바꾸지 않음) — 시험 서빙이 벡터까지 쓰게.
                  ACTIVATE_NEW_VECTOR_HEAD=True)
    return {'params': params, 'project': cfg['project'], 'target': target(params)}


def target_root(paths, gold):
    root = paths/('target-'+gold['GOLD_OWNER']+'-'+(gold['TABLE_PREFIX'] or 'IDD_B003_LGL_'))
    root.mkdir(exist_ok=True)
    # 적재 본체는 세대가 <작업폴더>/restored/generation 에 있어야 한다고 확인한다. 한 번 푼 세대를 대상마다 공유.
    link = root/'restored'
    if not link.exists():
        link.symlink_to(Path('..')/'restored', target_is_directory=True)
    if link.resolve() != (paths/'restored').resolve():
        raise Stop('RESTORED_LINK_CHANGED')
    return root


def restore(cfg, paths, folders, variables, trial):
    engine_path()
    from lawrag.pipeline import oracle_legacy_parts as legacy, oracle_existing_zip as archive
    from gold_io import digest
    folder = folders['input']                       # S3 — 읽기만
    names = folder.list_paths_in_partition()
    info = legacy.inspect_parts(folder.get_download_stream, names, original_file=cfg.get('ORIGINAL_SHA_FILE', ''),
                                parts_file=cfg.get('PARTS_SHA_FILE', ''))
    if info['archive_name'] != cfg['EXPECTED_ARCHIVE'] or info['part_count'] != cfg['EXPECTED_PARTS']:
        raise Stop('ARCHIVE_OR_PART_COUNT_MISMATCH: 입력 폴더 '+info['archive_name']+' '+str(info['part_count'])+'조각, '
                   '설치값 '+cfg['EXPECTED_ARCHIVE']+' '+str(cfg['EXPECTED_PARTS'])+'조각')
    log('PARTS_READY', archive=info['archive_name'], parts=info['part_count'])
    joined = legacy.join_parts(folder.get_download_stream, names, paths/'joined',
                               original_file=cfg.get('ORIGINAL_SHA_FILE', ''), parts_file=cfg.get('PARTS_SHA_FILE', ''),
                               binding=digest({'project': cfg['project'], 'folder': cfg['INPUT_FOLDER_ID']}))
    result = archive.restore(joined, paths/'restored', expected_sha=info['archive_sha256'])
    binding = {k: info[k] for k in ('archive_name', 'archive_sha256', 'parts', 'part_count')}
    selection = paths/'restored/SEARCH_SELECTION/generation.json'
    record = {'status': 'RESTORED', 'archive': info['archive_name'], 'archive_sha256': info['archive_sha256'],
              'parts': info['part_count'], 'dataset_version': result['dataset_version'],
              'source_counts': result['source_counts'], 'selection_in_archive': selection.exists()}
    from flow_runtime import put as put_receipt
    import prod_pipeline as prod
    prod.fixed(paths/'input.json', {'generation': result['generation'], 'agent': binding})
    put_receipt(folders['restore'], trial+'/restore.json', record)
    log('RESTORED', **{k: v for k, v in record.items() if k != 'source_counts'})
    return record


SELECTION_FILE = 'SEARCH_SELECTION_GENERATION.json'


def selection_matches(selection, paths):
    import hashlib
    manifest = paths/'restored/generation/manifest.json'
    return (isinstance(selection, dict) and selection.get('schema_version') == 'filename-search-selection-v2'
            and selection.get('manifest_sha256') == hashlib.sha256(manifest.read_bytes()).hexdigest()
            and selection.get('store_sha256') == json.loads(manifest.read_text())['store_sha256'])


def write_selection(paths, selection):
    path = paths/'restored/SEARCH_SELECTION/generation.json'
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix('.partial')
    tmp.write_text(json.dumps(selection, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    tmp.rename(path)


def ensure_selection(db, contract, paths, cfg):
    """판본 선택 정보가 ZIP에 없으면(10-07 운영 ZIP 등) 차례로 찾는다.
    1) 코드 폴더(OBS)의 SEARCH_SELECTION_GENERATION.json  2) 설치값 SELECTION_CHANNEL 채널 세대에 들어간 것.
    어느 쪽이든 세대 해시(store·manifest)가 이 세대와 같아야 쓴다(다르면 멈춤)."""
    from gold_io import literal
    path = paths/'restored/SEARCH_SELECTION/generation.json'
    if path.exists():
        return {'source': 'archive'}
    import dataiku
    code = dataiku.Folder(cfg['CODE_FOLDER_ID'])
    found = [p for p in code.list_paths_in_partition() if p.lstrip('/') == SELECTION_FILE]
    if found:
        with code.get_download_stream(found[0]) as stream:
            raw = stream.read(16*1024**2+1)
        if len(raw) > 16*1024**2:
            raise Stop('SELECTION_FILE_TOO_LARGE')
        selection = json.loads(raw.decode('utf-8-sig'))
        if not selection_matches(selection, paths):
            raise Stop('SELECTION_FILE_OTHER_GENERATION: '+SELECTION_FILE+'는 이 세대의 판본 선택이 아닙니다')
        write_selection(paths, selection)
        return {'source': 'code-folder-file', 'excluded': len(selection.get('excluded') or [])}
    channel = (cfg.get('SELECTION_CHANNEL') or '').strip()
    if not channel:
        raise Stop('SEARCH_SELECTION_REQUIRED: ZIP에 판본 선택 정보가 없습니다. 코드 폴더에 '+SELECTION_FILE+
                   '(NFS 세대 옆 SEARCH_SELECTION/generation.json)를 올리거나, 설치값 SELECTION_CHANNEL에 '
                   '같은 세대를 서빙 중인 채널 이름(점검 P01)을 넣으세요.')
    rows = db.query('SELECT '+contract.col('SRCH_CHNL', 'RFRN_POST_HASH_VALU')+' AS Q FROM '+contract.table('SRCH_CHNL')+
                    ' WHERE '+contract.col('SRCH_CHNL', 'RFRN_CHNL_NAME')+'='+literal(channel))
    if len(rows) != 1:
        raise Stop('SELECTION_CHANNEL_MISSING: '+channel)
    body = db.query('SELECT '+contract.col('SRCH_POST', 'RFRN_POST_IFMN_CTNT')+' AS BODY FROM '+contract.table('SRCH_POST')+
                    ' WHERE '+contract.col('SRCH_POST', 'RFRN_POST_HASH_VALU')+'='+literal(rows[0]['Q']))
    if len(body) != 1:
        raise Stop('SELECTION_RELEASE_MISSING: '+rows[0]['Q'])
    selection = json.loads(body[0]['BODY']).get('search_selection')
    if not isinstance(selection, dict) or not selection.get('schema_version'):
        raise Stop('SELECTION_NOT_IN_CHANNEL: '+channel+' 세대에도 판본 선택 정보가 없습니다')
    if not selection_matches(selection, paths):
        raise Stop('SELECTION_OTHER_GENERATION: '+channel+'의 판본 선택은 다른 세대 것입니다. 코드 폴더에 '+SELECTION_FILE+'를 올리세요')
    write_selection(paths, selection)
    return {'source': 'channel', 'channel': channel, 'release': rows[0]['Q'],
            'excluded': len(selection.get('excluded') or [])}


def check(cfg, paths, folders, variables, trial):
    import prod_pipeline as prod
    gold = gold_target(variables)
    config = prod_config(cfg, gold)
    root = target_root(paths, gold)
    prod.fixed(root/'restore.json', prod.base.read(paths/'input.json'))
    report = prod.execute('inspect', config, root)
    from prod_pipeline import Contract, connection
    db = connection(config)
    try:
        contract = Contract(root/'contract.json')
        channels = db.query('SELECT '+contract.col('SRCH_CHNL', 'RFRN_CHNL_NAME')+' AS NAME,'+
                            contract.col('SRCH_CHNL', 'RFRN_POST_HASH_VALU')+' AS RELEASE_ID,'+
                            contract.col('SRCH_CHNL', 'CHAN_NO')+' AS REV FROM '+contract.table('SRCH_CHNL'))
        privs = {r['PRIVILEGE'] for r in db.query('SELECT PRIVILEGE FROM SESSION_PRIVS')}
        user = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS U FROM DUAL")[0]['U']
    finally:
        db.close()
    record = {'status': 'CHECKED', 'gold': gold['GOLD_OWNER']+'.'+(gold['TABLE_PREFIX'] or 'IDD_B003_LGL_')+'*',
              'target': report['target'], 'channels_untouched': channels,
              'stats_privilege': user == gold['GOLD_OWNER'] or 'ANALYZE ANY' in privs}
    if not record['stats_privilege']:
        log('STATS_PRIVILEGE_MISSING', note='04_STATS에서 DBA 요청 문장을 출력합니다. 적재는 진행할 수 있습니다.')
    put(folders['check'], trial+'/check.json', record)
    log('CHECKED', channels=len(channels), stats_privilege=record['stats_privilege'])
    return record


def load(cfg, paths, folders, variables, trial):
    import prod_pipeline as prod
    gold = gold_target(variables)
    config = prod_config(cfg, gold)
    root = target_root(paths, gold)
    prod.base.read(root/'inspect.json')            # 02_CHECK 먼저
    from prod_pipeline import Contract, connection
    db = connection(config)
    try:
        selection = ensure_selection(db, Contract(root/'contract.json'), paths, cfg)
    finally:
        db.close()
    log('SELECTION', **selection)
    for step in ('prepare', 'source', 'search', 'publish', 'vector', 'report'):
        log('LOAD_STEP', step=step, target=gold['GOLD_OWNER'])
        report = prod.execute(step, config, root)
    if not report.get('row_counts_and_publications_verified'):
        raise Stop('TARGET_READBACK_INCOMPLETE')
    record = {'status': 'GOLD_LOADED_NOT_SERVING', 'gold_owner': gold['GOLD_OWNER'], 'table_prefix': gold['TABLE_PREFIX'],
              'channel': report['channel'], 'query_release_id': report['query_release_id'],
              'source_release_id': report['source_release_id'], 'counts': report['counts'],
              'vector_publication_id': report['vector']['publication_id'], 'selection': selection,
              'row_key': 'v2-content', 'serving_switched': False,
              'next': '04_STATS 뒤 시험 서빙 DP_QUERY_CHANNEL='+report['channel']+' 로 비교'}
    put(folders['load'], trial+'/load.json', record)
    log('LOADED', **{k: record[k] for k in ('channel', 'query_release_id', 'counts')})
    return record


def stats(cfg, paths, folders, variables, trial):
    import prod_pipeline as prod
    from gold_io import literal
    gold = gold_target(variables)
    config = prod_config(cfg, gold)
    root = target_root(paths, gold)
    loaded = prod.base.read(root/'report.json')
    from prod_pipeline import Contract, connection
    contract = Contract(root/'contract.json')
    owner = gold['GOLD_OWNER']
    tables = [contract.table(k).split('.', 1)[1] for k in STATS_KEYS]
    db = connection(config)
    try:
        user = db.query("SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS U FROM DUAL")[0]['U']
        privs = {r['PRIVILEGE'] for r in db.query('SELECT PRIVILEGE FROM SESSION_PRIVS')}
        names = ','.join(literal(t) for t in tables)
        before = db.query('SELECT TABLE_NAME,NUM_ROWS,STATTYPE_LOCKED,'
                          "TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED FROM ALL_TAB_STATISTICS "
                          'WHERE OWNER='+literal(owner)+' AND TABLE_NAME IN ('+names+") AND OBJECT_TYPE='TABLE'")
        locked = [r['TABLE_NAME'] for r in before if r['STATTYPE_LOCKED']]
        if locked:
            raise Stop('STATS_LOCKED: '+str(locked)+' — DBA가 잠근 통계입니다')
        statements = ['BEGIN DBMS_STATS.GATHER_TABLE_STATS(ownname=>'+literal(owner)+', tabname=>'+literal(t)+
                      ', cascade=>TRUE, degree=>'+str(int(cfg.get('STATS_DEGREE', 4)))+', no_invalidate=>FALSE); END;'
                      for t in tables]
        if user != owner and 'ANALYZE ANY' not in privs:
            log('PRIVILEGE_REQUIRED', user=user, dba_statements=statements)
            raise Stop('PRIVILEGE_REQUIRED: '+user+' 계정에 ANALYZE ANY가 없습니다. 로그의 dba_statements를 DBA에 요청한 뒤 '
                       '새 세대 채널로 바꾸세요(통계 없이 바꾸면 느린 실행 계획 위험).')
        done = []
        for t, sql in zip(tables, statements):
            started = time.time()
            log('GATHER_START', table=t)
            db.block(sql)
            done.append({'table': t, 'seconds': round(time.time()-started, 1)})
            log('GATHER_DONE', **done[-1])
        after = db.query('SELECT TABLE_NAME,NUM_ROWS,'
                         "TO_CHAR(LAST_ANALYZED,'YYYY-MM-DD HH24:MI:SS') AS LAST_ANALYZED FROM ALL_TAB_STATISTICS "
                         'WHERE OWNER='+literal(owner)+' AND TABLE_NAME IN ('+names+") AND OBJECT_TYPE='TABLE'")
    finally:
        db.close()
    record = {'status': 'STATS_GATHERED', 'channel': loaded['channel'], 'query_release_id': loaded['query_release_id'],
              'tables': done, 'after': after, 'serving_switched': False}
    put(folders['stats'], trial+'/stats.json', record)
    log('STATS_GATHERED', tables=len(done))
    return record


def run(operation, cfg):
    import dataiku
    engine_path()   # 레시피마다 새 프로세스 — 적재 본체(prod_pipeline)가 쓰는 엔진 경로를 먼저 넣는다
    from flow_runtime import trial_paths  # noqa: F401  (같은 묶음 확인용)
    project = dataiku.api_client().get_default_project().project_key
    if cfg['project'] != project:
        raise ValueError('FLOW_PROJECT_MISMATCH')
    variables = dataiku.get_custom_variables()
    trial = variables.get('R8_RELOAD_TRIAL', 'reload-001')
    if not isinstance(trial, str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}', trial):
        raise ValueError('TRIAL_ID_INVALID')
    needed = {'restore': ('input', 'restore'), 'check': ('restore', 'check'),
              'load': ('check', 'load'), 'stats': ('load', 'stats')}[operation]
    ids = dict(cfg['folders'], input=cfg['INPUT_FOLDER_ID'])
    folders = {k: dataiku.Folder(ids[k]) for k in needed}
    paths = Path(cfg['WORK_DIR'])/WORK_NAME/project/trial
    paths.mkdir(parents=True, exist_ok=True, mode=0o700)
    import transport as t
    with t.lock(paths/'flow.lock'):
        result = {'restore': restore, 'check': check, 'load': load, 'stats': stats}[operation](
            cfg, paths, folders, variables, trial)
    log('STEP_DONE', operation=operation, status=result.get('status'))
    return result
