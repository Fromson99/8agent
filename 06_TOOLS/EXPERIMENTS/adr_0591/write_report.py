"""Publish existing results and static review. Does not rerun or rescore products."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0591-case-memory-functional-mock-probe'
RUN=ADR/'artifacts/run-001'
REPORT=ROOT/'07_DOCS/REFERENCE/REPORTS/CASE_MEMORY_FUNCTIONAL_MOCK_20261001'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n\n'
def link(p,from_dir=REPORT):return '['+p.name+']('+os.path.relpath(p,from_dir)+')'

GROUPS={'load':'적재·무결성','identity':'식별·권한','state':'사건 상태','correction':'판단 정정','history':'사용자 이력·선호','handoff':'다음 단계 전달','experience':'경험 적재·활용','recovery':'실패·복구','sql_boundary':'SQL 단독 검증 경계'}
LABELS=[
'23개 표와 질문·실행·판단 연결 적재','기존 사실 이력 UPDATE 차단','확정 상태의 사실 추가 차단','상태·사실 목록 지문 계산',
'외부 세션 원형 보존과 동일 세션 재조회','같은 세션 문자열·다른 사용자 분리','미인증 사용자 차단','다른 조직 사건 차단','읽기 권한·쓰기 금지·권한 회수','과도한 ID 길이는 절단 없이 거부',
'같은 입력 재시도에서 턴 중복 방지','같은 요청 키의 다른 입력 거부','오래된 상태 번호 거부','head 전 실패의 원자적 롤백','가정 분기에 부모 상태 고정','가정에 부모의 후속 정정 유입 차단','새 사건에 기존 사실 자동 복사 방지','검증 영수증 없는 확인 사실 거부',
'질문 2번과 발언 3번 구분','질문별 범위 정정·후속 판단만 재검토','목표와 판단 ID의 잘못된 연결 거부','정정 전 값 불일치 거부','모호한 명령의 상태 수정 차단','공통 당사자 정정의 두 목표 영향','새 예외에 기존 연결이 없어도 넓게 재검토','당사자 발언 철회의 미확인 보존','새 판단·대체 관계·이전 결론 보존','이미 대체된 판단의 재정정 거부',
'과거 판단의 이유·출처 원본 조회','답변 문단·게시본 지문·판단 정확 연결','사용자 입장을 agent 결론과 구분','개인 선호 최신값·철회 처리','개인 선호 만료·추정 미승인 제외','현재 사실·판단·이유·출처 전달','필수 상태 용량 초과 시 자르지 않고 중단',
'새 연결에서 저장 상태 재조회','두 연결의 오래된 상태 쓰기 거부','outbox 전달 후 영수증 전 실패·동일 재전달','같은 outbox ID의 다른 payload 차단','기존 native v5 판단 의존 무효화',
'SQL은 같은 조직의 무권한 발언자를 수락','SQL은 틀린 상태 JSON·지문을 수락','SQL은 잘못된 goal을 가진 정정을 수락','SQL은 64글자 비16진수 지문을 수락','SQL은 run-state 순번 공백을 수락','SQL은 근거 없는 적용 가능 판정을 수락','SQL은 같은 fact의 의미 키 변경을 수락','SQL은 같은 게시본의 상충 지문을 수락',
'조건 일치·가상 승인 경험 채택 가능','미검토 경험은 보존하되 채택 제외','원문 generation 변경 시 기본 경로 복귀','원문 hash 변경 시 기본 경로 복귀','현재 사용자 접근권한 재확인','당사자 등 적용 조건 변경 시 복귀','위키 연결 해제 시 복귀','분쟁 중인 지식은 채택 제외','중단된 원실행의 경험 채택 제외','부분 원문 읽기 경험 채택 제외','무결성 PASS로 법률 검토 FAIL 덮기 금지','경쟁하는 검토 최신본은 보류','명시적 검토 대체 관계 반영','실제 shortcut SQL 순환·부모 지문 검증','shortcut 질문부터 작업 영수증까지 적재']

def main():
    r=json.loads((RUN/'result.json').read_text());REPORT.mkdir(parents=True,exist_ok=True)
    assert len(LABELS)==len(r['features'])
    features=[{**x,'korean_feature':label} for x,label in zip(r['features'],LABELS)]
    # Independent bookkeeping check, preserving the original runner artifact.
    dbp=RUN/'functional/063-experience/shortcut.sqlite';db=sqlite3.connect(dbp)
    counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")};db.close()
    usage=json.loads((RUN/'provider/usage.json').read_text())
    binding=json.loads((ADR/'artifacts/design/baseline-binding.json').read_text())
    audit={'schema_version':'case-memory-report-audit-v1','source_result_sha256':sha(RUN/'result.json'),
      'shortcut_actual_table_rows':counts,'shortcut_actual_row_total':sum(counts.values()),'original_reported_rows':21,
      'note':'Original result remains unchanged. Its hard-coded row count is inaccurate: database has 19 rows.',
      'models':sorted(set(u['model'] for u in usage)),'upstream_providers':sorted(set(u['upstream_provider'] for u in usage)),
      'baseline_binding_unchanged':{p:sha(ROOT/p)==h for p,h in binding.items()},
      'guarded_dispatch_statuses':{x['id']:x['arms']['GUARDED']['dispatch']['status'] for x in r['natural_language']}}
    dump(ADR/'artifacts/report-audit.json',audit)
    issues=[
      ('I01','높음','NL03','사건 전체 범위 변경을 모호하다고 판단','두 목표가 있어도 명시 CURRENT_CASE는 일괄 정정으로 구분하는 계약 필요'),
      ('I02','높음','NL15','새 긴급 조건을 기록하지 않고 확인 질문으로 종료','목표가 없는 새 사건 조건의 기본 적용 범위와 영향 검토를 명시'),
      ('I03','높음','NL16','사용자 입장을 장기 개인 기억 변경으로 오분류','USER_POSITION 저장·색인·조회 경로를 개인 선호와 분리'),
      ('I04','높음','NL09','이번 답변 형식은 올바르게 해석했지만 실행기가 거부','request-local formatting handler를 연결하고 전역 선호를 수정하지 않기'),
      ('I05','높음','NL05 answer','가정 답변에 가정이라는 표시를 누락','절차·출처 ID 외에 실제/가정·조건·예외 표기의 게시 전 계약 검사 필요'),
      ('I06','높음','F041..F048','SQL 단독으로 의미·권한·지문 검증 8개를 강제하지 않음','검증된 writer만 DB 쓰기; 제약 가능한 항목은 스키마 새 버전에 추가 검토'),
      ('I07','높음','NL10 / dispatch','위키 수정 대상 실제 ID·버전이 없이 mock-wiki-v1 후보 생성','선택된 정확한 연결과 버전 확인 전에는 후보의 target을 미해결로 유지'),
      ('I08','높음','NL20 fixture','프롬프트에는 정정 완료라고 적었지만 DB에는 정정 이벤트가 없음','실제 저장한 순차 턴에서 이력·정정·게시까지 다시 검증; 현재 의미 해석 점수를 end-to-end 인증으로 쓰지 않기'),
      ('I09','높음','prototype API','실제 service/app/Coordinator에 continuity 연결 없음','신뢰된 envelope와 공통 context 서비스·스키마 소비자 연결'),
      ('I10','높음','identity/reviews/wiki fixtures','인증·법률 승인·위키가 모의 서비스/이벤트','GENOS identity·저장 토폴로지·공통 위키 계약을 실제 adapter로 검증'),
      ('I11','높음','handoff','일부 필드 전달·바이트 초과 검사만 있고 실제 wire/토큰 검증 없음','F/T/J/E와 원문 span/READ 영수증, response schema 포함 실제 전달량과 예산 검사'),
      ('I12','높음','concurrency/recovery','두 연결 검사는 순차 CAS; 장시간 실행 소유권·SSE 취소 미검증','lease/fencing·동시 정정·매 chunk 상태 확인·게시 충돌·다중 worker 재개 검증'),
      ('I13','중간','shortcut SQL','부모 없는 1개 선별 step의 모의 SKIPPED 영수증만 적재','실제 ranked pool·복수 부모 대응·생략 작업·fallback·전체 답변 품질 비교 필요'),
      ('I14','중간','user_wiki','별도 이력 화면·교차 세션 후보 탐색·정정 기록 조회 미구현','조회 소비자와 질문/goal/decision/correction projection 연결'),
      ('I15','낮음','F063 receipt','runner 행 수 21 표기는 실제 DB 19행과 다름','원시 결과 보존; 보고서는 DB에서 계산한 19행 사용'),
      ('I16','높음','apply static review','명령과 원발언 span의 일치까지 검증하지 않음','정정 대상 관계 외에도 현재 발언이 해당 변경을 명시하는지 검증; CONTINUE의 scope 변경 허용 경계 재설계'),
    ]
    dump(REPORT/'issues.json',[dict(id=i,priority=p,evidence=e,problem=q,next_action=a) for i,p,e,q,a in issues])
    with (REPORT/'features.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.writer(f);wr.writerow(['검사 ID','단계','세부 기능','실행 결과','실제 관측','판정 해석'])
        for x in features:
            meaning='SQL 외부 writer 검사 필요 확인' if x['group']=='sql_boundary' else '격리 후보/모의 fixture 범위에서 기대 동작'
            wr.writerow([x['id'],GROUPS[x['group']],x['korean_feature'],x['status'],json.dumps(x.get('observed',x.get('error')),ensure_ascii=False),meaning])
    with (REPORT/'natural_language.csv').open('w',newline='',encoding='utf-8-sig') as f:
        wr=csv.writer(f);wr.writerow(['사례','모의 발언','맥락 없음 해석 일치','맥락 있음 해석 일치','해석된 의도','실행 상태','처리 문제'])
        for x in r['natural_language']:
            a=x['arms']['GUARDED'];wr.writerow([x['id'],x['utterance'],x['arms']['baseline']['exact_match'],a['exact_match'],a['output']['intent'],a['dispatch']['status'],a['dispatch'].get('reason','')])

    text='''# 사건 기억·멀티턴 기능별 모의 실험 결과

2026-10-01 · ADR-0591 · WSL 로컬 · 합성 자료 전용 · 자체 검토 · MAIN 미변경

**질문별 정정과 이력 보존은 격리 후보에서 작동했다. 자연어 해석과 실행 연결에는 아직 실패가 있다.**
저장 성공, 모델 해석 성공, 실제 기능 완료를 구분해야 한다. 기존 설계의 SQL은 잘못된 행을 전부 막는 스키마가 아니며, 인가·의미·지문을 검사하는 writer가 필요하다.

'''
    text+=f"상세 자료: {link(REPORT/'features.csv')} · {link(REPORT/'natural_language.csv')} · {link(REPORT/'issues.json')} · {link(ADR/'README.md')} · {link(RUN/'result.json')}\n\n"
    text+='''## 실측과 해석

| 지표 ID | 확인 결과 | 분모·환경·한계 |
|---|---|---|
| M01 | 기존 계약 40/40 통과 | 기존 사건 22 + shortcut 18; SQL 저장 제약 검사 |
| M02 | 기능·경계 63/63 예상 관측 | 후보 기능 55개 + SQL 단독 경계 8개. 8개는 잘못된 입력이 수락됨을 확인한 검사이므로 기능 정상 63개라는 뜻이 아님 |
| M03 | 맥락 없이 해석 9/20, 맥락 포함 17/20 | 같은 한 사건에서 만든 20발언; exact intent/대상/값 기준. 활성 MAIN 성능 비교가 아님 |
| M04 | 신규 해석 일치 8, 회귀 0, 양쪽 일치 9, 양쪽 불일치 3 | 후보-기준 +40%p = 85%-45%; 독립 사건 20개 아님 |
| M05 | 가상 답변 절차·출처 ID 4/4 일치 | 실제 법률 정확도 아님. 가정 표시 누락은 이 좁은 점수에 잡히지 않음 |
| M06 | 후보의 추가 확인/실행 거부 사례 4개 | NL03·09·15·16. NL09는 해석 점수상 통과했지만 처리 실패 |
'''
    s=r['summary'];lat=s['latency']['resolver_seconds']
    text+=f"| M07 | Qwen3.8 실제 호출 {s['usage']['calls']}회, 입력 {s['usage']['input_tokens']:,} / 출력 {s['usage']['output_tokens']:,} tokens | Parasail FP8, reasoning none, fallback·repair 0회; 원응답 usage |\n"
    text+=f"| M08 | provider 기록 비용 ${s['usage']['reported_cost_usd']:.8f} | 44개 원응답 cost의 합. 운영 비용 예측 아님 |\n"
    text+=f"| M09 | 해석 p50 {lat['baseline']['p50']:.2f}→{lat['GUARDED']['p50']:.2f}초, p95 {lat['baseline']['p95']:.2f}→{lat['GUARDED']['p95']:.2f}초 | 각 arm 20회, nearest-rank p95. 전체 RAG/첫 토큰/서빙 속도 개선은 미측정 |\n\n"
    text+='''## 만든 모의 데이터와 실제 실행 경로

가상의 내규·외규 각 1개를 만들었다. 실제 회사 규정이나 법령을 사용하지 않았다.
가상 내규는 국내=B·해외=A, 외규는 국내=D·해외=C라는 단순 절차로 구성했다. 긴급 예외는 별도 확인 조건이다.
각 원문에 SYNTHETIC 표시, 문서 ID·버전·내용 SHA-256을 보존했다.

원시 모의 자료→context SQL 23표 적재→질문/사실/실행/6판단 연결→사용자 정정→새 상태 및 영향 판단 기록→가상 원문으로 새 판단 생성→Qwen 답변 작성 순서로 실행했다.
질문 1은 T1, 질문 2는 T3이며 T2는 당사자 조건 발언이다. 따라서 질문 2를 발언 2로 오인할 수 있는 상황을 포함한다.
기능 검사는 각자 DB를 새로 만들며, 자연어 20개도 동일 초기 상태를 독립 복제해 실행했다. 20턴을 하나의 대화에서 연속 실행한 검증은 아니다.

문서 PDF 파싱·용어집·색인 생성은 기존 MAIN의 상류 단계로 동결했다. 이번 실험은 **기억 원장으로의 적재**부터 조사 상태의 활용을 검증한다. 모의 원문은 ADR의 RAW fixture로 명시 공급했으며 실제 DatasetPackage 반입·활성 원문 세대 교체를 하지 않았다.

context 저장은 실제 SQL 초안, 판단 원본은 모의 불변 JSON asset, 기존 요청 내부 의존성은 frozen native v5 WorkRepository로 각각 확인했다.
context에서 native 실행으로의 생산 경로는 연결하지 않았다. `WorkRepository.put/invalidate`의 재검토 동작은 실제 함수로 검사했지만 기존 Coordinator·BoundedSourceSession 전체를 실행한 것은 아니다.

shortcut SQL에는 질문 2행·실행·판단·원문·capsule·4검토·선택·실행 결속·packet·채택·작업 영수증 등 **19행**을 적재했다.
검토는 SYNTHETIC_REVIEW_FIXTURE이며 실제 법률 승인이 아니다. packet 전달과 SKIPPED는 모의 기록이다. 실제 모델 작업을 생략한 속도 실험은 하지 않았다.

## 기능별 판단

| 단계 | 잘 작동한 범위 | 확인된 문제·미연결 |
|---|---|---|
| 적재 | 질문→실행→판단→출처 연결, 지문 계산, append-only, sealed state | SQL만으로 권한·JSON 의미·hash 내용 검사를 보장하지 않음 |
| 식별 | 긴 세션 ID 보존, 다른 사용자/조직 분리, 권한 회수 | DevIdentity fixture. GENOS 실제 인증 adapter 미구현 |
| 사실·상태 | 현재 revision, 중복 요청, 이전 조건 보존, 가정 부모 고정 | 장시간 실행 lease와 운영 저장소·다중 리비전 동시 쓰기 미검증 |
| 특정 질문 정정 | G2 범위만 외규로 바꾸고 G1 내규 유지 | 명확한 사건 전체 정정은 모델이 지나치게 확인을 요구 |
| 의존 판단 | 범위 판단→근거 선택→결론만 재검토; 공통 당사자는 두 목표에 영향 | 새 조건의 자연어 해석이 막힘. 실제 native와 context 원장 간 일관성 연결 필요 |
| 새 판단·이력 | 새 D 판단과 원 B 판단·대체 관계 함께 보존 | 전체 이력 조회 UI·현재 유효 판단 투영 미구현 |
| user_wiki | 이유/출처 원본 조회, 확정 선호 최신값·만료·철회 | 사용자 의견 오분류, 이번 요청 형식 처리 미연결, 교차 세션 탐색 없음 |
| legal_wiki | 후보 보존·가상 승인/철회 경계 | 실제 연결 ID/버전 없는 후보 생성. 승인·게시 소비자는 모의 |
| 전달 | 상태·사실·이유·출처 필드와 NEEDS_CHECK 표시; 바이트 초과 거부 | F/T/J/E, 실제 READ/presentation, tokenizer·wire·schema 예산·필수 상태 분할 미검증 |
| shortcut | 실제 SQL 적재 사슬, 검토·조건·원문 버전·ACL별 거부 정책 fixture | 의미 탐색·현재 실행 주입·복수 부모 대응·작업 생략은 운영 미연결 |
| 복구 | 상태/outbox/head 트랜잭션, 전달 후 receipt 전 실패, 같은 event 재전달 | 파일 sink fixture. 실제 two-DB worker·lease·SSE 취소·게시 복구는 없음 |

## 실제 실패와 점수가 놓친 문제

| 사례 | 사용자 발언 | 실제 결과 | 원인과 영향 |
|---|---|---|---|
| NL03 | 이 사건 전체를 외규로 다시 검토해줘 | CLARIFY, 상태 변경 없음 | 여러 목표라는 이유로 명확한 전체 범위를 모호함으로 처리. 불필요한 확인과 진행 중단 |
| NL09 | 이번 답변만 표로 보여줘 | CONTINUE+preference=table, 실행 거부 | 모델 출력은 맞지만 일회성 형식 handler가 없음. 의도만 검사하는 점수의 한계 |
| NL15 | 긴급 사건이라는 새 조건도 고려해줘 | CLARIFY, 조건 기록 없음 | 새 사건 공통 조건과 질문별 조건의 기본 처리 정책이 불명확 |
| NL16 | 내 생각에는 추가 검토가 필요 없어. 내 의견으로 남겨줘 | UPDATE_USER_MEMORY, 실행 거부 | 사용자 입장과 지속 선호 혼동. 잘못된 전역 기억 저장은 차단됐지만 요청 미완료 |
| NL05 답변 | 해외 법인이라고 가정해봐 | A·내규 ID는 일치, 본문에 가정 표시 없음 | 내부 실제 상태는 국내로 유지했으나 답변은 “현재 상태(해외)”라고 표현. 저장 격리와 사용자 설명은 별도 검증 필요 |
| NL10 | 이 위키 연결이 틀렸어 | 임의 mock 버전 대상의 PROPOSED asset | intent 분류만 맞음. 정확한 연결 ID를 받지 않아 실제 수정 대상 해결 검증이 빠짐 |
| NL20 | 외규 변경은 이미 처리됐지? 당시 기록만 | 프롬프트상 완료 정정, DB에는 해당 정정 없음 | fixture의 맥락과 저장 원장이 다름. 조회의 저장→소비 일관성을 인증하지 못함 |

실패 후 prompt·코드·gold를 바꾸거나 모델을 재호출하지 않았다. 원시 결과는 그대로 보존했다.
NL05·10·20의 문제는 기존 17/20 및 4/4 점수를 수정한 재채점이 아니라, 좁은 채점 항목이 충족해도 전체 요구가 충족되지 않는다는 자체 검토 발견사항이다.

## SQL이 writer에 맡긴 8개 경계

같은 조직의 무권한 actor, 틀린 state JSON/hash, 다른 goal의 정정, 비16진수 64문자 hash,
run-state seq 공백, 증거 없는 APPLICABLE 판정, 같은 fact_id의 fact_key 변경,
같은 publication_ref의 상충 hash가 SQL에 수락됐다.
일부는 설계서가 이미 writer 책임으로 명시한 경계다. 이를 SQL 자체 오류 8개라고 부르지 않는다.
하지만 writer가 아직 생산 경로에 없으므로 현재 설계·SQL만으로 서비스를 활성화하면 해당 요구를 보장할 수 없다.
후보도 원발언 span과 모든 변경값의 의미 일치까지 보장하지 않는다. 이 경계는 실서비스 연결 전에 보강해야 한다.

## 세부 검사 63개

아래 PASS는 **각 검사가 의도한 관측을 얻었다**는 뜻이다. SQL 경계의 PASS는 잘못된 입력 수락을 확인했다는 의미다.
세부 관측 JSON은 CSV와 원시 결과에 있으며, 위의 기능 판단이 적용 범위를 함께 설명한다.

| ID | 단계 | 검사한 세부 기능 | 관측 |
|---|---|---|---|
'''
    for x in features:
        verdict='수락됨 → writer 필요' if x['group']=='sql_boundary' else '예상 동작 확인'
        text+=f"| {x['id']} | {GROUPS[x['group']]} | {x['korean_feature']} | {verdict} |\n"
    text+='''
## 구현 우선순위와 후속 검증

1. 자연어 명령 계약: CURRENT_CASE와 TARGET_GOAL, 일회 형식과 장기 선호, 사용자 입장과 agent 판단을 분리한다. 명시 발언과 patch의 일치를 검증한다.
2. 생산 context 경로: 신뢰된 identity→continuity→검증 writer→native 상태/판단→게시 envelope를 연결한다. 단순히 service의 필드 제거만 없애는 변경은 충분하지 않다.
3. 순차 멀티턴: 같은 DB에서 질문 두 개→조건 추가→범위 정정→가정→재시작→다른 세션 조회를 연속 실행한다. 이력 fixture를 프롬프트에만 넣지 않는다.
4. 실제 handoff와 게시: 필수 조건/예외·출처·변경 이력·실제/가정 표시와 wire 크기를 검사한다. 오래된 상태의 SSE와 publication을 중단한다.
5. 공통 위키와 shortcut: 실제 대상 ID/버전·review 권한을 결속한 뒤 경험 주입과 생략을 연결한다. 실시간과 후처리 실패·철회·원문 개정을 포함한다.

후속 후보 수정·재실행은 ADR-0591/GUARDED의 완료 결과를 부모로 하는 새 ADR에서 수행한다.
현재 후보는 Proposed, in-sample=true, decision_eligible=false다. 로컬 활성 릴리스 generation 37, PIPELINE 기본 경로, 데이터 CURRENT, GENOS 배포는 변경하지 않았다.
운영 활성화 전에는 위 실패와 연결 부족을 해결하고 별도 사건의 분리평가·동시성·전체 RAG 품질·첫 토큰/완료 지연을 측정해야 한다.
개발 일정과 실제 성능 개선은 미산정이다. 손익분기는 추가 상태/해석/전달 비용보다 실제 생략 작업의 비용이 커지는 조건이다. 이번 모의 SKIPPED 기록으로 그 값을 계산할 수 없다.

## 변경·확인 경로와 재현

실험 추가 범위는 ADR-0591, 연구 candidate, 전용 runner, 이 보고서다. 기존 source·SQL·service·PIPELINE은 변경하지 않았다.
raw 요청/response/schema/usage와 불변 후보 revision은 artifact manifest에 byte·SHA-256으로 기록했다.
자체 검토이며 독립 심사나 GENOS 현장 검증은 아니다. SQL fixture의 21행 요약 오기는 DB 계산 19행으로 명시했으며 원시 artifact는 덮어쓰지 않았다.

```bash
PYTHONPATH=02_BACKEND .venv/bin/python -B -m pytest -q \\
  05_TESTS/CONTRACTS/test_case_memory_schema_draft.py \\
  05_TESTS/CONTRACTS/test_shortcut_schema_draft.py
.venv/bin/python 06_TOOLS/run_tool.py adr_candidate.py validate \\
  02_BACKEND/lawrag/research/candidates/adr_0591/guarded-context
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate \\
  --path 04_EXPERIMENTS/ADR/ADR-0591-case-memory-functional-mock-probe --final
```

실제 실행 명령은 `PYTHONPATH=02_BACKEND .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0591/run_probe.py`였다.
완료된 run을 덮어쓰지 않도록 runner는 재실행을 거부한다. 새로운 모델 실행은 새 ADR·run 동결 후 수행한다.
'''
    (REPORT/'README.md').write_text(text)
    # Standard-compliant case documentation with full exact provider texts inline.
    m=json.loads((ADR/'실험/manifest.json').read_text());question_index=[]
    for x in r['natural_language']:
        q=next(q for q in m['questions'] if q['case_id']==x['id']);file=ADR/'실험'/q['file']
        body=f"# {x['id']} — 모의 기억 명령\n\n## 1. 실행 메타\n\nrun-001 · baseline/GUARDED · qwen/qwen3.8-27b · Parasail FP8 · 합성 fixture · 1회/arm · exact payload 저장.\n\n## 2. 사용자 질문 원문\n\n{x['utterance']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n"+block(x['gold'])
        body+='## 4. 제품 입력을 구성한 원값\n\n'
        for arm in ['baseline','GUARDED']:
            body+='### '+arm+'\n'+block(json.loads((RUN/'natural-language'/x['id']/arm/'input.json').read_text()))
        body+='### 회수·탈락 단계 원장 — run·arm별\n\n법률 원문 검색·후보 가지치기 없음. 원문 mock document는 정확한 범위에 따라 명시 공급. 기억/맥락 소비 검사이며 canonical article-root 회수율은 해당 없음.\n\n'
        body+='## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n'
        calls=sorted(p for p in (RUN/'provider').glob('call-*') if '-'+x['id']+'-' in p.name)
        for p in calls:
            body+='### '+p.name+'\n\n'
            for name in ['binding.json','request.json','validation-schema.json','response.json','output.json']:
                if (p/name).exists():body+='#### '+name+'\n'+block(json.loads((p/name).read_text()))
        body+='## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n첫 명령 해석이 resolver 역할이다. 원문은 위 제품 호출에 포함. 사전 지정 4사례의 새 답변 호출도 위에 포함. 별도 verifier/repair/judge 0회.\n\n'
        body+='## 7. 채점 호출과 반복 판정\n\n사전 동결 gold 필드의 결정론적 exact 비교. gold는 모든 제품 호출 후 로드했다. judge 호출·다수결 없음.\n\n'
        body+='## 8. 사례 최종 판정\n'+block(x['arms'])
        if x['id'] in ['NL03','NL09','NL15','NL16','NL05','NL10','NL20']:
            body+='자체 검토 발견사항은 '+link(REPORT/'README.md',file.parent)+'의 사례별 분석을 함께 본다. 해석 일치가 전체 처리 완료를 뜻하지 않는다.\n'
        file.write_text(body)
        a=x['arms']['baseline']['exact_match'];b=x['arms']['GUARDED']['exact_match'];paired='둘 다 일치' if a and b else '후보만 일치' if b else '기준만 일치' if a else '둘 다 불일치'
        question_index.append(f"| {q['number']} | {x['id']} | {a} | {b} | {x['arms']['GUARDED']['dispatch']['status']} | {paired} | [{q['file']}]({q['file']}) |")
    (ADR/'실험/README.md').write_text('# ADR-0591 질문별 결과\n\n20개 합성 발언, 각 arm 1회. 모델해석과 실행 상태를 구분한다.\n\n| 번호 | 사례 | 맥락 없음 일치 | 맥락 있음 일치 | 후보 실행 | paired | 원문 |\n|---|---|---|---|---|---|---|\n'+'\n'.join(question_index)+'\n\n17/20 대 9/20. 신규 일치 8, 회귀 0. 법률 retrieval ledger는 해당 없음. 자세한 설계와 결과는 [manifest.json](manifest.json).\n')
    # Complete manifests only by reference to the original raw result.
    m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
    m['results'].update(status='complete',by_arm={'baseline':s['commands']['baseline'],'GUARDED':s['commands']['GUARDED']},
        comparisons=[{'metric':'exact command match','baseline':9,'candidate':17,'denominator':20,'delta_pp':40,**s['paired']}],judge_disagreements=0,
        usage=s['usage'],latency=s['latency'],error_taxonomy=[{'type':'scope_actor_mismatch','cases':['NL03','NL15','NL16'],'note':'case scope, new condition and user-position command classification'},
                                                        {'type':'other','cases':['NL09'],'note':'correct intent but missing request-local formatting handler'},
                                                        {'type':'condition_exception','cases':['NL05'],'note':'hypothetical disclosure omitted, outside narrow procedure/source grade'}])
    dump(ADR/'실험/manifest.json',m)
    front=(ADR/'README.md').read_text().split('---',2)[1]
    sections=[
      ('결정 요약','Proposed 연구 후보로 유지한다. 63개 관측 검사와 20개 실제 Qwen 명령 비교를 완료했다. 맥락 포함 해석은 17/20, 네 사례는 처리까지 완료되지 않았다. 로컬 MAIN·GENOS·데이터 CURRENT는 unchanged다.'),
      ('문제와 변경 전 구조','사건 SQL r2와 shortcut SQL r2만 존재하며 생산 continuity 소비자는 없다. 기존 service는 GENOS 사용자/세션 ID를 제거한다. 현행 활성 generation37과 전체 MAIN 상류 파이프라인을 동결한 채 격리 후보를 검사했다.'),
      ('가설과 사전 판정 기준','정확한 사건 맥락과 검증 writer가 질문별 정정/이력/권한/버전 경계를 구현하고 대상 해석을 돕는다는 가설이다. 무권한/잘못된 목표/오래된 원문 채택 0, 전체 해석20/20을 목표로 사전 동결했다. 의미 목표는 충족하지 못했다.'),
      ('실험 설계','baseline은 같은 prompt의 context-free 명령 해석 및 SQL 단독 경계다. GUARDED는 같은 SQL·Qwen·20발언에 정확한 맥락과 격리 writer를 붙였다. 홀짝 교차 arm 순서, 1회/arm, 4개 사전 지정 새 답변, 모델44회. 기준답변은 호출 종료 후 grader만 읽었다. 활성 API 대비 실험이 아니다.'),
      ('데이터·모델·재현성','가상 내규·외규2개, 3발언·2질문·6판단 및 사용자/권한/예외/철회 fixtures. source는 모두 SYNTHETIC. DatasetPackage RAW 파서나 실제 법률 품질은 대상 밖이다. qwen/qwen3.8-27b, Parasail FP8 only, reasoning effort none, fallback/repair0. design/freeze.json과 candidate rev-001 SHA에 결속.'),
      ('결과','관측 검사63/63: 후보55 + SQL writer 경계8. 해석 baseline9/20, GUARDED17/20. 후보만8·기준만0·둘다9·둘다불일치3. 가상 절차·source ID4/4. NL09 실행 거부와 NL05 가정 표시 누락은 좁은 점수에서 드러나지 않는다.'),
      ('사례별 오류 분석','NL03 사건 전체 정정과 NL15 새 조건은 지나친 확인 요청. NL16은 의견/개인 기억 혼동. NL09는 일회 형식 실행 handler 없음. NL05는 가정 표시 누락. NL10 위키 대상 ID 없고 NL20의 정정 이력은 prompt/DB가 불일치한다. 자세한 자체 검토는 상세 보고서 및 issues.json에 보존한다.'),
      ('비용·지연·회수 규모',f"실제 모델44회, 입력{s['usage']['input_tokens']:,}·출력{s['usage']['output_tokens']:,}tokens, provider 비용${s['usage']['reported_cost_usd']:.8f}. resolver p50 {lat['baseline']['p50']:.2f}/{lat['GUARDED']['p50']:.2f}초, p95 {lat['baseline']['p95']:.2f}/{lat['GUARDED']['p95']:.2f}초. 실제 검색·작업 생략과 전체 RAG 지연 미측정. 법률 article-root 회수 원장은 not_applicable."),
      ('해석','사건 맥락은 정확한 질문·판단 ID를 찾는 데 도움이 됐다. 저장 계약 통과가 자연어 기능 완성으로 이어지지는 않는다. 위키/승인/dispatch fixture를 실제 운영 기능으로 해석하지 않는다.'),
      ('한계와 일반화 가능 범위','한 seed 사건에서 파생한 in-sample probe다. 인증·법률 review·wiki·outbox sink 모의, sequential CAS, 실제 source selection/claim agent 미연결. 직접 SQL 경계 검사는 writer 책임 일부를 보여준다. 20개 독립 사건의 일반화 점수나 GENOS 성능 인증이 아니다. 행 수21 요약 오류는 실제 DB19행으로 별도 report-audit에 기록했으며 원시 결과는 보존했다.'),
      ('운영 결정·롤백 조건','승격하지 않는다. phase=probe, in_sample=true, decision_eligible=false, main_wiring=unchanged. 변경은 격리 후보·runner·mock DB·ADR·보고서에 한정. 후속 수정은 완료 GUARDED arm에서 새 ADR. 원자료와 활성 MAIN rollback 상태는 유지했다.'),
      ('재현 명령','`PYTHONPATH=02_BACKEND .venv/bin/python -B 06_TOOLS/EXPERIMENTS/adr_0591/run_probe.py`로 실제 실행했다. 완료 run 재실행은 overwrite 방지로 거부된다. 후보/ADR validate와 원문 artifact 해시로 검증하며 새 모델 실행은 새 ADR에서 수행한다.')]
    body='---'+front+'---\n\n# ADR-0591 사건 기억 기능별 모의 실험\n\n'
    for i,(title,content) in enumerate(sections,1):body+=f'## {i}. {title}\n\n{content}\n\n'
    body+='상세 결과: '+link(REPORT/'README.md',ADR)+' · '+link(RUN/'result.json',ADR)+' · [질문 인덱스](실험/README.md).\n'
    (ADR/'README.md').write_text(body)
    index=ROOT/'04_EXPERIMENTS/ADR/README.md'
    old=index.read_text()
    if 'ADR-0591-case-memory-functional-mock-probe/README.md' not in old:index.write_text(old+'\n- [ADR-0591 — 사건 기억 적재부터 활용까지 모의 기능 검증](ADR-0591-case-memory-functional-mock-probe/README.md) — Proposed, MAIN unchanged.\n')
    # Every file and completed DB is bound; report/runner artifacts are included.
    paths=[p for p in ADR.rglob('*') if p.is_file() and p!=ADR/'artifacts/manifest.json' and not p.is_relative_to(ADR/'실험') and p.name!='README.md']
    paths += [p for p in REPORT.rglob('*') if p.is_file()]
    paths += [p for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_0591').glob('*.py')]
    paths += [p for p in (ROOT/'02_BACKEND/lawrag/research/candidates/adr_0591/guarded-context').rglob('*') if p.is_file()]
    files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen synthetic experiment evidence / code / report','contains_raw_prompts_and_outputs':p.name in {'request.json','response.json','output.json','input.json'}} for p in sorted(set(paths))]
    dump(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0591','created_at':m['reservation']['created_at'],'files':files})
    print(REPORT/'README.md');print('artifact files',len(files),'baseline bindings unchanged',all(audit['baseline_binding_unchanged'].values()))

if __name__=='__main__':main()
