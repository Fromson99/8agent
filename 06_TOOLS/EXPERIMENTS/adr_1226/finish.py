from common import *
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261029-main122-authoring-revalidation'
a=read(ART/'audit.json');x=read(ART/'live/execution.json');b=read(DES/'baseline.json');f=read(DES/'freeze.json');r=read(RUN/'result.json')
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
assert all(sha(ROOT/n)==h and sha(ROOT/b['release']['code_root']/n)==h for n,h in b['release']['files'].items())
assert sha(ROOT/b['data_path']/'manifest.json')==b['generation_manifest_sha256']
assert (OUT/'adr-final.log').read_text().startswith('OK:')
old={s for s in (ROOT/'09_ARTIFACTS/AUDITS/20261029-cumulative-authoring-main122/adr-graph.log').read_text().splitlines() if s.startswith('ERROR:')}
new={s for s in (OUT/'adr-graph.log').read_text().splitlines() if s.startswith('ERROR:')};assert old==new
providers=sorted({c['actual_provider'] for c in a['wire_calls'] if c['actual_provider']})
put(OUT/'completion.json',{'main':b['active'],'main_unchanged':True,'working_selected_candidate487_identical':True,'data_unchanged':True,'product_changes':0,'calls':a['calls'],'providers':providers,'provider_switches':x['provider_switches'],'seconds':a['seconds'],'cost_usd':a['reported_cost_usd'],'normalizations':a['normalization_audit'],'previews':a['previews'],'complete_responses':a['complete_responses'],'error_null':a['error_null_count'],'unknown':a['unknown'],'predeclared_whole_success':False,'knowledge_approved':False,'published':False,'global_graph_existing_errors':len(new),'global_graph_new_errors':0,'result_path':str((RUN/'result.json').relative_to(ROOT)),'audit_path':str((ART/'audit.json').relative_to(ROOT)),'content_review_path':str((ART/'content-review.json').relative_to(ROOT))})
report=f'''MAIN122 정규화·누적 실제 재검증 결과 — 2026-10-29

결론
이번에는 새 정규화2/2 → 첫 누적 저장 → 두 번째 누적 저장 → 두 판본 컴파일까지 모두 완료됐다.
다만 내용 기준은 미통과다. 이유·목적 분류 오류와 취득 의무를 조건으로 바꾸는 의미 오류가 남아 전체 ADR1226은 Rejected로 기록했다.
제품 코드·MAIN122·데이터·모델·온톨로지 기본OFF는 바꾸지 않았다. 지식 내용 승인/게시도 하지 않았다.

실제 실행
선택 MAIN122 / cumulative-authoring-20261029-r1의487파일과 작업/동결후보를 모두 대조했다.
연구용 전송기1파일만 더한488파일 격리 사본에서 제품의 DomainWorkflow·authoring·검증·저장·컴파일 경로를 실행했다.
이전 정규화 결과를 재사용하지 않고 같은 원래 판단2조각을 새 저장소에 입력했다.
동일 승인 공개원문5unit·용어9후보, Qwen3.8·{', '.join(providers)}. 기준답변/진단 기대는 제품 입력에 넣지 않았다.
순서: 정규화A1회 → 누적A최초/보완2회 → 정규화B1회 → 누적B1회 = 실제5회.
최대9회 한도 안에서 종료했다. 429전환0, error/null0, UNKNOWN0, 자원중단0이다.
전체 {a['seconds']:.3f}초(약3분8초), 보고 비용 {a['reported_cost_usd']:.8f}달러.

구조·상태·인용 결과
A3/B7=입력10구간을 모두 연결했고, A12/B19=인용31좌표를 원문 및 조립 영수증과 대조했다.
두 정규화 모두 최초 응답으로 canonical 저장됐다. 실제 전송 schema를 펼친 결과는 요청 schema와 같고 messages/context도 일치했다.
A 누적 최초는 이전 그래프가 없는데 SAME을 선택해 거절됐다. 새 오류 안내를 받은 기존1회 보완에서 NEW로 수정됐다.
같은 보완에서 REQUIRES_CONDITION 간선도 EFFECT→CONDITION 방향으로 바뀌어 전체 검증을 통과했다.
A: 첫판본·3노드/2간선/2목적 경로·관찰2개·비교이력1개.
B: 둘째판본·7노드/5간선/2목적 경로·관찰3개·비교이력2개.
B는 이전 n-001~003과 간선들을 그대로 유지하고 n-004~007/새간선3개를 추가했다. 삭제0이며 두번째 누적은 최초 응답으로 통과했다.
두 판본의 저장 컴파일 패키지를 독립 재컴파일해 동일함을 확인했다.
두 preview의 목적 경로는 미확인 검토 슬롯 때문에 모두 PARTIAL이다. 완성·승인된 법률 지식으로 해석하지 않는다.

남은 내용 오류1 — 원래 기록에 없는 이유/목적
원래 A/B 입력에는 명시적인 reason/purpose가 없다.
하지만 A의 본문 관찰과 식별자 관찰, B의 본문 관찰 모두 statement 또는 식별자를 reason/purpose에도 복사했다.
총6필드를 PRESENT로 기록했다. 정확한 원문 문구를 인용했더라도 그 문구가 원래 기록의 이유/목적이었다는 뜻은 아니다.
이전의 구조값1 대신 이번에는 본문/식별자를 넣었으며, 같은 종류의 의미 분류 오류가 재현된 것이다.

남은 내용 오류2 — 취득 의무의 조건화
A의 누적 비교는 원래 '취득하는 경우' 의견을 SUPPORTED로 인정했다.
비교 이유에서 취득 자체를 독립된 의무가 아니라 보유 의무의 전제로 설명했다.
n-001은 '취득하는 경우'라는 CONDITION이고, n-002의 action은 '보유'만 남았다.
EFFECT의 전체 statement에는 원래 '취득하여 ... 보유하여야 한다'가 보존됐지만, typed action/condition과 비교 해석은 취득 의무를 보존하지 못했다.
B는 이전 그래프를 정확히 보존했기 때문에 이 잘못된 해석도 그대로 남았다.
따라서 원문 전달·인용·저장 성공으로 법률 의미 정답을 인증하지 않는다.

B의 세부 기준
사모 취득(n-005), 상장예비심사 신청일부터 신규상장 신청일까지의 취득시기(n-006), 인수계약 잔여 수량 포함(n-007)이 실제 원문 S3~S5에 연결되어 둘째판본에 저장됐다.
이 세 기준의 보존과 A의 일반 의무 해석 실패는 구분한다.

검증 범위와 보존
신규 실모델5회와 실제 저장/원문/요청/컴파일 검증이다. 이전106개 기술검사를 새로 실행한 것으로 세지 않는다.
코드와입력준비 사전 검증, 자원중단 모의검사8개, 실제authoring 전송경계2개도 확인했다.
RAM최소 {a['resource']['min_available_GiB']:.3f}GiB, 프로세스RSS최대 {a['resource']['peak_rss_MiB']:.3f}MiB, 호스트swap증가0.
환경 확인의 git diff 공백 오류는 기존 작업 상태와 같으며 임의 정리하지 않았다.
원래 실패·모든 요청/응답·관찰·두 누적판본·조립/컴파일 영수증을 무손실 보존했다.
MAIN122 선택 포인터와487파일, 데이터manifest가 전후 동일하다. GENOS현장·Git·메일·전체CM007/009 실행은 없다.
ADR최종검사 통과. 전역graph 기존16오류 동일·새0.

해석
마지막 구조·참조 보완으로 이번에는 전체 저장 흐름을 완료했다. 하지만 알려진2사례의 한 번 실행이며, 일반화·속도 인과효과·법률품질 개선율을 주장하지 않는다.
이유/목적의 원래기록 분류와 의무/조건 해석은 후속 수정·검증이 필요한 별도 문제다.

근거
04_EXPERIMENTS/ADR/ADR-1226-main122-authoring-revalidation/README.md
04_EXPERIMENTS/ADR/ADR-1226-main122-authoring-revalidation/artifacts/run-001/result.json
04_EXPERIMENTS/ADR/ADR-1226-main122-authoring-revalidation/artifacts/audit.json
04_EXPERIMENTS/ADR/ADR-1226-main122-authoring-revalidation/artifacts/content-review.json
09_ARTIFACTS/AUDITS/20261029-main122-authoring-revalidation/completion.json
'''
(OUT/'재검증결과.txt').write_text(report)
note=f'''<!-- MAIN122_AUTHORING_REVALIDATION_1226 -->
**2026-10-29 — MAIN122 실제 정규화·누적 재검증:** [결과 TXT](09_ARTIFACTS/AUDITS/20261029-main122-authoring-revalidation/재검증결과.txt) · [ADR1226](04_EXPERIMENTS/ADR/ADR-1226-main122-authoring-revalidation/README.md). 선택/작업/후보487동일·승인원문5/판단2/용어9로 **새정규화2/2(10구간·31좌표)→누적2판본→컴파일2 완료**, 실제5물리·Parasail5/stop5/error-null0·UNKNOWN0·전환0, {a['seconds']:.3f}초·보고{a['reported_cost_usd']:.8f}달러. A최초SAME/base없음 거절→기존1회보완NEW/간선정정→저장, B최초통과·기존3노드보존+4추가·이력2/관찰3. 원문·조립영수증/전송/재컴파일동일. **내용기준미통과/Rejected:** 두정규화가본문·식별자를미기록reason/purpose에복사(6필드), A취득의무를보유의전제조건으로해석해SUPPORTED·action보유만, B에서도유지. 세부취득방법/시기/잔여수량기준은둘째판본에보존. 모든preview경로PARTIAL·지식승인/게시0. **제품/MAIN122/데이터불변·GENOS/Git/메일/전체007·009없음**. 106기술검사재실행아님·법률품질인증없음. RAM최소{a['resource']['min_available_GiB']:.3f}GiB/RSS{a['resource']['peak_rss_MiB']:.3f}MiB/swap증가0, ADR최종통과·graph기존16/새0.
<!-- /MAIN122_AUTHORING_REVALIDATION_1226 -->

'''
for name,heading in [('AGENTS.md','# 8-AGENT 작업 가이드\n\n'),('GENOS.md','# GENOS — 질문과 작업의 진입점\n\n')]:
 p=ROOT/name;t=p.read_text();assert '<!-- MAIN122_AUTHORING_REVALIDATION_1226 -->' not in t and heading in t;p.write_text(t.replace(heading,heading+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';lines=p.read_text().splitlines(True);lines.insert(2,'- [ADR1226 MAIN122 실제 재검증](ADR-1226-main122-authoring-revalidation/README.md) — 새정규화2·누적2·컴파일2, 실제5회·내용미통과·MAIN122유지.\n');p.write_text(''.join(lines))
print('Revalidation documented; MAIN122 unchanged; structural2/2, content rejected')
