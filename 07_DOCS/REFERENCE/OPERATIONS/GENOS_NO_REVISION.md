# GENOS 리비전 필수 조건 제거 패치

`GENOS_LLM_REVISION` 또는 `--model-revision` 없이 데이터 E2E를 실행한다.
GENOS가 요구하지 않는 별도 리비전 값을 사용자에게 요구하던 두 검사를 제거했다.
기존 DOC 변환·실패 건너뛰기·통과율 출력·청크 임베딩 배치는 그대로 유지한다.
URL·키·서빙 ID·현장 전송 코드·service.py·원본·Git·CURRENT는 변경하지 않는다.

## 설치와 실행

`genos-no-revision-20260910.zip`과 `genos_apply_no_revision.sh.b64.txt`를
`/home/genos/DEV/TRANSFER`에 올린 뒤 아래 전체를 실행한다. unzip은 필요 없다.
기존 doc-skip-001과 구분하기 위해 새 run-id doc-skip-002를 사용한다.

```bash
(
set -e
cd /home/genos/DEV/TRANSFER
base64 -d genos_apply_no_revision.sh.b64.txt > genos_apply_no_revision.sh
bash genos_apply_no_revision.sh

cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh \
  --run-id doc-skip-002 --execute \
  --embed-batch-size 64 --max-calls 10000
)
```

입력만 먼저 확인하려면 --execute 대신 --check-only를 사용한다.
GENOS 모델 환경변수는 기존 연결 성공한 값 그대로 사용한다. 리비전은 입력할 필요 없다.
기존 명령 호환성을 위해 선택 옵션은 남아 있지만 미지정/빈 값도 실행을 막지 않는다.
미지정 리비전은 models.json에 null/not_provided로 기록하며, 기존 큐의 감사용 문자열은
unspecified(미지정)로만 기록한다. 실제 배포 버전을 추측하거나 API에 전송하지 않는다.
실제 요청 대상 모델 ID와 엔드포인트는 기존처럼 기록·재개 검증한다.
같은 모델 ID/주소 뒤에서 서버 모델이 교체되는 경우까지 감지한다고 보장하지 않는다.

## 결과와 중단/재개

- 진행 로그: data/logs/doc-skip-002/progress.log
- 결과/실패 사유/비율: data/builds/doc-skip-002/batch-result.json
- 문서별 완료 결과: data/builds/doc-skip-002/documents/<원본ID>/generation
- Ctrl+C로 중단한 뒤 같은 명령에 --resume을 붙여 재개한다. 저장되지 않은 요청은 재호출될 수 있다.
- 코드·원본·태그·스키마·모델 설정을 변경했으면 새 run-id를 사용한다.
- 성공 결과는 문서별 DRAFT 목록이다. 자동 통합/운영 반영/OQL/질문답변은 하지 않는다.
- DOC 변환에는 현장 LibreOffice/soffice가 필요하며 없거나 변환 실패하면 해당 문서만 건너뛴다.

이 패치는 합성 문서/fake provider로 검증한다. 실제 GENOS/현장 문서 전수 실행은 별도다.
