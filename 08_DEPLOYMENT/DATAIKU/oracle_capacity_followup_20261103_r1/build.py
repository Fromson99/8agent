"""Produce a paste-ready notebook cell and equivalent DBA SELECT statements."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('capacity_check',HERE/'capacity_check.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
source=(HERE/'capacity_check.py').read_text(encoding='utf-8')
ast.parse(source,feature_version=(3,10))
launch='''# Dataiku LEGAL_RAG / AIDP / 사진의 R3를 실행한 Python 노트북 새 셀.
# ZIP 업로드 없이 이 TXT 전체를 복사합니다. 기존 R3/적재 셀은 다시 실행하지 않습니다.
# Oracle SELECT만 수행. 새 로컬 결과 폴더만 생성. 기존 데이터/적재 기록은 변경하지 않습니다.
CAPACITY_REPORT_PATH = ''  # 같은 커널의 R3 결과를 사용. 필요할 때만 정확한 REPORT.json 경로.
CAPACITY_CONNECTION = 'AIDP'
import types as _capacity_types
_capacity_module = _capacity_types.ModuleType('g19_capacity_readonly')
'''+ 'exec(compile('+repr(source)+", '<g19_capacity_readonly>', 'exec'), _capacity_module.__dict__)\n"+'''
_capacity_module.REPORT_PATH = CAPACITY_REPORT_PATH
_capacity_module.CONNECTION = CAPACITY_CONNECTION
_capacity_result, _capacity_output = _capacity_module.notebook_main(globals().get('_g19_observer'))
def SHOW_CAPACITY_PAGE(name='요약'):
    _capacity_module.show(_capacity_result, _capacity_output, name)  # 저장 결과만.
'''
(HERE/'01_CHECK_CAPACITY_RUN_R1.txt').write_text(launch,encoding='utf-8')
labels={
    'identity':'Q1 실제 접속자/DB 확인',
    'tables':'Q2 현재 _1 대상 17개와 과거 통계; 실제 COUNT 아님',
    'segments':'Q3 _1 테이블+인덱스+LOB 물리 할당; 일반 테이블 구조만',
    'quota':'Q4 소유자 SIDDS/SIDDA의 해당 tablespace 전체 계정 사용량/등록 한도',
    'space':'Q5 공유 tablespace 파일/미할당 extent/자동확장 설정',
}
sql='-- DBA 전달용. 대상 DB/서비스는 Q1과 사진의 기존 AIDP 연결을 대조합니다.\n-- 각 Q를 별도로 실행하는 SELECT 전용 문서입니다. NULL/0행은 확인불가일 수 있습니다.\n-- quota 행 없음은 무제한/0 판정이 아닙니다. UNLIMITED TABLESPACE 직접/역할 권한은 DBA가 별도 확인합니다.\n-- _1 외 기존 표 용량은 Q3에 없고 계정 전체 할당은 Q4에 포함됩니다.\n-- 운영 여유/물리 디스크/자동확장 성공은 별도 확인. 임의 DDL/정리 명령 없음.\n\n'
for name,label in labels.items():sql+='-- '+label+'\n'+c.SQL[name]+';\n\n'
(HERE/'02_DBA_CAPACITY_SELECT.sql').write_text(sql,encoding='utf-8')
time_source=(HERE/'time_analysis.py').read_text(encoding='utf-8')
ast.parse(time_source,feature_version=(3,10))
time_launch='''# 같은 R3 Python 노트북 새 셀. 저장 보고서만 읽습니다. SQL/INSERT/모델 실행 없음.
TIME_REPORT_PATH = ''  # 같은 커널은 빈값. 필요할 때만 기존 REPORT.json의 정확한 경로.
import types as _time_analysis_types
_time_analysis_module = _time_analysis_types.ModuleType('g19_saved_time_analysis')
'''+ 'exec(compile('+repr(time_source)+", '<g19_saved_time_analysis>', 'exec'), _time_analysis_module.__dict__)\n"+'''
_time_analysis_result, _time_analysis_output = _time_analysis_module.run(globals().get('_g19_observer'), TIME_REPORT_PATH)
'''
(HERE/'03_ANALYZE_SAVED_R3_TIME_R1.txt').write_text(time_launch,encoding='utf-8')
analysis=HERE.parents[2]/'09_ARTIFACTS/AUDITS/20261103-dataiku-r3-capacity/예상시간과_SQL최적화.txt'
(HERE/'04_시간과_SQL검토결과.txt').write_bytes(analysis.read_bytes())
names=['01_CHECK_CAPACITY_RUN_R1.txt','02_DBA_CAPACITY_SELECT.sql','03_ANALYZE_SAVED_R3_TIME_R1.txt','04_시간과_SQL검토결과.txt','GUIDE.txt']
with zipfile.ZipFile(HERE/'ORACLE_CAPACITY_FOLLOWUP_20261103_R1.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in names:z.write(HERE/name,name)
manifest={name:{'bytes':(HERE/name).stat().st_size,'sha256':hashlib.sha256((HERE/name).read_bytes()).hexdigest()} for name in names}
(HERE/'ARTIFACTS.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Packaged',len(names),'files')
