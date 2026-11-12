"""Gold 적재 대상(소유자·표 이름 앞부분)을 Dataiku 프로젝트 변수에서 읽는다.

개발계와 운영계는 표 이름·컬럼이 같고 소유자만 다르다(개발계 SIDDS, 운영 SIDDG).
코드·레시피에는 소유자를 넣지 않고, 실행할 때마다 프로젝트 변수로 정한다.

  LGL_GOLD_OWNER         필수. Gold 13표 소유자 (예: SIDDS, SIDDG)
  LGL_GOLD_TABLE_PREFIX  선택. 기본 IDD_B003_LGL_. 시험 복사본(TST_B003_LGL_ 등)에 적재할 때만 바꾼다.
"""
import re

OWNER_VAR = 'LGL_GOLD_OWNER'
PREFIX_VAR = 'LGL_GOLD_TABLE_PREFIX'
DEFAULT_PREFIX = 'IDD_B003_LGL_'


def resolve(variables):
    owner = str(variables.get(OWNER_VAR) or '').strip()
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,29}', owner):
        raise ValueError('LGL_GOLD_OWNER_REQUIRED: 프로젝트 변수 LGL_GOLD_OWNER에 Gold 소유자를 대문자로 넣으세요 '
                         '(개발계 SIDDS, 운영 SIDDG). 지금 값: ' + repr(owner))
    prefix = str(variables.get(PREFIX_VAR) or DEFAULT_PREFIX).strip()
    # 인덱스 이름 X4_<앞부분><표 9자>가 30자를 넘지 않게 앞부분은 18자까지.
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,17}', prefix) or not prefix.endswith('_'):
        raise ValueError('LGL_GOLD_TABLE_PREFIX_INVALID: 대문자로 시작하고 _로 끝나는 18자 이내 (기본 IDD_B003_LGL_). '
                         '지금 값: ' + repr(prefix))
    return {'GOLD_OWNER': owner, 'TABLE_PREFIX': prefix}


def report_name(gold):
    """적재 결과 파일 이름 — 시험 복사본(앞부분이 다름)은 따로 남겨 같은 trial의 기본 결과와 부딪히지 않게."""
    if gold['TABLE_PREFIX'] == DEFAULT_PREFIX:
        return 'report.json'
    return 'report-' + gold['TABLE_PREFIX'].rstrip('_').lower() + '.json'
