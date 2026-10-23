"""Build the explicitly requested prefilled diagnostic from sealed R2."""
import ast
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PARENT = HERE.parent / 'relay_terminal_20261023_r2'
OUT = HERE / 'private_delivery'
NAME = 'GENOS_RELAY_CHECK_20261023_R3'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inputs():
    env = ROOT / '.env'
    values = [line.split('=', 1)[1].strip() for line in env.read_text().splitlines() if line.startswith('LAW_OC=')]
    assert len(values) == 1
    law = ast.literal_eval(values[0])
    sample = ROOT / '08_DEPLOYMENT/DATAIKU/law_api_photo_20261015_r1/private_delivery/DATAIKU_PHOTO_INPUTS_20261015_R1_CELL.txt'
    for node in ast.parse(sample.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PHOTO_INPUTS' for t in node.targets):
            photo = ast.literal_eval(node.value)
            break
    else:
        raise ValueError('Local photo inputs missing')
    return {'LAW_OC': law, 'MAKING_OC': photo['OC'], 'RELAY_COOKIE': photo['Cookie']}


def main():
    os.umask(0o077)
    OUT.mkdir(exist_ok=True, mode=0o700)
    parent = PARENT / 'GENOS_RELAY_CHECK_20261023_R2.txt'
    sealed = json.loads((PARENT / 'SEALED.json').read_text())
    assert sha(parent.read_bytes()) == sealed['script_sha256']
    source = parent.read_text()
    old = "oc, cookie = os.environ.get(key, '').strip(), os.environ.get('RELAY_COOKIE', '').strip()"
    assert source.count(old) == 1
    source = source.replace(old, "oc = os.environ.get(key, DEFAULT_CREDENTIALS[key]).strip()\n        cookie = os.environ.get('RELAY_COOKIE', DEFAULT_CREDENTIALS['RELAY_COOKIE']).strip()")
    source = source.replace('genos-relay-terminal-20261023-r2', 'genos-relay-terminal-20261023-r3')
    source = source.replace('GENOS_RELAY_RESULTS_R2', 'GENOS_RELAY_RESULTS_R3')
    source = source.replace('MAX_BYTES =', '# User-requested prefilled values; explicit environment variables take precedence.\nDEFAULT_CREDENTIALS = ' + repr(inputs()) + '\nMAX_BYTES =', 1)
    compile(source, NAME + '.txt', 'exec')
    (OUT / (NAME + '.txt')).write_text(source)
    guide = (PARENT / 'GUIDE.txt').read_text().replace('R2', 'R3')
    guide = guide.replace('R1과 기존 실패 결과는 그대로 두고 새 R3 파일을 사용합니다.', '이전 R1/R2와 기존 실패 결과는 그대로 두고 이번 R3 파일을 사용합니다.')
    start = guide.index('   국민참여입법센터에 현재 등록된 OC를 비표시 입력합니다.')
    end = guide.index('\n   목적지:', start)
    guide = guide[:start] + '''   사용자 요청에 따라 법제처 OC, 입법센터 샘플 OC, 샘플 Cookie를 실행 TXT에 미리 넣었습니다.
   별도 입력 없이 실행됩니다. 입법센터 OC/Cookie는 2026-10-15 보관 샘플로 현재 유효성은 미확인입니다.
   LAW_OC/MAKING_OC/RELAY_COOKIE 환경변수가 있으면 그 값이 내장값보다 우선합니다.
   값을 교체하려면 TXT 상단 DEFAULT_CREDENTIALS를 수정하거나 위 환경변수에 새 값을 설정하세요.
   Cookie 없이 실행하려면 RELAY_COOKIE='' 환경변수로 명시합니다.
   값 변경 후에는 --run-id notice-02 또는 law-02로 새 기록을 사용합니다.
''' + guide[end:]
    guide = guide.replace('이 경우 국가법령정보센터에 등록한 OC를 입력합니다. LAW_OC 환경변수 사용 가능.', '이 경우 내장된 로컬 법제처 OC를 사용합니다. LAW_OC 환경변수로 교체할 수 있습니다.')
    guide = guide.replace('이번 R3는 로컬 합성 통신 검증 결과와 GENOS 현장 실행을 구분합니다.', '이번 R3는 R2의 통신·로그·검증을 유지하고 인증값 기본값과 출력 폴더만 구분합니다.\n로컬 합성 통신 검증 결과와 GENOS 현장 실행을 구분합니다.')
    (HERE / 'GUIDE.txt').write_text(guide)
    binding = {'parent_script': str(parent.relative_to(ROOT)), 'parent_sha256': sealed['script_sha256'],
               'script': NAME + '.txt', 'script_sha256': sha(source.encode()),
               'changes': ['explicitly requested local credential defaults', 'R3 version and separate result directory'],
               'credential_sources': {'LAW_OC': '.env', 'MAKING_OC': '2026-10-15 stored photo sample', 'RELAY_COOKIE': '2026-10-15 stored photo sample'},
               'credential_validity_verified': False, 'genos_network_called': False, 'main_changed': False,
               'failure_contract': 'R2 phases/status/budget/no retries/redaction preserved; explicit env overrides defaults; existing run IDs do not resend.'}
    (HERE / 'SOURCE_BINDING.json').write_text(json.dumps(binding, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'BUILT', 'script_sha256': binding['script_sha256'], 'credentials_printed': False}))


if __name__ == '__main__':
    main()
