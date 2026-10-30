from common import *
f=read(DES/'freeze.json');b=read(DES/'baseline.json');active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==119 and active['release_id']==RELEASE and release['files']==f['files']
assert all(sha(ROOT/n)==h and sha(ROOT/release['code_root']/n)==h for n,h in f['files'].items())
consumers={m:read(ART/f'consumer-active-{m}.json') for m in ('off','on','db')};assert all(v['passed'] for v in consumers.values())
old={x for x in (ROOT/'09_ARTIFACTS/AUDITS/20261029-source-accordion-main118/adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')}
new={x for x in (OUT/'adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')};assert old==new,(new-old,old-new)
from collections import Counter
reg=read(ART/'regression-comparison.json');nc=sum(len(v['checks']) for v in consumers.values())
put(OUT/'completion.json',{'active':active,'release_manifest':bind(ROOT/active['manifest_path']),'serving_files':487,'changed_files':96,'product_config_files':65,'pin_files':31,'new_files':21,'feature_contracts':348,'excluded_fixture':1,'regression':reg,'selected_service_checks':nc,'selected_service':{k:bind(ART/f'consumer-active-{k}.json') for k in consumers},'candidate_service_checks':34,'all_working_and_selected_files_equal':True,'global_graph_existing_errors':len(new),'global_graph_new_errors':0,'external_model_calls':0,'quality_certified':False,'genos_deployed':False,'input_diagnosis':bind(ART/'input-size-findings.json'),'prompt_shortening_implemented':False,'rollback_release':b['active']['release_id'],'rollback_caveat':'Old MAIN118 readers cannot be assumed compatible with compact journals; after new compact writes keep new readers and use GENOS_JOURNAL_STORAGE=plain to disable further compact writes.'})
report=f'''누적 작업 MAIN119 반영과 입력 길이 확인 — 2026-10-29

결과
로컬 MAIN119 / {RELEASE}를 공식 prepare/apply로 선택했다.
실제 service가 선택한 코드와 검증한 후보·작업 폴더의 487파일 해시가 모두 같다.
MAIN118 대비 기존75파일 변경·신규21파일 = 총96변경(제품/설정65+pin31).
새 실모델 호출0·GENOS 현장 배포0·Git commit/push0·메일0.
입력 크기는 확인했으며 이번 반영에서 입력 축약을 새로 구현하지 않았다.

반영한 완료 작업
1. 필요한 원문 선언의 안정ID·선택/확보/판단/최종 해결·제외·미해결 연결.
2. 잘못된 행동이 거절되어도 독립 검증한 필요 선언을 먼저 보존. 거절 행동과 판단은 승인하지 않음.
3. 감독의 독립 조사 경로 복구, NOT_USED의 필요한 change_review 필수화, ROLE_ONLY 구분, 핵심gap 연결.
4. 원문·입출력·판단·실패 기록의 무손실 압축 저장과 저장공간 입장 제한, 기존 평문 읽기.
5. 도메인 프로필·원래 의견/정정 구조화·기존 용어집 연결·누적/컴파일·내용 승인/게시·RAG 연결, 관리 CLI/UI.
6. MAIN118 출처 펼치기와 accepted-content-v1 전체 답변 보존 유지.
비활성 domain/business 템플릿2개를 engine pin에 포함했다. 온톨로지 기본OFF·실제 게시 데이터 미변경.
서버 참조 형제 자동 확장 호출은 제외된 상태다. 필요한 조문·여러 범위는 LLM이 선택한다.
실패한 별도 advisory 검토1201·실모델 미실행 portable JSON-object 전송1207·병행 R12 연구1208을 자동 채택하지 않았다.

검증
누적 기능 계약 고유348통과·기존 actual007 준비검사1제외.
최초346통과/2준비오류: import한 unified fixture의 ROOT가 작업 경로에 남아 workflow 결속이 거절됐다.
검사기의 ROOT만 고쳐 같은 제품·fixture로 해당2개 통과. 처음 실패 기록은 남겼다.
동일254회귀: MAIN118/후보 각각228통과·26실패, 항목별 동일·새실패0.
제품 전체가 모두 통과했다는 뜻이 아니며 기존26실패를 통과로 계산하지 않았다.
후보 서비스34확인. 실제 선택 service OFF/ON미설정/ON빈DB 총{nc}확인·HEALTH3·모의HTTP3 통과.
코드/데이터/예산/공급자/원문 표시·저장 호환을 확인했고 실제 외부 모델에는 전송하지 않았다.
서비스 추가 저장검사의 최초 준비 코드가 일반 sqlite3.Connection을 사용한 오류는 보존하고 제품 connect/initialize API로 정정했다.
ADR1209 최종검사 통과. 전역graph 기존{len(new)}오류 동일·새오류0.
법률 의미 정확성·공급자 공백/UNKNOWN 개선·새007/009 성공을 인증하지 않았다.

입력 길이: 저장된 실제 전송49요청 대조
단위는 유니코드 문자와 compact JSON 문자이며 토큰 수/패킷 캡처 바이트가 아니다.
messages와 response_format을 분리했다. canonical의 축약 전 크기를 실제 전송 크기로 세지 않았다.
각 실행의 질문·탐색 상태가 달라 아래 최대값은 통제된 성능비교가 아니다.

실행       요청수  최대 전체JSON자  system자  user자  출력schema자
ADR1198       7       105958         3927     66605       27232
ADR1200      10        93813         3927     53566       30399
ADR1201      14       112690         3927     71975       29342
ADR1203      11       118262         3927     78801       27626
ADR1205       4        73798         4152     40336       24627
ADR1206       3       247213         7924     70323      159226
전체에는 JSON 키·escaping·요청 옵션도 있어 system+user+schema의 합과 정확히 같지 않다.

원인 A: 일반 RAG 조사 메뉴와 누적 상태
1203 최대 요청에서 연결범위 선택지16502자·원문14848자·도구메뉴12947자·이미 제시한 읽기5506자·참조4317자·읽기이력3848자였다.
시스템 지시문3927자만 길어진 것이 아니다. 실제 필요한 원문 외 선택 메뉴/상태 정보의 비중이 크다.
기존 compact_model_input과 local_gemma.provider_request의 schema factoring은 이미 적용된다.
이 기존 축약이 꺼졌다고 판단하지 않는다. 조사 범위와 이력이 늘어나는 잔여 구조를 줄여야 한다.

원인 B: 도메인 구조화 생성 스키마의 반복
1206 최대 요청의 출력 schema가159226자다. profile_schema.node_schema가 모든 node kind마다 같은 slots와 locator schema를 반복 생성한다.
raw판단 입력은1829자인데 용어집 후보9개 묶음이63983자다. 그중 detail 합50151자, entry_links4440자, card3823자, 반복 binding2754자다.
glossary_binding.restore가 inspect 전체와 entry_links·card·binding을 모두 담고 authoring_model이 이를 그대로 전달한다.
따라서 후보 개수만9개로 작아도 입력은 크다. 일반RAG와 별도의 authoring 경로다.

추가 성장 경로: 새 필요 이력
need_continuity.record는 같은 필요ID에서도 decision_key/답변초안/다음변화/제안행동 등 선언 이력을 누적한다.
investigation_supervisor의 declared_needs와 최종 needs가 이 전체 이력을 deepcopy로 전달한다.
같은 필요1개에 서로다른 선언슬롯을 추가한 모의 저장크기는1회480자→2회805자→3회1130자→4회1455자였다.
이는 모델 실제 요청/토큰 실험이 아니라 성장 경로 검사다. 현재 판단을 넘어 과거 선언 전부가 전달될 수 있다는 뜻이다.
실제1205는 수정 전 필요 유실 때문에 MN0이었으므로 새 누적이 그때의 긴입력을 만들었다고 설명하면 틀린다.

수정 우선순위
1. 도메인 출력schema에서 동일 slot/locator를 공통 $defs/$ref로 표현하되 서버 strict검증과 생성 의미를 유지하는 별도 전송 검증.
   1207에159226→12287자 동등표현 오프라인 근거가 있으나 JSON-object 전송 변경도 포함하고 실모델 미실행이다. 전체를 그대로 반영하지 않았다.
2. 용어집의 완전한 inspect 결과·해시·판본은 서버 영수증에 보존하고, 첫 구조화에는 필요한 개념ID/정의/상태를 투영. 상세가 필요할 때 정확한ID로 추가 조회.
3. 필요의 안정ID·문장·쟁점·연결목표·상태와 미승인행동 구분은 매 단계 유지하고, 과거 선언 전체는 원장에 보존하면서 모델 입력의 중복 이력만 줄이는 명시적 투영.
4. 연결범위·도구 메뉴는 현재 선택 가능한 ID와 상태를 중복 없이 표현. 복수 선택/구간/제외·원문 확보 및 최종 대조는 유지.
필요 원문을 일괄 잘라내거나 미해결 필요를 삭제해서 입력 길이를 줄이면 이번 연결 계약이 훼손된다.

속도/실패 해석
입력이 크다는 사실과 응답179~180초 UNKNOWN의 원인 확정은 다르다.
이전 요청지연 진단에서도 비슷한 전송 크기/동일 원문을 가진 정상37.512초와 미완료179.699초 기록이 있었다.
스키마·크기 단순화의 효과는 별도 통제 검증이 필요하며 이번 새모델0으로 속도나 법률 품질 개선을 약속하지 않는다.
이전 진단: 09_ARTIFACTS/AUDITS/20261029-model-latency-diagnosis/요청지연_원인진단.txt

운영/롤백
MAIN118 / source-accordion-20261029-r1 릴리스는 보존했다. 새 압축기록이 없는 경우 공식 rollback --confirm-main 경로로 복귀할 수 있다.
압축기록이 만들어진 뒤에는 이번 reader를 유지하고 GENOS_JOURNAL_STORAGE=plain으로 새 압축 쓰기만 중지한다.
MAIN118의 옛 reader로 새 압축 journal을 읽을 수 있다고 보장하지 않는다. 원장/실패 기록을 삭제하지 않는다.
장기 실행 서비스는 재시작해야 새 binding을 사용한다. 이번 선택service는 새 프로세스로 확인했다.
기존 GENOS MAIN118 ZIP은 이번 MAIN119의 배포물로 간주하지 않는다. 현장 배포는 하지 않았다.

근거
04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit/README.md
04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit/artifacts/design/integration.json (변경96개 전후hash)
04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit/artifacts/input-wire-size-audit.json (49요청 원본경로/hash·항목크기)
04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit/artifacts/input-size-findings.json (원인코드/hash·성장검사)
09_ARTIFACTS/AUDITS/20261029-cumulative-main119-input-audit/completion.json
'''
(OUT/'메인반영과_입력길이_진단.txt').write_text(report)
note=f'''<!-- CUMULATIVE_MAIN119_INPUT_AUDIT -->
**2026-10-29 — 누적 작업 MAIN119·입력 길이 진단:** [반영·진단 TXT](09_ARTIFACTS/AUDITS/20261029-cumulative-main119-input-audit/메인반영과_입력길이_진단.txt) · [ADR1209](04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit/README.md). 사용자 요청으로 **MAIN119 / cumulative-contracts-20261029-r1**을 선택했다. 필요ID/거절응답 관찰·감독 복구·목적변경/gap·무손실저장/용량제한·도메인 작성/승인/컴파일 누적 작업 반영, 출처펼치기/accepted-content 유지. **487파일/MAIN118대비96변경(제품설정65+pin31), 작업·후보·선택서비스 동일. 기능348통과·1제외, 동일254회귀228통과/기존26실패·새실패0. 후보34·선택서비스{nc}(OFF/ON미설정/ON빈DB), HEALTH3·모의HTTP3 통과.** 초기검사ROOT/저장API 준비오류 보존·정정. **실제49전송 입력 조사: 도메인최대247213자=system7924/user70323/schema159226, 용어집9후보63983자(detail50151). 일반RAG최대118262자, 연결메뉴/도구/이력 비중 큼.** 신규need선언 전체 복사 성장경로는 모의확인·과거1205주원인 단정금지. 기존 wire축약 유지·입력축약 새적용0·UNKNOWN인과미입증. 미실행1207전송/실패1201검토/병행1208연구는 미채택. **새실모델0·007/009재시험0·GENOS/Git/메일없음·온톨로지기본OFF/데이터유지·법률품질인증없음.** ADR최종통과·graph기존{len(new)}오류/새0. MAIN118 보존하되 압축기록 생성 후 reader다운그레이드 금지, 새reader+GENOS_JOURNAL_STORAGE=plain 사용.
<!-- /CUMULATIVE_MAIN119_INPUT_AUDIT -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;t=p.read_text();assert '<!-- CUMULATIVE_MAIN119_INPUT_AUDIT -->' not in t and heading in t;p.write_text(t.replace(heading,heading+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';lines=p.read_text().splitlines(True);lines.insert(2,'- [ADR1209 누적 작업과 입력 길이](ADR-1209-cumulative-main-input-audit/README.md) — MAIN119·487파일·기능348·새회귀0·실제49입력진단, 축약은 후속.\n');p.write_text(''.join(lines))
print('MAIN119 verified;',nc,'selected service checks; report written; no new models')
