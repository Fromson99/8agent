"""Package the existing read-only report summarizer as a standalone bash TXT."""
from pathlib import Path
import hashlib
import json
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NAME = 'GENOS_MODEL_CALL_DIAG_20261013_R1'


def main():
    source = ROOT / '06_TOOLS/COMMANDS/genos_request_timing.py'
    code = source.read_bytes()
    runner = '''#!/usr/bin/env bash
set -euo pipefail
umask 077
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo '사용법: bash GENOS_MODEL_CALL_DIAG_20261013_R1_RUN.txt "/실제/요청보고서.json" ["/새/요약.txt"]' >&2
  echo '전체 요청 .json을 지정하세요. .llm_raw.jsonl이 아닙니다.' >&2
  exit 2
fi
diag_report="$1"
diag_output="${2:-${diag_report%.json}.model_diag.txt}"
python3 - --models-only --report "$diag_report" --output "$diag_output" <<'GENOS_MODEL_DIAG_PY'
'''.encode() + code + b'''\nGENOS_MODEL_DIAG_PY
cat -- "$diag_output"
'''
    guide = '''GENOS 모델 호출 요약 R1 — 기존 JSON 읽기 전용

목적
전체 요청 JSON의 article/원문/질문/프롬프트/답변을 화면에 늘어놓지 않고,
호출별 단계·HTTP·입력 문자 수·출력 한도·응답 스키마 지문·재시도 여부를 확인합니다.
기존 genos_request_timing.py의 --models-only 기능을 독립 실행 TXT에 포함했습니다.
Python 표준 라이브러리만 사용합니다. 패키지 설치, 모델 호출, 서비스 재배포는 없습니다.

실행
1. ZIP을 TRANSFER의 원하는 폴더에 풉니다. 별도 첨부 RUN TXT만으로도 실행할 수 있습니다.
2. 아래 /실제/요청보고서.json을 현장 파일의 정확한 경로로 바꾸고 실행합니다.

bash GENOS_MODEL_CALL_DIAG_20261013_R1_RUN.txt "/실제/요청보고서.json"

기존 현장 설정 기준 위치:
/nfs-root/diamo/8-agent/rag-request-reports/2026-10-13/financial_team/
이 폴더의 요청ID-고유값.json을 선택합니다. .llm_raw.jsonl/.txt/.log는 입력이 아닙니다.
코드서빙의 GENOS_SHARED_LOG_DIR 설정이 다르면 그 실제 경로를 사용합니다.
요청보고서 옆에 같은 이름의 .model_diag.txt가 생기고 터미널에도 출력됩니다.
원본 JSON은 읽기만 합니다. 요약 파일이 이미 있으면 덮어쓰지 않고 중단합니다.
쓰기 권한이 없거나 다시 실행할 때는 두 번째 인자로 새로운 출력 경로를 지정합니다.

bash GENOS_MODEL_CALL_DIAG_20261013_R1_RUN.txt "/실제/요청보고서.json" "$PWD/model_diag_02.txt"

확인 항목
- HTTP 200 뒤 실패한 호출 단계와 attempt_id/start 시각
- 입력 문자 수, 저장 요청 재직렬화 바이트, max_tokens, temperature, stream, thinking
- response_format/strict, 스키마 바이트/해시, enum 항목 수와 빈 enum 수
- 응답이 제공한 실제 prompt_tokens/completion_tokens (없으면 unknown)
- 직전 성공 대비 model_same, input_chars_delta, schema_same, max_tokens_same
- 모델 오류 응답의 알려진 단서만 표시; 자유 형식 오류 본문은 복사하지 않음

판정 범위
문자 수는 토큰 수가 아니며, 요청 재직렬화 크기는 실제 전송 바이트의 계측값이 아닙니다.
동적 enum 때문에 스키마 해시는 정상 호출 사이에도 달라질 수 있습니다.
값이 달라졌다는 사실만으로 HTTP 500 원인을 확정하지 않습니다.
model_attempt가 보고서에 없으면 서비스 이벤트만 요약하고 요청 비교 불가로 표시합니다.
실제 서버 예외는 같은 시간의 LLM 서빙/게이트웨이 로그에서 확인해야 합니다.
현장 보고서 자체는 이 외부 개발 환경에 없으며, 현장 실행 결과는 아직 미확인입니다.
'''
    files = {'genos_request_timing.py': code, NAME + '_RUN.txt': runner,
             'GUIDE_UTF8.txt': guide.encode('utf-8')}
    binding = {'tool': str(source.relative_to(ROOT)), 'sha256': hashlib.sha256(code).hexdigest(),
               'mode': 'read_only_existing_report', 'network_calls': 0,
               'onsite_execution': 'NOT_RUN', 'serving_code_changed_by_runner': False}
    files['SOURCE_BINDING.json'] = (json.dumps(binding, ensure_ascii=False, indent=2) + '\n').encode()
    files['SHA256SUMS.txt'] = ''.join(hashlib.sha256(raw).hexdigest() + '  ' + name + '\n'
                                    for name, raw in sorted(files.items())).encode()
    for name, raw in files.items():
        (HERE / name).write_bytes(raw)
    target = HERE / (NAME + '.zip')
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            assert Path(name).suffix.lower() not in ('.js', '.jsx', '.mjs', '.cjs')
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 13, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, raw)
    print(target)


if __name__ == '__main__':
    main()
