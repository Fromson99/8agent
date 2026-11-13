"""R8 재적재 로컬 검증 — 전용 Oracle 컨테이너 + Dataiku 대역(S3 읽기 전용, OBS 쓰기) + 실제 3문서 세대.

전달할 설치 셀(DATAIKU_SETUP_R8_RELOAD_R5.txt)을 그대로 실행하고, 설치된 레시피 코드를 시나리오 순서대로 실행한다.
컨테이너는 이 검증만 쓴다(label a8.task=r8-reload). 끝나면 지운다.
사용: python verify_r8.py <새 출력 폴더>
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import types
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R7 = REPO/'08_DEPLOYMENT/DATAIKU/pipeline_gold_owner_20261112_r1'
GEN = REPO/'09_ARTIFACTS/AUDITS/20261113-r8-row-identity/sample-gen/generation'   # R6 예시 원문을 GENOS 작업자로 구조화한 1문서 세대 + 판본 선택
CONTAINER = 'a8-r8-reload'
LOGICAL = '/nfs-root/diamo/8-agent/term-releases/r8-reload-test/generation'
ARCHIVE = 'r8-test-data.zip'
PART = 49_000_000


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def build_parts(out, folder, *, with_selection):
    """운영 34조각과 같은 형식: 한 루트 아래 DATA_MANIFEST.json + payload/<절대 경로>, GNU sha256sum 파일 2개."""
    sys.path[:0] = [str(out/'pkg/engine/vendor/02_BACKEND')]
    from lawrag.pipeline.oracle_full_package import inventory
    root, paths, info = inventory(GEN)
    files, payload = {}, {}
    for name, path in paths.items():
        if name.startswith('SEARCH_SELECTION/') and not with_selection:
            continue
        logical = (LOGICAL+'/'+name[len('generation/'):]) if name.startswith('generation/') else \
            str(Path(LOGICAL).parent/'SEARCH_SELECTION'/(Path(LOGICAL).name+'.json'))
        files[logical] = {'kind': 'file', 'bytes': info['files'][name]['bytes'], 'sha256': info['files'][name]['sha256']}
        payload[logical] = path
    meta = {'schema_version': 'genos-rag-data-path-preserving-v1', 'archive_restore_eligible': True,
            'generation': LOGICAL, 'generation_manifest_sha256': info['dataset_version'], 'files': files}
    folder.mkdir(parents=True)
    archive = out/('work-'+folder.name+'.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('genos-rag-data-test/DATA_MANIFEST.json', json.dumps(meta, sort_keys=True))
        for logical, path in payload.items():
            z.write(path, 'genos-rag-data-test/payload'+logical)
    whole = sha_file(archive)
    parts = []
    with archive.open('rb') as src:
        while block := src.read(PART):
            name = ARCHIVE+f'.part{len(parts):06d}'
            (folder/name).write_bytes(block)
            parts.append((name, hashlib.sha256(block).hexdigest()))
    (folder/'ORIGINAL.sha256').write_text(whole+'  '+ARCHIVE+'\n')
    (folder/'PARTS.sha256').write_text(''.join(s+'  '+n+'\n' for n, s in parts))
    archive.unlink()
    return {'parts': len(parts), 'archive_sha256': whole, 'selection': with_selection}


def main(out):
    import oracledb
    import pandas as pd
    oracledb.defaults.fetch_lobs = False
    info = json.loads(subprocess.check_output(['docker', 'inspect', CONTAINER]))[0]
    assert info['Config']['Labels'].get('a8.task') == 'r8-reload'
    port = info['NetworkSettings']['Ports']['1521/tcp'][0]
    assert port['HostIp'] == '127.0.0.1'
    dsn = '127.0.0.1:'+port['HostPort']+'/FREEPDB1'
    pw = dict(v.split('=', 1) for v in info['Config']['Env'])['ORACLE_PASSWORD']
    admin = oracledb.connect(user='system', password=pw, dsn=dsn)
    out.mkdir(parents=True)
    checks, diag = [], {}
    with zipfile.ZipFile(HERE/'DATAIKU_ZIP_R8_RELOAD_R5.zip') as z:
        z.extractall(out/'pkg')
    storage = out/'storage'
    parts_a = build_parts(out, storage/'s3in', with_selection=True)
    parts_b = build_parts(out, storage/'s3in-nosel', with_selection=False)
    diag['parts'] = {'with_selection': parts_a, 'without_selection': parts_b}
    checks.append('archive_parts_built_from_declared_generation_files')

    secret = 'R8test_'+hashlib.sha256(os.urandom(8)).hexdigest()[:12]
    with admin.cursor() as c:
        for user in ('SIDDS', 'PIDD2APP'):   # 이 검증 전용 컨테이너 — 이전 시험 계정만 지운다
            if c.execute('SELECT COUNT(*) FROM ALL_USERS WHERE USERNAME=:u', u=user).fetchone()[0]:
                c.execute('DROP USER '+user+' CASCADE')
        for user in ('SIDDS', 'PIDD2APP'):
            c.execute(f'CREATE USER {user} IDENTIFIED BY "{secret}" DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS')
            c.execute('GRANT CREATE SESSION TO '+user)
        text = (R7/'CREATE_GOLD_TABLES_SIDDG_R1.txt').read_text()
        ddl = [b.split('\n', 1)[1].strip().replace('SIDDG.', 'SIDDS.') for b in text.split('-- [')[1:]]
        for stmt in ddl:
            c.execute(stmt)
        tables = [r[0] for r in c.execute("SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER='SIDDS'")]
        assert len(tables) == 13, tables
        for t in tables:
            c.execute('GRANT SELECT, INSERT ON SIDDS.'+t+' TO PIDD2APP')
        # 지금 서빙 중인 채널 흉내 — 재적재 뒤에도 그대로여야 한다.
        c.execute("INSERT INTO SIDDS.IDD_B003_LGL_SRCH_CHNL (RFRN_CHNL_NAME,RFRN_POST_HASH_VALU,CHAN_NO) "
                  "VALUES ('main','"+'0'*64+"',7)")
        admin.commit()
    checks.append('delivered_CREATE_GOLD_DDL_13_tables_select_insert_only')

    def login():
        return oracledb.connect(user='PIDD2APP', password=secret, dsn=dsn)

    class Executor:
        def __init__(self, connection):
            assert connection == 'AIDP'

        def query_to_df(self, query, pre_queries=(), post_queries=(), **kw):
            with login() as conn, conn.cursor() as c:
                for item in pre_queries:
                    c.execute(item)
                c.execute(query)
                frame = pd.DataFrame(c.fetchall(), columns=[d[0] for d in c.description])
                for item in post_queries:
                    c.execute(item)
                return frame

    embed_calls = []

    class Embed:
        def __init__(self):
            self.texts = []

        def add_text(self, t):
            self.texts.append(t)

        def execute(self):
            embed_calls.append(len(self.texts))
            return types.SimpleNamespace(get_embeddings=lambda: [[1.0]+[0.0]*1023 for _ in self.texts])

    writes = []

    OBS_BUCKET = 'AIDP-YNY-DEV-BUC-SRI'      # 현장 확인 셀: 코드 폴더·조각 폴더 둘 다 이 버킷
    WRITABLE = '/dataiku/'                    # 현장: 화면으로 만든 폴더(/dataiku/...)만 쓰기 됨, 코드로 만든 폴더(/LEGAL_RAG_R8/...)는 404

    def denied(bucket):
        return RuntimeError("NoSuchBucketException: Either the bucket named '"+bucket+"' does not exist in the "
                            "namespace 'axuwokij1bcw' or you are not authorized to access it (Service: S3, Status Code: 404)")

    class Folder:
        """현장처럼 S3형 연결 두 개: OBS(버킷 하나, /dataiku/ 밑에만 쓰기)·S3(읽기만). 목록 읽기는 어디서나 된다.
        dataikuapi create_managed_folder로 만든 폴더는 path가 /${projectKey}/${odbId}(접두어 없음)."""
        def __init__(self, ref, raw=None):
            self.id = self.name = ref
            self.type = 'S3'
            self.raw = raw or {'connection': 'obs', 'path': '/${projectKey}/${odbId}'}
            self.saves = 0

        @property
        def connection(self): return self.raw['connection']
        def bucket(self): return self.raw.get('bucket') or (OBS_BUCKET if self.connection == 'obs' else 'S3-READ-BUCKET')
        def root(self):
            return '/'+self.raw['path'].replace('${projectKey}', 'LOCAL_TEST').replace('${odbId}', self.id).strip('/')

        @property
        def path(self):
            target = storage/self.bucket()/self.root().lstrip('/')
            target.mkdir(parents=True, exist_ok=True)
            return target

        def get_settings(self): return self
        def get_raw_params(self): return self.raw
        def save(self): self.saves += 1
        def move_to_zone(self, z): pass
        def get_info(self, sensitive_info=False):
            return {'type': 'S3', 'accessInfo': {'bucket': self.bucket(), 'root': self.root()}}

        def write_check(self, p):
            if self.connection != 'obs':
                raise PermissionError('S3_WRITE_ATTEMPT:'+self.id+':'+p)
            if not self.root().startswith(WRITABLE):
                raise denied(self.bucket())

        def list_paths_in_partition(self):
            return sorted('/'+str(p.relative_to(self.path)) for p in self.path.rglob('*') if p.is_file())

        def get_download_stream(self, p):
            return (self.path/p.lstrip('/')).open('rb')

        def upload_data(self, p, data):
            self.write_check(p)
            target = self.path/p.lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            writes.append((self.id, p))

        def upload_stream(self, p, stream):
            self.upload_data(p, stream.read())

        def delete_path(self, p):
            self.write_check(p)
            (self.path/p.lstrip('/')).unlink()

    folders, recipes, scenarios = {}, {}, {}

    def folder(ref, raw=None):
        folders.setdefault(ref, Folder(ref, raw))
        return folders[ref]

    class Recipe:
        def __init__(self, name):
            self.name, self.ins, self.outs, self.code = name, [], [], None
        def with_input(self, x): self.ins.append(x); return self
        def with_output(self, x, append): assert append; self.outs.append(x); return self
        def with_script(self, code): self.code = code; return self
        def create(self): recipes[self.name] = self; return self
        def get_settings(self): return self
        def set_code_env(self, inherit): assert inherit
        def save(self): pass
        def get_code(self): return self.code
        def set_code(self, code): self.code = code
        def get_flat_input_refs(self): return self.ins
        def get_flat_output_refs(self): return self.outs
        def move_to_zone(self, z): pass

    class Scenario:
        def __init__(self, name): self.name, self.code, self.active = name, None, True
        def get_settings(self): return self
        def save(self): pass

    def create_folder(name, folder_type, connection_name):
        assert connection_name == 'obs', connection_name
        assert name not in folders
        return folder(name, {'connection': connection_name, 'path': '/${projectKey}/${odbId}'})   # dataikuapi와 같은 값

    def create_scenario(name, kind):
        scenarios[name] = Scenario(name)
        return scenarios[name]

    zones = {}
    project = types.SimpleNamespace(
        project_key='LOCAL_TEST', get_managed_folder=folder,
        get_flow=lambda: types.SimpleNamespace(list_zones=lambda: list(zones.values()),
                                               create_zone=lambda n: zones.setdefault(n, types.SimpleNamespace(name=n))),
        list_managed_folders=lambda: [{'name': n, 'id': n} for n in folders],
        create_managed_folder=create_folder, new_recipe=lambda kind, n: Recipe(n),
        list_recipes=lambda: [{'name': n} for n in recipes], get_recipe=recipes.__getitem__,
        list_scenarios=lambda: [{'name': n, 'id': n} for n in scenarios], get_scenario=scenarios.__getitem__,
        create_scenario=create_scenario,
        get_llm=lambda name: types.SimpleNamespace(new_embeddings=lambda **kw: Embed()))
    variables = {'AGENT_FLOW_WORK_DIR': str(out/'work')}
    dku = types.ModuleType('dataiku')
    dku.Folder = lambda ref, ignore_flow=False: folder(ref)
    dku.SQLExecutor2 = Executor
    dku.get_custom_variables = lambda: variables
    dku.api_client = lambda: types.SimpleNamespace(get_default_project=lambda: project, get_project=lambda k: project)
    sys.modules['dataiku'] = dku
    # 빈 새 프로젝트: 사용자가 만든 OBS 폴더 LGL_R8_CODE(코드 ZIP)뿐. S3 대역 폴더 2개는 S3 입력 경로 시험용.
    folder('LGL_R8_CODE', {'connection': 'obs', 'path': '/dataiku/${projectKey}/${odbId}'})   # 화면으로 만든 폴더
    for ref in ('s3in', 's3in-nosel'):
        old_path = storage/ref
        f = folder(ref, {'connection': 's3-readonly', 'bucket': 'S3-READ-BUCKET', 'path': '/${projectKey}/${odbId}'})
        for item in old_path.iterdir():
            shutil.move(str(item), str(f.path/item.name))
        old_path.rmdir()
    shutil.copyfile(HERE/'DATAIKU_ZIP_R8_RELOAD_R5.zip', folder('LGL_R8_CODE').path/'DATAIKU_ZIP_R8_RELOAD_R5.zip')

    alive = []

    def fresh_process():
        """실제 Dataiku는 레시피마다 새 프로세스 — 앞 레시피가 푼 코드 모듈·경로를 비운다."""
        roots = [str(Path(ns['_code_dir'].name)) for ns in alive if '_code_dir' in ns]
        for name, module in list(sys.modules.items()):
            f = getattr(module, '__file__', None) or ''
            if 'agent-flow-code-' in f:
                del sys.modules[name]
        sys.path[:] = [x for x in sys.path if 'agent-flow-code-' not in x]

    setup = (HERE/'DATAIKU_SETUP_R8_RELOAD_R5.txt').read_text()

    def install(input_folder, write_folder, selection_channel, parts, cell=None, fresh=True):
        text = (cell or setup).replace('"INPUT_FOLDER_ID": "LGL_R8_PARTS"', '"INPUT_FOLDER_ID": "'+input_folder+'"')
        text = text.replace('"WRITE_FOLDER_ID": ""', '"WRITE_FOLDER_ID": "'+write_folder+'"')
        text = text.replace('"EXPECTED_ARCHIVE": "genos-rag-data-20261007T002029Z-7c0b050f.zip"', '"EXPECTED_ARCHIVE": "'+ARCHIVE+'"')
        text = text.replace('"EXPECTED_PARTS": 34', '"EXPECTED_PARTS": '+str(parts))
        text = text.replace('"SELECTION_CHANNEL": ""', '"SELECTION_CHANNEL": "'+selection_channel+'"')
        ns = {}
        if fresh:                      # fresh=False: 같은 노트북 커널에서 이어서 실행(현장 R4 때처럼)
            fresh_process()
        alive.append(ns)
        exec(compile(text, 'setup-cell', 'exec'), ns)
        return ns['cfg']

    try:
        install('LGL_R8_PARTS', '', '', parts_a['parts'])
    except ValueError as exc:
        assert str(exc).startswith('LGL_GOLD_OWNER_REQUIRED'), exc
        assert 'LGL_R8_PARTS' not in folders
    else:
        raise AssertionError('설치가 LGL_GOLD_OWNER 없이 진행됨')
    checks.append('install_refused_without_LGL_GOLD_OWNER')
    variables['LGL_GOLD_OWNER'] = 'SIDDS'
    try:
        install('s3in', 's3in', '', parts_a['parts'])
    except ValueError as exc:
        assert str(exc).startswith('WRITE_FOLDER_IS_INPUT_FOLDER'), exc
    else:
        raise AssertionError('입력 폴더를 쓰기 폴더로 받아들임')
    assert not recipes
    checks.append('install_refuses_input_folder_as_write_folder')
    def write_ok(ref):
        """쓰기·지우기를 해 보고 결과만 돌려준다(파일은 남기지 않음)."""
        try:
            folders[ref].upload_data('/.verify_probe', b'x')
        except RuntimeError as exc:
            assert 'AIDP-YNY-DEV-BUC-SRI' in str(exc) and 'Status Code: 404' in str(exc), exc
            return False
        folders[ref].delete_path('/.verify_probe')
        return True

    rule = '/dataiku/${projectKey}/${odbId}'
    # 현장 재현 1: 보낸 R3 셀 → 코드로 만든 폴더 5개는 경로에 /dataiku/가 없어 목록은 읽히고 쓰기는 404 (11-13 확인 셀 결과)
    shutil.copyfile(HERE/'local_checks/r3/DATAIKU_ZIP_R8_RELOAD.zip', folder('LGL_R8_CODE').path/'DATAIKU_ZIP_R8_RELOAD.zip')
    cfg_r3 = install('LGL_R8_PARTS', '', '', parts_a['parts'], cell=(HERE/'local_checks/r3/DATAIKU_SETUP_R8_RELOAD.txt').read_text())
    broken = ['LGL_R8_PARTS', *cfg_r3['folders'].values()]
    for ref in broken:
        assert folders[ref].list_paths_in_partition() == [] and not write_ok(ref), ref
        assert folders[ref].root() == '/LOCAL_TEST/'+ref and folder('LGL_R8_CODE').root() == '/dataiku/LOCAL_TEST/LGL_R8_CODE'
    checks.append('R3_cell_folders_list_ok_but_write_404_same_bucket_like_field')
    # 현장 재현 2: 보낸 R4 셀(커널 재시작 뒤) → 목록이 읽혀 폴더를 고치지 않음(버킷 맞춤 없음), 레시피만 R4 → 업로드 여전히 404
    shutil.copyfile(HERE/'local_checks/r4/DATAIKU_ZIP_R8_RELOAD_R4.zip', folder('LGL_R8_CODE').path/'DATAIKU_ZIP_R8_RELOAD_R4.zip')
    cfg_r4 = install('LGL_R8_PARTS', '', '', parts_a['parts'], cell=(HERE/'local_checks/r4/DATAIKU_SETUP_R8_RELOAD_R4.txt').read_text())
    assert cfg_r4['folders'] == cfg_r3['folders']
    assert all(folders[r].saves == 0 and not write_ok(r) for r in broken)
    assert all('DATAIKU_ZIP_R8_RELOAD_R4.zip' in r.code for r in recipes.values()) and len(recipes) == 4
    stale = sys.modules['reload_install'].__file__
    checks.append('R4_cell_reproduces_field_no_fix_upload_still_404')
    # R5 셀을 같은 커널에서(재시작 없이) → 이전 판 모듈을 지우고 R5로: 폴더 5개 경로를 /dataiku/로, 쓰기 확인, 레시피 R5로
    cfg = install('LGL_R8_PARTS', '', '', parts_a['parts'], fresh=False)
    current = sys.modules['reload_install'].__file__
    assert current != stale and 'agent-flow-code-' in current and 'FOLDER_PATH' in cfg
    assert cfg['folders'] == cfg_r3['folders'] and cfg['CODE_FOLDER_ID'] == 'LGL_R8_CODE' and cfg['WRITE_FOLDER_ID'] == 'LGL_R8_CODE'
    for ref in broken:
        assert folders[ref].raw['path'] == rule and folders[ref].saves == 1 and write_ok(ref), ref
        assert folders[ref].list_paths_in_partition() == []          # 쓰기 확인 파일은 남지 않음
    assert all('DATAIKU_ZIP_R8_RELOAD_R5.zip' in r.code for r in recipes.values()) and len(recipes) == 4
    checks.append('R5_cell_same_kernel_drops_old_modules_fixes_5_folder_paths_writes_ok_updates_recipes')
    again = install('LGL_R8_PARTS', '', '', parts_a['parts'], fresh=False)
    assert again == cfg and len(recipes) == 4 and len(scenarios) == 1
    assert all(folders[r].saves == 1 for r in broken)     # 두 번째 설치는 폴더 설정을 다시 저장하지 않음
    for f in sorted(folders['s3in'].path.iterdir()):     # 사용자가 조각을 LGL_R8_PARTS 에 올림(쓰기 규칙 적용)
        with f.open('rb') as src:
            folder('LGL_R8_PARTS').upload_stream(f.name, src)
    assert sorted(recipes) == ['LGL_R8_RELOAD_01_RESTORE', 'LGL_R8_RELOAD_02_CHECK', 'LGL_R8_RELOAD_03_LOAD', 'LGL_R8_RELOAD_04_STATS']
    assert all(folders[f].connection == 'obs' for f in cfg['folders'].values())
    scenario = next(iter(scenarios.values()))
    assert not scenario.active and scenario.code.count('build_folder(') == 4
    assert not any('SIDDS' in r.code for r in recipes.values())
    checks.append('exact_setup_cell_installs_4_recipes_disabled_scenario_outputs_on_OBS_repeatable')

    def run_scenario(names, *, expect_stop=None):
        for name in names:
            started = time.time()
            ns = {}
            fresh_process()
            alive.append(ns)
            try:
                exec(compile(recipes[name].code, name, 'exec'), ns)
            except Exception as exc:
                if expect_stop and str(exc).startswith(expect_stop):
                    diag.setdefault('stops', []).append({'recipe': name, 'stop': str(exc)[:300]})
                    return 'STOPPED'
                raise
            diag.setdefault('seconds', {})[name] = round(time.time()-started, 1)
        return 'DONE'

    order = sorted(recipes)
    assert run_scenario(order[:3]) == 'DONE'
    with admin.cursor() as c:
        main = c.execute("SELECT RFRN_POST_HASH_VALU,CHAN_NO FROM SIDDS.IDD_B003_LGL_SRCH_CHNL WHERE RFRN_CHNL_NAME='main'").fetchall()
    assert main == [('0'*64, 7)]
    checks.append('existing_main_channel_untouched_after_load')
    loaded = json.loads((folder(cfg['folders']['load']).path/'reload-001/load.json').read_text())
    diag['loaded'] = loaded
    assert loaded['status'] == 'GOLD_LOADED_NOT_SERVING' and loaded['channel'].startswith('g19_')
    assert loaded['selection'] == {'source': 'archive'}
    assert embed_calls, 'vector stage did not embed'
    checks.append('restore_check_load_GOLD_rows_and_publications_verified_by_loader_readback')

    # 통계: 권한 없으면 멈추고 DBA 문장 출력 → 권한 받은 뒤 다시 실행.
    assert run_scenario([order[3]], expect_stop='PRIVILEGE_REQUIRED') == 'STOPPED'
    with admin.cursor() as c:
        c.execute('GRANT ANALYZE ANY TO PIDD2APP')
    assert run_scenario([order[3]]) == 'DONE'
    stats = json.loads((folder(cfg['folders']['stats']).path/'reload-001/stats.json').read_text())
    assert stats['status'] == 'STATS_GATHERED' and len(stats['tables']) == 10
    checks.append('stats_stop_with_DBA_statements_then_gather_after_grant')

    # 행 번호가 내용 기준인지: 같은 종류 안 번호가 모두 다르고 행 수가 명세와 같다(적재기 대조) + 명세에 v2 표시.
    with admin.cursor() as c:
        body = c.execute('SELECT RFRN_POST_IFMN_CTNT FROM SIDDS.IDD_B003_LGL_SRCH_POST WHERE RFRN_POST_HASH_VALU=:q',
                         q=loaded['query_release_id']).fetchone()[0]
        kinds = dict(c.execute('SELECT RFRN_DTA_TYPE_VALU,COUNT(*) FROM SIDDS.IDD_B003_LGL_SRCH_ROW '
                               'WHERE RFRN_POST_HASH_VALU=:q GROUP BY RFRN_DTA_TYPE_VALU', q=loaded['query_release_id']).fetchall())
    manifest = json.loads(body)
    assert manifest['gold_projection']['version'] == 'gold-zip-flow-full-v2-content-rows'
    assert {k: t['rows'] for k, t in manifest['tables'].items() if t['rows']} == kinds
    assert manifest['search_selection'] and manifest['search_selection']['schema_version']
    diag['kinds'] = kinds
    checks.append('content_row_keys_unique_per_kind_counts_equal_manifest_selection_present')

    # 선택 정보 없는 ZIP + 채널에서 가져오기 → 같은 세대 번호(이미 적재됨이므로 적재 전 정지).
    variables['R8_RELOAD_TRIAL'] = 'reload-nosel'
    try:
        install('s3in-nosel', '', '', parts_b['parts'])
    except ValueError as exc:
        assert str(exc).startswith('RECIPE_CONFLICT'), exc
        checks.append('changed_install_values_refused_on_existing_recipes')
    for r in list(recipes):
        del recipes[r]
    for s in list(scenarios):
        del scenarios[s]
    cfg2 = install('s3in-nosel', '', '', parts_b['parts'])
    assert run_scenario(sorted(recipes)[:2]) == 'DONE'
    try:
        run_scenario([sorted(recipes)[2]])
    except Exception as exc:
        assert str(exc).startswith('SEARCH_SELECTION_REQUIRED'), exc
    else:
        raise AssertionError('선택 정보 없이 적재 진행')
    # 코드 폴더(OBS)에 올린 선택 파일 — 다른 세대 것이면 멈춤, 같은 세대 것이면 같은 세대 번호.
    selection_source = GEN.parent/'SEARCH_SELECTION'/(GEN.name+'.json')
    other = json.loads(selection_source.read_text()); other['store_sha256'] = 'f'*64
    (folder('LGL_R8_CODE').path/'SEARCH_SELECTION_GENERATION.json').write_text(json.dumps(other))
    try:
        run_scenario([sorted(recipes)[2]])
    except Exception as exc:
        assert str(exc).startswith('SELECTION_FILE_OTHER_GENERATION'), exc
    else:
        raise AssertionError('다른 세대 선택 파일을 받아들임')
    shutil.copyfile(selection_source, folder('LGL_R8_CODE').path/'SEARCH_SELECTION_GENERATION.json')
    try:
        run_scenario([sorted(recipes)[2]])
    except Exception as exc:
        assert 'EXISTING_RELEASE_REQUIRES_ORIGINAL_CHECKPOINT' in str(exc), exc
    else:
        raise AssertionError('같은 세대를 다시 적재함')
    prepared = json.loads((out/'work/r8-reload/LOCAL_TEST/reload-nosel/target-SIDDS-IDD_B003_LGL_/prepared.json').read_text())
    sys.path.insert(0, str(out/'pkg/engine'))
    from gold_io import digest
    assert digest(prepared['query']) == loaded['query_release_id'], 'file selection made a different release'
    checks.append('selection_file_on_OBS_other_generation_refused_same_generation_same_release')
    (folder('LGL_R8_CODE').path/'SEARCH_SELECTION_GENERATION.json').unlink()
    # 채널에서 가져오기 — 새 trial
    variables['R8_RELOAD_TRIAL'] = 'reload-chan'
    for r in list(recipes):
        del recipes[r]
    for s in list(scenarios):
        del scenarios[s]
    cfg2 = install('s3in-nosel', '', loaded['channel'], parts_b['parts'])
    assert run_scenario(sorted(recipes)[:2]) == 'DONE'
    try:
        run_scenario([sorted(recipes)[2]])
    except Exception as exc:
        assert 'EXISTING_RELEASE_REQUIRES_ORIGINAL_CHECKPOINT' in str(exc), exc
    else:
        raise AssertionError('같은 세대를 다시 적재함')
    prepared = json.loads((out/'work/r8-reload/LOCAL_TEST/reload-chan/target-SIDDS-IDD_B003_LGL_/prepared.json').read_text())
    assert digest(prepared['query']) == loaded['query_release_id'], 'channel selection made a different release'
    assert digest(prepared['source']) == loaded['source_release_id']
    with admin.cursor() as c:
        n = c.execute('SELECT COUNT(*) FROM SIDDS.IDD_B003_LGL_SRCH_POST').fetchone()[0]
    assert n == 1
    checks.append('missing_selection_stops_then_copied_from_channel_same_release_no_duplicate_load')

    # 이미 S3(읽기 전용)에 있는 조각을 그대로 입력으로 — 설치·복원·점검이 되고 S3에는 쓰지 않는다.
    variables['R8_RELOAD_TRIAL'] = 'reload-s3'
    for r in list(recipes):
        del recipes[r]
    for s_ in list(scenarios):
        del scenarios[s_]
    before = sorted(p.name for p in folders['s3in'].path.iterdir())
    cfg3 = install('s3in', '', '', parts_a['parts'])
    assert folders['s3in'].connection == 's3-readonly' and all(folders[f].connection == 'obs' for f in cfg3['folders'].values())
    assert run_scenario(sorted(recipes)[:2]) == 'DONE'
    try:
        run_scenario([sorted(recipes)[2]])
    except Exception as exc:
        assert 'EXISTING_RELEASE_REQUIRES_ORIGINAL_CHECKPOINT' in str(exc), exc
    else:
        raise AssertionError('같은 세대를 다시 적재함')
    assert sorted(p.name for p in folders['s3in'].path.iterdir()) == before
    checks.append('existing_parts_on_readonly_S3_input_install_restore_check_ok')
    variables['R8_RELOAD_TRIAL'] = 'reload-new'
    for r in list(recipes):
        del recipes[r]
    for s_ in list(scenarios):
        del scenarios[s_]
    install('LGL_R8_PARTS_NEW', '', '', parts_a['parts'])
    new = folders['LGL_R8_PARTS_NEW']
    assert new.raw['path'] == rule and new.saves == 1 and new.list_paths_in_partition() == [] and write_ok('LGL_R8_PARTS_NEW')
    checks.append('R5_new_parts_folder_created_with_code_folder_path_and_writable')
    assert not list(folders['s3in'].path.glob('**/*receipt*')) and all(w[0] != 's3in' for w in writes)
    s3_files = sorted(p.name for p in folders['s3in'].path.iterdir())
    assert s3_files == sorted(['ORIGINAL.sha256', 'PARTS.sha256'] + [ARCHIVE+f'.part{i:06d}' for i in range(parts_a['parts'])])
    assert not list(storage.rglob('.lgl_r8_write_check'))
    checks.append('S3_input_never_written_receipts_only_on_OBS_no_probe_left')
    diag['writes'] = sorted(set(w[1] for w in writes))
    diag['embedding_calls'] = len(embed_calls)
    result = {'status': 'PASS', 'checks': checks, 'diagnostics': diag}
    (out/'verify_r8.json').write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({'status': 'PASS', 'checks': len(checks)}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    main(p.parse_args().output.resolve())
