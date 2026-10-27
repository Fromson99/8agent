"""Rebind the sealed ingestion client to the user-confirmed development layers."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent / 'pipeline_mapped_20261023_r1'
DIAGNOSTICS = HERE.parent / 'pipeline_diagnostics_20261023_r2'
sys.path.insert(0, str(ROOT / '02_BACKEND'))
from semantic_runtime.physical_mapping import SchemaMap

CLIENT = 'DATAIKU_PIPELINE_CLIENT_20261027_R1'
RUNNER = 'DATAIKU_PIPELINE_RUN_20261027_R1'
BUNDLE = 'DATAIKU_PIPELINE_LAYERS_20261027_R1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('BASE_CONTEXT_CHANGED: ' + before[:100])
    return source.replace(before, after, 1)


def archive(path, files, prefix):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            item = zipfile.ZipInfo(prefix + '/' + name, date_time=(2026,10,27,0,0,0))
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, raw)


def build():
    old_manifest = json.loads((BASE/'DELIVERY_MANIFEST.json').read_text())
    old_client = BASE/'DATAIKU_PIPELINE_CLIENT_20261023_R1.zip'
    old_raw = old_client.read_bytes()
    assert sha(old_raw) == old_manifest['files'][old_client.name]
    with zipfile.ZipFile(old_client) as z:
        files = {name.split('/',1)[1]:z.read(name) for name in z.namelist()}
    old_pins = json.loads(files['CODE_PINS.json'])['files']
    assert all(sha(files[name]) == digest for name,digest in old_pins.items())
    mapping = yaml.safe_load(files['physical_mapping.yaml'])
    mapping['revision'] = '20261027-dev-sidds-sidda-r1'
    owners = mapping['profiles']['dev_silver']['owner_by_role']
    owners.update(agent='SIDDA', gold_knowledge='SIDDS', gold_support='SIDDS', transfer_archive='SIDDS')
    for key, table in mapping['tables'].items():
        suffix = '_A' if table['role'] == 'agent' else '_S'
        table['name'] += suffix
        table['pk_name'] += suffix
        for group in ('indexes','checks','foreign_keys'):
            for item in table[group]:
                item['name'] += suffix
        target = owners[table['role']] + '.' + table['name']
        table['description'] = table['description'].replace(
            '개발 실버 검증용: AIDP/SIDDA. 골드 표준 승인 미완료.',
            '2026-10-27 사용자 지정 개발계 대상: ' + target +
            '. 앞의 Gold 후보 설명은 운영 설계 이력이며 현재 개발 적재 대상은 이 스키마·접미사를 따른다.')
    yaml_path = HERE/'physical_mapping.yaml'
    yaml_path.write_text(yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False))
    schema = SchemaMap.load(yaml_path)
    targets = {key:schema.names(key).table for key in schema.tables}
    assert all(name.startswith('SIDDS.') and name.endswith('_S') for key,name in targets.items() if key!='query_state')
    assert targets['query_state'] == 'SIDDA.LGL_EXEC_ST_A'
    binding = {'yaml_sha256':schema.file_sha256,'execution_sha256':schema.execution_sha256,
               'target_sha256':schema.target_sha256,'profile':'dev_silver','connection':'AIDP',
               'owners':dict(schema.owners),'targets':targets,'tables':9,'columns':46,
               'user_confirmed_development_layers':True,'production_approved':False}
    write_json(HERE/'MAPPING_BINDING.json',binding)
    header = ('-- 2026-10-27 / AIDP 연결 / SIDDS.*_S 실버, SIDDA.*_A 에이전트\n'
              '-- 기존 무접미사 LGL/LEGAL 테이블은 보존한다. 데이터 복사·삭제·이름 변경 없음.\n'
              '-- 각 SQL 문을 별도 Query에서 실행. 이미 존재하는 객체는 건너뛰고 check로 구조 검사.\n'
              '-- DDL은 자동 커밋. SIDDS/SIDDA 생성 권한이 없으면 해당 스키마 담당자에게 전달.\n'
              '-- 실행 매핑 SHA256: '+schema.execution_sha256+'\n\n')
    query = "SELECT OWNER,OBJECT_NAME,OBJECT_TYPE FROM ALL_OBJECTS WHERE (" + ' OR '.join(
        "(OWNER='"+schema.owners[schema.tables[key]['role']]+"' AND OBJECT_NAME='"+name+"')"
        for _,key,name,_ in schema.ddl()) + ') ORDER BY OWNER,OBJECT_TYPE,OBJECT_NAME;\n'
    (HERE/'00_CHECK_TARGET.sql').write_text(header+
        "SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS LOGIN_USER, SYS_CONTEXT('USERENV','DB_UNIQUE_NAME') AS DB_NAME, SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS CURRENT_SCHEMA_NAME FROM DUAL;\n\n"+query)
    ddl=header
    for i,(_,key,_,sql) in enumerate(schema.ddl(),1):
        ddl+=f'-- {i:02d}. {schema.names(key).table}\n{sql};\n\n'
    (HERE/'01_CREATE_TABLES.sql').write_text(ddl)
    quote=lambda s:"'"+s.replace("'","''")+"'"
    comments=header
    for key,table in schema.tables.items():
        assert len(table['description'].encode())<=4000
        comments+='COMMENT ON TABLE '+schema.names(key).table+' IS '+quote(table['description'])+';\n'
        for column in table['columns'].values():
            assert len(column['description'].encode())<=4000
            comments+='COMMENT ON COLUMN '+schema.names(key).table+'.'+column['name']+' IS '+quote(column['description'])+';\n'
    (HERE/'02_COMMENTS.sql').write_text(comments)
    checks=header+'-- 7개 적재 대상의 전체 행 수 참고용. 실행 성공 판정은 runner의 해당 세대 재조회 결과를 따른다.\n'
    for key in ('document','source_unit','block_payload','asset_part','source_release','query_release','query_row'):
        checks+='SELECT '+quote(schema.names(key).table)+' AS TABLE_NAME, COUNT(*) AS ROW_COUNT FROM '+schema.names(key).table+';\n'
    (HERE/'03_CHECK_LOADED.sql').write_text(checks)
    source=files['dataiku_run.py'].decode()
    source=replace_once(source,"'client_version':'mapped-20261023-r1'","'client_version':'layers-20261027-r1'")
    source=replace_once(source,"'target':'AIDP / SIDDA / dev_silver'","'target':'AIDP / SIDDS.*_S + SIDDA.LGL_EXEC_ST_A / dev_silver'")
    files['dataiku_run.py']=source.encode()
    (HERE/'dataiku_run.py').write_text(source)
    files['physical_mapping.yaml']=yaml_path.read_bytes()
    files['MAPPING_BINDING.json']=(HERE/'MAPPING_BINDING.json').read_bytes()
    files['GUIDE.txt']=(HERE/'GUIDE.txt').read_bytes()
    files.pop('CODE_PINS.json')
    files['CODE_PINS.json']=json.dumps({'files':{name:sha(raw) for name,raw in sorted(files.items())}},indent=2).encode()
    archive(HERE/(CLIENT+'.zip'),files,CLIENT)
    baseline=(DIAGNOSTICS/'DATAIKU_PIPELINE_RUN_20261023_R2.txt').read_bytes()
    diag_pins=json.loads((DIAGNOSTICS/'SHA256.json').read_text())['files']
    assert sha(baseline)==diag_pins['DATAIKU_PIPELINE_RUN_20261023_R2.txt']
    runner=baseline.decode()
    runner=replace_once(runner,'CLIENT_NAME = "DATAIKU_PIPELINE_CLIENT_20261023_R1"','CLIENT_NAME = "'+CLIENT+'"')
    runner=replace_once(runner,'CLIENT_SHA256 = "9d553a32d460b6ddfe4b73a4186dea5501a0b878512ccd622fa7cbae631b9bb3"',
                        'CLIENT_SHA256 = "'+sha((HERE/(CLIENT+'.zip')).read_bytes())+'"')
    runner=replace_once(runner,'CLIENT_BYTES = 224607','CLIENT_BYTES = '+str((HERE/(CLIENT+'.zip')).stat().st_size))
    # This is a new target binding, not a replacement cell for an old unfinished job.
    start=runner.index('_previous_settings = ')
    end=runner.index('\n\nimport fcntl',start)
    runner=runner[:start]+'''ACTION = "prepare"                    # prepare / check / run
FOLDER_NAME = "SET_S3_MANAGED_FOLDER_ID"  # S3 경로가 아니라 관리 폴더 ID
WORK_DIR = "./legal_pipeline_layers_20261027_r1"
JOB_NAME = "layers_20261027_r1"
# 이전 실행의 폴더/작업/예산을 자동 승계하거나 초기화하지 않습니다.
# 기존 원격 작업이 미해제이면 먼저 기존 실행기로 상태를 확인합니다.
'''+runner[end:]
    runner=replace_once(runner,'    work = safe_path(work_dir)',
                        '    if folder_name == "SET_S3_MANAGED_FOLDER_ID" or not folder_name.strip():\n'
                        '        raise RunError("FOLDER_REQUIRED: S3 관리 폴더의 실제 ID를 지정하세요.")\n'
                        '    work = safe_path(work_dir)')
    runner=runner.replace('DATAIKU_PIPELINE_RUN_20261023_R2','DATAIKU_PIPELINE_RUN_20261027_R1')
    runner=runner.replace('Oracle LGL_* 적재·검증','SIDDS.*_S 적재·검증 / SIDDA.*_A 상태 계약 검사')
    compile(runner,RUNNER+'.txt','exec')
    (HERE/(RUNNER+'.txt')).write_text(runner)
    names=[CLIENT+'.zip',RUNNER+'.txt','00_CHECK_TARGET.sql','01_CREATE_TABLES.sql',
           '02_COMMENTS.sql','03_CHECK_LOADED.sql','physical_mapping.yaml','MAPPING_BINDING.json','GUIDE.txt','WORK_CONTRACT.txt']
    for name in ('VALIDATION.json','LOCAL_ORACLE_E2E_RESULT.json'):
        if (HERE/name).exists():names.append(name)
    manifest={'version':'pipeline-layers-20261027-r1','files':{name:sha((HERE/name).read_bytes()) for name in names},
              'base_client_sha256':sha(old_raw),'base_runner_sha256':sha(baseline),
              'service_code_sha256':files['SERVICE_CODE_SHA256.txt'].decode().strip(),
              'targets':targets,'dataiku_connection':'AIDP','genos_worker_changed':False,
              'genos_rag_binding_changed':False,'field_executed':False,'main_changed':False,
              'ontology_shortcut_oracle_load_implemented':False}
    write_json(HERE/'DELIVERY_MANIFEST.json',manifest)
    archive(HERE/(BUNDLE+'.zip'),{name:(HERE/name).read_bytes() for name in names+['DELIVERY_MANIFEST.json']},BUNDLE)
    print(json.dumps({'client_bytes':(HERE/(CLIENT+'.zip')).stat().st_size,'bundle_bytes':(HERE/(BUNDLE+'.zip')).stat().st_size,'targets':targets}))


if __name__=='__main__':
    build()
