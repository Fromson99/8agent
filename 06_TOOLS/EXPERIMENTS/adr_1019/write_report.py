"""Write final research documentation from preserved results, no model calls."""
from common import *
from report_common import finish_documents,seal
r=read(RUN/'summary.json');m=read(ADR/'실험/manifest.json');cases=read(DES/'cases.json')
criteria=read(ART/'offline/criteria.json');frozen=read(DES/'freeze.json')
table='| 질문 | 기존 모델 설명 | 후보 모델 설명 | 후보 필수 표시 | 기존 초·호출 | 후보 초·호출 |\n|---|---:|---:|---:|---:|---:|\n'
for c in cases:
    pair={v['arm']:v for v in r['rows'] if v['case_id']==c['id']}
    b=pair.get('baseline');a=pair.get('candidate')
    score=lambda x:f"{x['required_items_met']}/{x['required_items_total']}" if x else '미실행'
    cost=lambda x:f"{x['seconds']:.1f}·{x['model_calls']}" if x else '미실행'
    display=(str(a['required_review_audit']['displayed_count'])+'/'+str(a['required_review_audit']['expected_count'])) if a else '미실행'
    table+=f"| {c['id']} | {score(b)} | {score(a)} | {display} | {cost(b)} | {cost(a)} |\n"
parts=[
 '원문별 필수 검토 항목의 상태·근거·최종 표시를 격리 후보에 구현했다. MAIN102 및 GENOS는 반영하지 않았다. '
 '구조 검사19개, 원문 전달·정책 검사15개, 실제 API의 합성4시나리오(8검증 묶음)를 통과했다. '
 '실제 모델 비교 결과는 아래와 같으며 필수 메모 표시를 정답으로 세지 않았다. '
 '항목 연결 오류가 다른 검증된 설명까지 제거하는 결함이 확인되어 이 후보의 운영 통합은 기각한다. '
 '[확인된 결함과 수정 요구](artifacts/known-failures.json). '
 '[기계 판독 결과](artifacts/run-001/summary.json), [구조 감사](artifacts/run-001/required-audit.json).',
 'ADR0996의 use-first 프롬프트는 원문을 받았어도 설명 누락·기존 claims 소실을 막지 못했다. '
 '이번 후보는 기존 SELECT 원문 전달 뒤 ASSESS에서 source-bound METHOD steps를 필수 항목으로 결속한다. '
 '같은 ASSESS 응답에 EXPLAIN/NOT_APPLICABLE/UNKNOWN/KEEP을 받으며, 근거 연결·이력은 기존 Agent 저널에 보존하고 COMPOSE가 정해진 형식으로 표시한다. 별도 생성·채점 모델 단계를 추가하지 않는다.',
 '[호출 전 동결 기준](artifacts/design/criteria.json), [424파일 코드 동결과 입력 해시](artifacts/design/freeze.json). '
 '모든 등록 항목의 상태·메모 표시100%, 출처·권한·해시 보존, 모델 설명 항목 전체·질문별 비열등, 새 금지추론 없음, 호출 기준+5 이하 및 전체 지연1.5배 이하를 미리 고정했다. '
 '모델 누락은 UNKNOWN으로 남긴다. 논리적 정답을 자동 보증하지 않으며 불확실성만으로 반복 조사를 강제하지 않는다.',
 '직접 부모는 완료된 ADR0996 candidate다. 두 arm 모두 use-first 프롬프트·원문 전달·읽기 쉬운 검토 메모를 동일하게 사용한다. '
 'candidate만 필수 항목의 구조·상태·표시를 사용한다. CM051·008은 CLOSED_EVIDENCE, 나머지는 EXTEND이며 질문별 정책은 동결했다. '
 '5질문×2arm을 번갈아 순차 실행한다. 메모 투영은 양쪽 모두 변경했으므로 이전 ADR0996 수치와 이번 수치를 직접 이어 붙이지 않는다.',
 '완료 부모의 MAIN100 기반424파일을 동결했으며 현행 MAIN102 작업 코드에 덮어쓰지 않았다. '
 '[현재 작업 코드와 부모 차이](artifacts/design/working-parent-differences.json)를 보존했다. '
 'Gold 연구 저장소에는 원문4단위·METHOD6/FIELD2/APPLICATION1을 저장했고, 질문·판단·실패 이력은 Agent 연구 저장소에 둔다. '
 '원문 판본·좌표·개념이 재사용 지식의 키이며 질문은 발견·조회 이력이다. Qwen3.8/Parasail FP8, reasoning none, fallback 없음, 요청24호출900초, RSS6GiB·가용3GiB 하한이다. '
 '로컬 SQLite는 연구 실행용이며 Oracle/GENOS 연동 완료를 뜻하지 않는다.',
 table+'\n\n사전 기준 판정: `'+json.dumps(r['success_criteria'],ensure_ascii=False)+'`. '
 '모델 설명 점수는 고정된26개 항목만 평가한다. 화면의 등록 메모·미확인·원문 발췌는 설명 점수에서 제외한다.',
 '\n\n'.join(v['case_id']+' '+v['arm']+': '+v['review']['note'] for v in r['rows'])+
 '\n\n구현 중 사전 API 검사에서 항목 키가 기존 입력 ID 축약기와 맞지 않는 문제를 발견했다. '
 '동결·외부 호출 전에 item_id 배열 계약으로 바꿨고 API4시나리오를 다시 통과했다. 최초 import 충돌과 축약기 실패 로그도 보존했다. '
 '반복 형식 실패는 기존 수정1회 후 검증된 원문·UNKNOWN으로 제한 응답하며 실패 이력을 성공 지식으로 승격하지 않는다.',
 '```json\n'+json.dumps({'by_arm':r['by_arm'],'usage':r['usage']},ensure_ascii=False,indent=2)+'\n```\n\n'
 '[원문→최종 인용 회수 원장](artifacts/run-001/retrieval-ledger.json), [실제 판단 입력의 원문 전달 감사](artifacts/run-001/delivery-audit.json). '
 '속도는 각 arm/질문1회 관찰값이고 첫 요청 준비 시간 차이가 포함된다. 실행별 메모리·디스크 표본은 run-001-resource.json/jsonl에 보존했다.',
 '시스템이 강제할 수 있는 것은 원문에 연결한 필수 항목의 존재, 처리 상태, 근거 연결, 이력, 최종 표시다. '
 'EXPLAINED는 출처를 검증한 claim이 연결됐다는 뜻이며 해당 항목의 법률 의미를 올바르게 설명했다는 인증이 아니다. '
 'NOT_APPLICABLE도 모델의 비적용 의견으로 표시한다. 모델이 항목을 생략하면 이전 기록을 보존하면서 현재 상태를 UNKNOWN으로 남긴다. '
 '[모델이 항목을 생략한 합성 API 표시 예](artifacts/synthetic-display-omitted.txt).',
 '이미 노출된 CM4질문과 개발자가 구성한 복합1질문의 인샘플 비교다. 신규 복합 질문도 holdout이 아니다. '
 '원문 메모는 수동 보완한 연구용 후보이며 전문가 승인 지식이나 법령 최신성 검증으로 표시하지 않는다. '
 '등록하지 않은 중요 항목까지 자동으로 빠짐없이 발견하는 기능은 이번 범위가 아니다. '
 '독립 평가자·반복 측정·운영 Oracle·GENOS 내부 모델 검증은 수행하지 않았다. '
 '자동 입력 제한 때문에 긴 원문이 빠지는 경우에는 누락 상태를 표시하고 의미 설명으로 세지 않는다.',
 '격리 실험 후보 보존. 작업 코드/선택 MAIN/GENOS 반영·Git commit/push 없음. '
 '부모 snapshot 전체를 작업 코드에 덮어쓰지 않았다. MAIN 통합을 진행할 때는 현재 MAIN102 이후 변경과 충돌을 대조하고 동일 통합 코드로 별도 검증해야 한다. '
 '실험 후 프롬프트·모델 효과를 바꾸거나 같은 질문을 재실행하려면 새 ADR을 선점한다.',
 '실행 진입점은 `06_TOOLS/EXPERIMENTS/adr_1019/e2e.py run`이며 이미 시작된 run은 덮어쓰지 않는다. '
 '외부 모델 재실행은 새 ADR에서만 수행한다. `audit.py`, `delivery_audit.py`, `required_audit.py`, `summarize.py`는 저장된 기록의 모델0회 감사다. '
 '압축한 실행 저널은 해당 archive receipt의 원본 해시와 복원 명령을 따른다. '
 '`06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1019-source-required-answer-items --final` 및 graph 검사를 완료 기록에 남긴다.'
]
cp={}
for c in cases:
    rr=[v for v in r['rows'] if v['case_id']==c['id']]
    ledger='\n\n### 회수·탈락 단계 원장 — run·arm별\n\n| arm | 원문 열람 조문 | 최종 인용·발췌 조문 | 정확한 원장 |\n|---|---:|---:|---|\n'
    for x in rr:
        link='../artifacts/run-001/agent_layer/'+x['arm']+'/'+c['id']+'/retrieval-capture.json'
        ledger+=f"| {x['arm']} | {x['read_articles']} | {x['final_cited_articles']} | [좌표·추가·제외]({link}) |\n"
    ledger+='\n최종 인용·발췌는 모델의 충분한 설명을 뜻하지 않는다. 정답 근거와의 대조는 [후처리 회수 원장](../artifacts/run-001/retrieval-ledger.json)에 분리했다.'
    cp[c['id']]=['run-001; baseline/candidate; native /v1/rag/ask; in-sample.',c['question'],
        json.dumps(criteria[c['id']],ensure_ascii=False,indent=2),
        '[동일 원문 지식 입력](../artifacts/run-001/gold_layer/source-concept-registry.json). 양 arm의 등록 메모는 동일하고 판정 기준은 제품 입력과 분리했다.'+ledger,
        '`../artifacts/run-001/agent_layer/{baseline,candidate}/'+c['id']+'/`의 request.json·response.json·answer.txt·wire/·raw/·canonical/에 실제 입출력을 보존한다. 미실행 arm은 응답을 만들지 않는다.',
        'calls.json·generations.json·원시 저널에 모든 호출·수정·실패·사용량·지연을 기록한다. 전체 요청을 새 예산으로 재시도하지 않았다.',
        '모델 judge0회. 동결 required/forbidden을 작성자가 검토했다. 등록 메모나 미확인 표시는 모델의 내용 설명 성공에 포함하지 않는다.',
        json.dumps(rr,ensure_ascii=False,indent=2)]
finish_documents(ADR,'원문별 필수 설명 항목의 상태 보존과 최종 표시',parts,cp)
state='Rejected'  # Observed content-preservation defect; keep frozen metric results separate.
p=ADR/'README.md';p.write_text(p.read_text().replace('status: Proposed','status: '+state))
seal(ADR)
print(table)
