# GENOS 채팅 화면 연결

GENOS 채팅 화면은 다음 한 경로로 답을 받는다.

`화면 질문 → 워크플로우 run(data) → 코드서빙 ELS_QUERY → /v1/rag/ask → {"text": ...} 반환`

먼저 [GENOS.md](../../../GENOS.md)의 환경·버전 기준을 확인한다. 2026-09-11 현재
[브릿지 코드](../../../08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py)의 `run(data)`는
완성된 답변을 `text`가 있는 dict로 반환하며 `yield`하지 않는다. 코드서빙이 만든 답변을
별도 LLM으로 재생성하지 않고, 실제 claim이 사용한 문서만 출처로 붙인다.

상위 main의 현장 V1.8.6 기록도 dict 반환이며, 데모 v1.9.1의 JSON token/end yield 규약과
다르다. 예전 “dict return이면 채팅 실패” 설명은 데모 기준으로만 읽는다.
다른 버전에 배포할 때는 그 환경의 반환 계약을 확인한다. 현재 코드 확인은 현장 배포 성공의 증거가 아니다.
근거: [버전별 현장 기록](../GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md).

## 1. 코드 저장소 적용

아래 `genos_apply_chat.sh` 절차는 해당 설치기가 포함된 인계본용이다. 설치 파일이 없거나 버전이 다르면 현재 커밋의 배포 절차를 사용한다.

전달 ZIP을 `/home/genos/DEV/TRANSFER`에 놓은 뒤 다음을 실행한다.

```bash
cd /home/genos/DEV/TRANSFER
bash genos_apply_chat.sh
```

스크립트는 기존 `/home/genos/DEV/service.py`를 전달본의 완성된 `service.py`로 교체하고
워크플로우 파일을 `/home/genos/DEV/08_DEPLOYMENT/GENOS/workflow/` 아래에 설치한다.
기존 service 파일은 `/home/genos/DEV/.genos-chat-backup-*`에 먼저 백업된다. 이후 변경을
Git에 커밋·push하고 그 커밋으로 코드서빙을 다시 배포한다.

## 2. GENOS 워크플로우 생성

GENOS 워크플로우 편집기의 Python 단계에 아래 파일 전체를 붙여 넣는다.

`08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`

진입 함수는 `run`이다. 채팅 앱 입력 전체를 `data`로 연결한다. `run`은 GenOS가 요구하는
token/end 이벤트를 직접 스트리밍하므로 별도 `text` 반환 노드는 두지 않는다.

워크플로우 리비전 환경변수에는 주소, 코드서빙 ID, 토큰을 각각 넣는다. 워크플로우
코드가 이 값으로 최종 호출 URL을 조합한다.

```text
GENOS_BASE_URL=http://<GENOS주소>
GENOS_CODESERVING_ID=<코드서빙ID>
GENOS_CODESERVING_TOKEN=<코드서빙 API 인증키>
GENOS_CODESERVING_TIMEOUT_SECONDS=120
```

최종 URL은 코드에서
`{GENOS_BASE_URL}/api/gateway/code_serving/{GENOS_CODESERVING_ID}/json`으로 만든다.
`GENOS_CODESERVING_URL`은 사용하지 않는다.

LLM 서빙 ID와 코드서빙 ID는 서로 다르다. 여기에는 코드서빙 ID를 넣는다. 키는 저장소나
워크플로우 코드에 쓰지 않는다.

## 3. 코드서빙 직접 확인

워크플로우 연결 전 코드서빙이 답을 내는지 먼저 확인한다. 아래 명령은 토큰을 명령행 인자나
히스토리에 직접 남기지 않는다.

```bash
python - <<'PY'
import json, os, urllib.request

base = os.environ["GENOS_BASE_URL"].rstrip("/")
serving_id = os.environ["GENOS_CODESERVING_ID"]
url = f"{base}/api/gateway/code_serving/{serving_id}/json"
token = os.environ["GENOS_CODESERVING_TOKEN"]
body = json.dumps({
    "API_TYPE": "ELS_QUERY",
    "question": "내규상 승인 절차를 알려줘",
    "channel": "genos-chat-test",
    "session_id": "manual-test-1",
    "user_id": "manual-test",
}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(url, data=body, method="POST")
req.add_header("Authorization", "Bearer " + token)
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req, timeout=120) as res:
    print(json.dumps(json.loads(res.read()), ensure_ascii=False, indent=2))
PY
```

정상 응답은 바깥에 `status: 200`, 안쪽 `body.answer.text`에 답변이 있다.

## 4. 화면 연결 확인

워크플로우를 저장·배포한 뒤 채팅 앱이 새 워크플로우 리비전을 선택했는지 확인한다. 화면에서
질문을 보내면 응답 객체의 `text`가 답변으로 표시된다. 진단용으로 `run_id`, `session_id`,
`tm_code_serving`, `tm_total`도 반환한다.

현재 `session_id`는 요청 추적용으로 전달되지만 대화 이력은 저장하지 않는다. 후속 질문이 앞선
대화를 자동으로 기억해야 한다면 별도의 승인된 세션 저장소와 이력 계약이 추가로 필요하다.

## 장애 구분

- `코드서빙 응답 401/403`: 코드서빙 인증키 또는 워크플로우 권한 문제
- `코드서빙 응답 404`: 코드서빙 ID나 URL 경로 문제
- `코드서빙 응답 422`: 질문/활성 데이터/LLM 구성 계약 문제. 코드서빙 로그의 상세 오류 확인
- `지금 답변을 가져오지 못했습니다`: 워크플로우에서 코드서빙까지의 네트워크 또는 설정 문제
- `관련 근거를 찾지 못해`: 호출은 성공했지만 활성 데이터에서 답변 근거를 만들지 못한 상태
