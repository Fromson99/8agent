def format_record(original):
    return '\n\n'.join([
        '# 고정2턴 실제 복구 시험 기록',
        '## 1. 실행 메타\n\nrun-001 / verified / review-followup. 제품 Qwen qwen/qwen3.8-27b. 실제 시각·입력 코드·해시는 ../artifacts/design/freeze.json 및 ../artifacts/live/review-followup/dispatch.json에 exact로 보존. baseline 새 호출0, 평가모델0.',
        '## 2. 사용자 질문 원문\n\n아래는 원래 기록의 내용이며 편집은 표준 절 제목을 추가한 것뿐이다.\n\n'+original,
        '## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n법률 기준답변/모델 채점 없음. 사전 기술 기준은 ../artifacts/design/criteria.json. 원문만 응답·후속 동일사건·원문검증·재조회 무호출을 확인하며 법률품질 점수로 확대하지 않는다.',
        '## 4. 제품 입력을 구성한 원값\n\n고정 질문과 사실은 ../artifacts/design/cases.json, 원문3조는 ../artifacts/design/source.json. 전체 실제 canonical view/schema는 ../artifacts/live/review-followup/canonical/*.json.gz, 실제 wire는 raw/call-*/request.json.gz에 보존했다.',
        '### 회수·탈락 단계 원장 — run·arm별\n\n회수 효과 비교가 아닌 복구 시험이므로 stage_ledger는 not_applicable. 원문 확보/전달 대조와 ACL은 audit.json.gz, navigation state는 states/*.json.gz에서 확인한다. 제품 입력에 채점 gold 유입0.',
        '## 5. 제품 모델 호출 — run·arm별 실제 원문\n\nverified/run-001의 전송 원문·원응답·usage·지연은 ../artifacts/live/review-followup/raw/call-*/request.json.gz, response.json.gz, finished.json. 주입은 injection/의 원래 응답과 delivered-response를 구분한다. 생략 요약으로 원문을 대체하지 않는다.',
        '## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n추가 연구용 router/judge 없음. 제품 내부 분류·명령·검토·보완도 같은 raw 및 canonical 전량에 포함. calls.json/generations.json에 순서·stage·turn을 기록했다.',
        '## 7. 채점 호출과 반복 판정\n\n평가 모델0. fresh-process audit.py가 코드·원문·ACL·wire·물리/예약 예산·재조회 영수증을 대조한다. 동일 셀 자동 반복0, in-sample·질문고정의 한계를 유지한다.',
        '## 8. 사례 최종 판정\n\n../artifacts/run-001/result.json의 checks와 status 및 ../README.md를 따른다. 실패/UNKNOWN은 통과로 고치지 않는다. 첫 원문 응답은 검토된 법률 결론이 아니다.'
    ])+'\n'
