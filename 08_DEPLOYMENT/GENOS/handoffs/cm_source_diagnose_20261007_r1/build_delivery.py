"""Seal a small read-only TXT; keep the already sent R8 delivery unchanged."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NAME = 'GENOS_CM_SOURCE_DIAG_20261007_R1'


def main():
    code = (ROOT/'06_TOOLS/COMMANDS/genos_cm_source_diagnose.py').read_text()
    compile(code, 'genos_cm_source_diagnose.py', 'exec')
    script = '''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_transfer="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
task_reports="$task_transfer/cm-source-diag-r1"
mkdir -p -- "$task_reports"
task_output="$(mktemp -d "$task_reports/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
task_log="$task_output/DIAGNOSIS.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"' EXIT
printf 'CM 원문 읽기 전용 진단 시작 LOG=%s\\n' "$task_log"
python3 - "$task_transfer" "$task_output" <<'CM_SOURCE_DIAG_PY'
'''+code+'\nCM_SOURCE_DIAG_PY\n'
    run = OUT/(NAME+'_RUN.txt')
    with run.open('x', encoding='utf-8') as handle:
        handle.write(script)
    subprocess.run(['bash', '-n', str(run)], check=True)
    guide = '''CM R8 원문 버전 오류 — 읽기 전용 진단

1. GENOS_CM_SOURCE_DIAG_20261007_R1_RUN.txt를 기존 ~/DEV/TRANSFER에 올립니다.
2. 아래 한 줄을 실행합니다.

bash ~/DEV/TRANSFER/GENOS_CM_SOURCE_DIAG_20261007_R1_RUN.txt

문서명 없음 / 원본 해시 다름 / 동일 원본 중복을 구분하고 CM 전체21문서를 대조합니다.
터미널의 대조 결과를 보내주세요. 필요하면 마지막 LOG 경로의 파일을 전달합니다.
자동 결과 파일: ~/DEV/TRANSFER/cm-source-diag-r1/<실행별 폴더>/SOURCE_DIAGNOSIS.json

R8이 생성한 경로 설정과 실패 당시 manifest 해시를 확인해 같은 NFS 세대를 읽습니다.
서버 Python 표준 라이브러리만 사용합니다. 새 환경변수·사용자·팀 입력은 없습니다.
코드·원문·등록 DB를 변경하지 않고 기존 R8 로그와 백업을 보존합니다.
이 파일은 등록·push·배포를 수행하지 않습니다. 모델 호출도 없습니다.
현장 데이터 확인 전에는 이름 변경이나 해시 차이를 원인으로 단정하지 않습니다.
'''
    (OUT/(NAME+'_GUIDE.txt')).write_text(guide)
    record = {'version': NAME, 'operation': 'READ_ONLY_DOCUMENT_IDENTITY_DIAGNOSIS',
              'source_path': '06_TOOLS/COMMANDS/genos_cm_source_diagnose.py',
              'source_sha256': hashlib.sha256(code.encode()).hexdigest(),
              'RUN_sha256': hashlib.sha256(script.encode()).hexdigest(),
              'registration_performed': False, 'model_calls': 0,
              'GENOS_field_verified': False, 'email_sent': False,
              'files': [{'name': p.name, 'bytes': p.stat().st_size,
                         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                        for p in (run, OUT/(NAME+'_GUIDE.txt'))]}
    (OUT/'HANDOFF.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n')
    print('BUILT', run.name, len(script.encode()), 'bytes')


if __name__ == '__main__':
    main()
