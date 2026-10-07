GENOS LEGAL_AGENT 모델 HTTP 400: uniqueItems 문법 오류 패치 (2026-09-23)

현장 오류: Grammar error: Unimplemented keys: ["uniqueItems"]
원인: 요청의 response_format.json_schema에 GENOS 모델 grammar compiler가
지원하지 않는 uniqueItems 키가 들어갔습니다. max_tokens 문제로 확인되지 않았습니다.

변경: ModelGateway와 bounded source 요청이 모델로 보내는 schema에서만
uniqueItems를 제거합니다. 애플리케이션의 원본 schema와 결과 검증은 유지합니다.
워크플로우 코드는 변경하지 않습니다.

코드스페이스에서 기존 ~/DEV를 사용하는 경우:

  cd -P ~/DEV
  python3 -m zipfile -t TRANSFER/genos-model-schema-uniqueitems-fix-20260923.zip
  python3 -m zipfile -e TRANSFER/genos-model-schema-uniqueitems-fix-20260923.zip TRANSFER
  python3 TRANSFER/genos-model-schema-uniqueitems-fix/apply.py --root .
  python3 TRANSFER/genos-model-schema-uniqueitems-fix/apply.py --root . --apply
  python3 TRANSFER/genos-model-schema-uniqueitems-fix/apply.py --root .
  python3 -m py_compile 02_BACKEND/semantic_runtime/legal_agent/gateway.py 02_BACKEND/semantic_runtime/legal_agent/bounded_source_session.py

첫 apply.py 실행은 버전·해시 검사만 합니다. --apply에서 코드 파일 2개,
연결된 엔진 manifest 26개와 PIPELINE.json의 해당 manifest pin만 갱신합니다.
모든 기존 해시가 맞지 않으면 적용하지 않습니다. 적용 직전의 파일 29개는
TRANSFER/uniqueitems-backup-<UTC시각>/ 아래에 저장됩니다.
적용 후 apply.py를 다시 실행해 ALREADY_APPLIED가 나오면 코드 2개,
엔진 manifest 26개, PIPELINE.json의 연결 해시가 일치합니다.
rehash-engines는 현재 코드스페이스에 없는 과거 데이터 manifest까지 확인하므로
이 패치의 설치 검증 명령으로 사용하지 않습니다.

코드스페이스 파일 적용과 실행 중 코드서빙 변경은 별개입니다. 현장에서 변경을
Git commit/push하고, 코드서빙 새 리비전을 배포한 뒤 워크플로우가 그 리비전을
호출하는지 확인하십시오. 재요청 후 요청별 JSON에서 model_attempt의 HTTP 상태와
model.attempt.accepted 또는 새로운 실패 원인을 확인합니다. HTTP 400이 사라져도
답변 품질과 근거 충실도는 별도 확인 대상입니다.

롤백: --apply 출력의 BACKUP 경로에서 같은 상대 경로의 파일 29개를 ~/DEV에
복사하고 원래 코드서빙 리비전으로 되돌립니다. 원본 질문·프롬프트·키는
ZIP에 포함하지 않습니다.
