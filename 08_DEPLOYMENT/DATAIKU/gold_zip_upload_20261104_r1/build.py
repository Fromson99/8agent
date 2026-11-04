"""Make a notebook entry point for the existing, unchanged Gold ZIP Flow."""
import ast
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'gold_zip_flow_20261104_r1'
ZIP_NAME = 'DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip'

SETTINGS = '''# LEGAL_RAG 프로젝트 > Notebooks > 새 Python 노트북 > 셀 하나에 전체 붙여넣기
# 코드 ZIP과 데이터 조각34개 + SHA파일2개를 ehA8dpVm 루트에 업로드합니다.
# 이 셀은 Flow를 설치하고 시나리오를 한 번 시작합니다. 완료는 Scenario 실행 결과로 확인합니다.
EXPECTED_PROJECT = 'LEGAL_RAG'
PARAMS = {
    'CODE_FOLDER_ID': 'ehA8dpVm',
    'INPUT_FOLDER_ID': 'ehA8dpVm',  # 데이터가 다른 폴더에 있으면 그 폴더 ID만 입력
    'ORACLE_CONNECTION': 'AIDP',
    'EXPECTED_DB_USER': 'PIDD2APP',
    'TARGET_MODE': 'GOLD',
    'GOLD_OWNER': '',              # 필수: IDD_B003_LGL_* 테이블의 실제 소유 스키마명
    'TABLE_PREFIX': 'IDD_B003_LGL_',
    'TABLE_NAMES': {},
    'WORK_DIR': '',                # 권장: 모든 레시피가 공유하는 영속 Linux 절대경로
    'EMBED_MODEL': 'openai:genos-embedding:embedding-kure-v1',
    'EMBED_DIMENSIONS': 1024,
    'ACTIVATE_NEW_VECTOR_HEAD': True,
    'EXPECTED_ARCHIVE': 'genos-rag-data-20261007T002029Z-7c0b050f.zip',
    'EXPECTED_PARTS': 34,
    'ORIGINAL_SHA_FILE': '',
    'PARTS_SHA_FILE': '',
    'RUN_AFTER_INSTALL': True,     # False이면 Flow 생성까지만 실행
}
'''

PREFLIGHT = r'''
import re
import sys
from pathlib import Path
import dataiku

def check_upload_settings(params, expected_project):
    project = dataiku.api_client().get_default_project()
    if project.project_key != expected_project:
        raise ValueError('프로젝트 불일치: 현재=' + project.project_key + ', 지정=' + expected_project)
    if not params['GOLD_OWNER']:
        raise ValueError('GOLD_OWNER에 실제 Gold 테이블의 소유 스키마명을 입력하세요. 접속 계정과 다를 수 있습니다.')
    if params['WORK_DIR'] and not Path(params['WORK_DIR']).is_absolute():
        raise ValueError('WORK_DIR는 모든 레시피가 공유하는 Linux 절대경로여야 합니다.')
    if not params['INPUT_FOLDER_ID']:
        raise ValueError('INPUT_FOLDER_ID에 데이터 조각을 업로드한 Managed Folder ID를 입력하세요.')
    folder = dataiku.Folder(params['INPUT_FOLDER_ID'])
    names = [p[1:] if p.startswith('/') else p for p in folder.list_paths_in_partition()]
    if len(names) != len(set(names)):
        raise ValueError('업로드 목록에 중복 경로가 있습니다.')
    expected = {params['EXPECTED_ARCHIVE'] + '.part%06d' % i for i in range(params['EXPECTED_PARTS'])}
    missing = sorted(expected - set(names))
    extra = sorted(n for n in names if n.startswith(params['EXPECTED_ARCHIVE'] + '.part') and n not in expected)
    if missing or extra:
        if params['EXPECTED_ARCHIVE'] in names and missing:
            raise ValueError('이 실행문은 발송한 34조각용입니다. 통합 ZIP 한 개만으로는 실행하지 않습니다. 기존 part000000~part000033과 SHA파일2개를 올리세요.')
        raise ValueError('데이터 폴더 ' + params['INPUT_FOLDER_ID'] + '의 루트에 파일을 확인하세요. 누락=' + str(missing) + ', 추가조각=' + str(extra))
    for key, stem in [('ORIGINAL_SHA_FILE', 'ORIGINAL'), ('PARTS_SHA_FILE', 'PARTS')]:
        explicit = params.get(key, '')
        matches = [explicit] if explicit else [n for n in names if re.fullmatch(stem + r'(?: \([0-9]+\))?\.sha256', n)]
        if not matches or any(n not in names for n in matches):
            raise ValueError('데이터 폴더에 ' + stem + '.sha256를 업로드하세요.')
    print('업로드 목록 확인:', params['INPUT_FOLDER_ID'], '/', len(expected), '조각 + SHA파일2종')
    print('내용 해시는 시나리오의 ZIP 병합 단계에서 검증합니다.')
    if not params['WORK_DIR']:
        print('WORK_DIR 미지정: 같은 DSS 호스트의 /tmp를 사용합니다. 다른 컨테이너/호스트 실행이나 /tmp 삭제 후에는 재개할 수 없습니다.')
    return project

PROJECT = check_upload_settings(PARAMS, EXPECTED_PROJECT)
'''

TAIL = '''
# 새 노트북에서도 이전 커널의 다른 패키지가 import 캐시에 남아 있으면 재시작합니다.
for module_name in ('zip_config', 'zip_install'):
    loaded = sys.modules.get(module_name)
    if loaded is not None and Path(getattr(loaded, '__file__', '')).resolve().parent != FLOW_PACKAGE.resolve():
        raise RuntimeError('다른 Gold Flow 코드가 로드되어 있습니다. Kernel Restart 후 이 셀을 실행하세요.')
from zip_config import validate
validate(PARAMS)
from zip_install import install
FLOW_CONFIG = install(PARAMS, BOOTSTRAP)
print('입력 폴더:', FLOW_CONFIG['input_folder'])
print('결과 폴더:', FLOW_CONFIG['folders']['report'])
print('시나리오 ID:', FLOW_CONFIG['scenario'])
print('Scenarios에서 실행 상태와 00_INPUT~07_REPORT 결과를 확인하세요. 셀 종료는 적재 완료를 뜻하지 않습니다.')
'''


def main():
    # Reuse the exact recipe bootstrap so its package identity remains unchanged.
    tree = ast.parse((PARENT / 'DATAIKU_GOLD_ZIP_FLOW_RUN_R1.txt').read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == 'install']
    assert len(calls) == 1
    bootstrap = ast.literal_eval(calls[0].args[1])
    sha = hashlib.sha256((PARENT / ZIP_NAME).read_bytes()).hexdigest()
    assert "ZIP_SHA256 = '" + sha + "'" in bootstrap
    cell = SETTINGS + PREFLIGHT + '\nBOOTSTRAP = ' + repr(bootstrap) + '\nexec(BOOTSTRAP, globals())\n' + TAIL
    ast.parse(cell, feature_version=(3, 9))
    run = HERE / 'DATAIKU_GOLD_ZIP_UPLOAD_RUN_R1.txt'
    run.write_text(cell, encoding='utf-8')
    shutil.copyfile(PARENT / ZIP_NAME, HERE / ZIP_NAME)
    receipt = {'version': 'gold-zip-upload-notebook-20261104-r1',
               'parent': str(PARENT.relative_to(HERE.parents[2])),
               'parent_code_unchanged': True, 'code_zip_sha256': sha,
               'entrypoint_sha256': hashlib.sha256(run.read_bytes()).hexdigest(),
               'external_execution': False}
    (HERE / 'HANDOFF.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
