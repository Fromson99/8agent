"""Production configuration and storage checks; no retries or DSS creation."""
import io
import uuid
from prod_config import validate


def check(params, project):
    validate(params)
    if not isinstance(project,str) or not project:
        raise ValueError('CURRENT_DATAIKU_PROJECT_REQUIRED')
    if params['TARGET_MODE']!='GOLD' or params['EXPECTED_PARTS']!=34:
        raise ValueError('PRODUCTION_GOLD_34_PARTS_REQUIRED')
    if not isinstance(params['TABLE_NAMES'],dict):raise ValueError('TABLE_NAMES_MUST_BE_DICT')
    for name in ('CODE_FOLDER_ID','INPUT_FOLDER_ID','ORACLE_CONNECTION','GOLD_OWNER','EXPECTED_DB_USER','EMBED_MODEL'):
        if params[name]!=params[name].strip():raise ValueError('REMOVE_OUTER_SPACES:'+name)


def probe(folder, label):
    path='_connection_checks/'+uuid.uuid4().hex+'.txt'
    raw=('Gold production storage check: '+label).encode()
    try:
        folder.list_paths_in_partition()
        folder.upload_stream(path,io.BytesIO(raw))
        with folder.get_download_stream(path) as stream:
            if stream.read(len(raw)+1)!=raw:raise ValueError('READBACK_MISMATCH')
    except Exception as exc:
        raise RuntimeError('STORAGE_CHECK_FAILED:'+label+
            ' — 이 Managed Folder의 실제 버킷·namespace·읽기/쓰기 권한을 확인하세요. Oracle 적재 전 중단했습니다.') from exc


def failure_hint(exc):
    text=str(exc)
    if 'ORA-01031' in text or 'ORA-00942' in text:
        return 'ORACLE 권한/대상 확인: 접속 계정과 GOLD_OWNER는 다릅니다. 등록된 대상 테이블의 SELECT·INSERT 권한을 확인하세요. 이 실행기는 테이블을 생성하지 않습니다.'
    if 'RESUME_TABLE_MISSING' in text or 'RESUME_INDEX_MISSING' in text:
        return '운영 테이블/인덱스가 없거나 접속 계정에서 보이지 않습니다. 등록명·owner·권한을 확인하세요. 자동 생성하지 않습니다.'
    if 'CHECKPOINT' in text or 'EXISTING_RELEASE' in text:
        return '기존 WORK_DIR와 해당 실행 기록을 보존·복구하세요. 상태를 지우거나 새 폴더 ID로 중복 실행하지 마세요.'
    if 'EMBEDDING_OUTCOME_UNKNOWN' in text:
        return '임베딩 응답이 불명확합니다. 자동 재호출하지 않습니다. 보존된 로그·캐시·pending 기록으로 확인하세요.'
    return '원래 오류와 전체 로그를 확인하세요. 설정과 체크포인트를 보존했으며 자동 재실행하지 않습니다.'
