# GENOS 최적화 정식 실행 진입점

`genos_data_optimized.sh`는 검증된 v2의 명시적 DRAFT 실행 진입점이다.
기존 `genos_data_stages.sh`와 운영 MAIN 기본값은 변경하지 않았다.
optimizer 파일 SHA-256을 확인하고 repository의 실제 경로에서 실행한다.

## 저장소 최신 코드가 있는 환경

```bash
bash 06_TOOLS/COMMANDS/genos_data_optimized.sh --run-id external-opt-001 --exclude-internal --stage structure --execute
```

새 run-id를 사용한다. 원본·기존 캐시·중단된 LLM 결과는 삭제하지 않는다.
구조화만 실행하므로 LLM 호출은 없고, 진단용 85초 대조 검사는 실행하지 않는다.
파일 해시 검증은 유지한다. 최초 최적화 캐시는 새 지문으로 생성된다.

LLM 처리까지 원할 때는 동일 코드·run-id로 아래 명령을 사용한다. 실제 모델 호출이 발생한다.

```bash
bash 06_TOOLS/COMMANDS/genos_data_optimized.sh --run-id external-opt-001 --exclude-internal --stage llm --execute
```

## 이미 메일로 받은 v2만 있는 GENOS 환경

새 설치 없이 기존 첨부 파일로 같은 경로를 실행할 수 있다.

```bash
cd /home/genos/DEV
.venv/bin/python -u TRANSFER/genos_structure_optimized_v2.py.txt --pipeline --run-id external-opt-001 --exclude-internal --stage structure --execute
```

`--pipeline` 모드에는 timing 파일이 필요하지 않다. 이번 로컬 변경은 GENOS에 자동 배포되지 않는다.
rollback은 원래 실행기와 그 실행기의 기존 run-id로 복귀한다. 서로 다른 구현의 run-id를 섞지 않는다.

## MAIN 전환 차단 조건

ADR-0345는 Proposed, decision_eligible=false, main_wiring=unchanged이다.
현장 단일 문서의 성공 사진만으로 완료된 ADR을 소급 Accepted로 바꾸지 않는다.
정식 MAIN 전환에는 별도 동결 분리 검증, Accepted 완료 arm, 등록된 rollback switch,
hash-bound promotion plan/check/apply가 필요하다.
현재 전역 graph에는 기존 ADR-0305 run purpose 오류와 ADR-0158 부모 arm 누락도 남아 있다.
이 런처의 추가는 해당 오류 수정이나 MAIN 승격을 의미하지 않는다.
