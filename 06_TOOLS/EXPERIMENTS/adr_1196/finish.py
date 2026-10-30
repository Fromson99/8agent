from common import *
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-accepted-answer-main117'
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);f=read(DES/'freeze-rev-002.json')
assert active['generation']==117 and active['release_id']=='accepted-answer-20261029-r1'
assert release['files']==f['files']
consumers={m:read(O/('consumer-'+m+'.json')) for m in ('off','on','db')}
assert all(v['passed'] for v in consumers.values())
checks=sum(len(v['checks']) for v in consumers.values());reg=read(ART/'regression-comparison.json');saved=read(ART/'saved-render-diagnostic.json')
old_errors={x for x in (ROOT/'09_ARTIFACTS/AUDITS/20261029-main116-live-test/adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')}
new_errors={x for x in (O/'adr-graph.log').read_text().splitlines() if x.startswith('ERROR:')}
assert new_errors==old_errors,(new_errors-old_errors,old_errors-new_errors)
result={'active':active,'release_manifest':bind(ROOT/active['manifest_path']),'candidate':f['candidate_revision'],'serving_files':466,'changed_files':37,'product_config_files':6,'pins':31,'technical_contracts':116,'working_contracts':116,'regression':reg,'selected_service_checks':checks,'selected_service_modes':{k:{'passed':v['passed'],'checks':len(v['checks']),'model_calls':v['network_model_calls'],'mock_http_calls':v['mock_http_calls']} for k,v in consumers.items()},'saved_diagnostic':saved,'new_external_model_calls':0,'cm007_live_retested':False,'cm009_executed':False,'genos_deployed':False,'quality_certified':False,'performance_certified':False,'global_graph_existing_errors':len(new_errors),'global_graph_new_errors':0,'rollback_compatibility':read(ART/'rollback-compatibility.json'),'rollback_release':'final-answer-20261029-r1','rollback_command':'.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main'}
put(O/'completion.json',result)
report=f'''최종 답변 내용 보존 수정 — MAIN117

결과
작업 코드와 로컬 MAIN117 / accepted-answer-20261029-r1에 반영했다. 기존 MAIN116은 롤백 대상으로 보존했다. GENOS 현장 배포·Git·메일은 수행하지 않았다.

바꾼 동작
ASSESS에서 검증한 답변의 주체·범위·조건·의무/허용/금지·수치 기준·기한·예외를 서버가 문단/목록/표로 조립한다. 새 accepted-content-v1은 마지막 자유 서술 COMPOSE 호출을 생략한다. 추가 평가 모델이나 재시도를 넣지 않았다.
claim ID 포함 여부만으로 통과시키던 대신, 표시할 text를 기존 내용 컴파일러와 대조하고 ASSESS 해시에 결속한다. 누락/중복/가짜ID, 변조된 내용·원문 receipt, 임의 대체 text/paragraphs, 오래된 ASSESS 결속은 거절한다. 실제 원문/권한 검사는 기존대로 실행한다.
이전 grounded-narrative-v1의 저장 답변과 명시 프로필은 호환 유지한다. 원문 직접 반환/선택 시나리오/별도 workflow task는 기존 전용 경로를 유지한다. 실제 부족·제한 답변·stop_reason·UNKNOWN 기록은 보존한다.

검증
후보 고유116개와 통합 작업116개 관련 계약 통과. 실제 native API 정상/형식 보완/추가 조사 재개/중복/변조 차단, 생성 중 미검증 텍스트 미노출 및 workflow 완성 답변 전달을 확인했다.
동일211회귀: MAIN116과 후보 모두189통과·기존9실패·준비오류13, 항목별 결과 동일·새회귀0. 실패 테스트와 준비오류를 통과로 계산하지 않았다.
466서빙파일 중 제품/설정6개+pin31개 변경. 다른429파일과 작업 코드의 압축 읽기 등 기존 hunk를 보존했다.
실제 선택service OFF/ON미설정/ON빈DB: 총{checks}확인, HEALTH3·모의HTTP3 통과. 코드/데이터/프로필/pin 결속 확인. 새 외부모델0.
ADR1196 최종검사 통과. 전역 graph 기존{len(new_errors)}오류 동일·새오류0이므로 전체 graph 통과는 아니다.

저장7번 진단 (새 실모델 실행 아님)
1195의 실제 ASSESS/COMPOSE를 읽기 전용으로 재사용했다. 기존 저장 답변1524자는 그대로 보존하고 새 방식의2286자 답변을 별도로 만들었다. 주장4개 전체, 국내기업에서 국내소재외국지주회사 제외/외국기업에 포함 조건, 매월5%의 최초에 취득한 주식 분모3곳, 유가의 신청 후 국내 모집·매출 범위가 유지됐다. 원문/주장/제한/중단 사유는 동일하다. 원본 journal 해시는 불변이다.
새 CM007 재시험0·CM0090. 과거007 실패 판정은 바꾸지 않았고9번 실행 요건 충족으로 취급하지 않는다.

보존한 실패
최초 rev001의 digest import 누락(31실패/83통과)을 rev002에서 수정했다. 후보는 보존했다. native fixture의 format HTTP 필드·팀 t가 현행 입력/권한 계약에서 거절된 오류를 기존 route format 및 test_team으로 정정하고 동일 제품에서8검사를 다시 통과했다. ARM 메타의5오류, 저장 진단의 문구 매칭 오기, 덮어쓰기 금지로 거절된 요약 갱신도 기록에 남겼다.

한계
이미 ASSESS에서 빠졌거나 잘못 판단한 법률 내용까지 이 변경이 고치지는 않는다. 추가 의미 검토는 하지 않았고 UNREVIEWED/quality_certified=false를 유지한다. 자유 재서술은 줄고 완전한 검증 내용을 표시하므로 답변이 길어질 수 있다. 이번에는 실제 전체 지연·비용·법률 품질을 인증하지 않았다. 화면은 검증 후 완성된 답변을 전달받는다.
모델·Parasail/확정429 NearAI1회·40/1024/1800·개별180초·출력상한없음·온톨로지기본OFF 동일.

롤백
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
공식 롤백으로 이전 final-answer-20261029-r1을 선택한 뒤 새 service binding을 확인한다. 장기 프로세스가 있다면 재시작한다. 이전 MAIN116 코드가 새 방식의 저장 답변을 그대로 검증하는12개 호환 검사를 통과했다. 이번은 새 실모델 서비스 요청 저장 없이 기술 검증으로 반영했다.

근거
04_EXPERIMENTS/ADR/ADR-1196-accepted-answer-preservation/README.md
04_EXPERIMENTS/ADR/ADR-1196-accepted-answer-preservation/artifacts/run-001/result.json
04_EXPERIMENTS/ADR/ADR-1196-accepted-answer-preservation/artifacts/saved-cm007-preserved-answer.txt
09_ARTIFACTS/AUDITS/20261029-accepted-answer-main117/completion.json
'''
(O/'수정과_검증결과.txt').write_text(report)
p=ROOT/'AGENTS.md';t=p.read_text();marker='<!-- ACCEPTED_ANSWER_MAIN117 -->';assert marker not in t
note=f'''{marker}
**2026-10-29 — 최종 답변 내용 보존 MAIN117:** [수정·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261029-accepted-answer-main117/수정과_검증결과.txt) · [ADR1196](04_EXPERIMENTS/ADR/ADR-1196-accepted-answer-preservation/README.md). 사용자 후속 수정 요청으로 **MAIN117 / accepted-answer-20261029-r1**을 선택했다. 최종 자유 서술 COMPOSE 호출을 생략하고 ASSESS의 검증된 content/text를 서버가 문단·목록·표로 조립한다. 조건·예외·수치 분모 등 전체 내용을 재컴파일·해시 대조하며 임의 대체문장·누락·중복·변조를 거절한다. 과거 narrative-v1 저장 답변은 호환 유지한다. 후보116·작업116 계약 통과, 동일211회귀189통과/기존9실패/준비오류13·새회귀0. 466파일 중 제품/설정6+pin31변경, 다른429파일·작업 압축읽기 hunk 보존. 실제 선택service OFF/ON미설정/ON빈DB **{checks}확인·HEALTH3·모의HTTP3 통과**. 저장1195의007을 읽기 전용 재조립해1524→2286자·주장4개 전체와 국내소재외국지주회사 분류·최초취득 분모를 보존했다. **새모델0·007 실제 재시험0·0090·GENOS/Git/메일 미수행**, 과거 실패 판정 유지. ASSESS 자체 의미 누락/오판은 해결로 확대하지 않으며 UNREVIEWED 유지. 최초 import 누락·검사 fixture/메타 오류를 보존·정정했다. ADR최종검사통과·전역graph기존{len(new_errors)}오류동일. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`, MAIN116 롤백 보존.
<!-- /ACCEPTED_ANSWER_MAIN117 -->

'''
p.write_text(t.replace('# 8-AGENT 작업 가이드\n\n','# 8-AGENT 작업 가이드\n\n'+note,1))
p=ROOT/'04_EXPERIMENTS/ADR/README.md';t=p.read_text();lines=t.splitlines(True);lines.insert(2,'- [ADR1196 최종 답변 내용 보존](ADR-1196-accepted-answer-preservation/README.md) — accepted content 서버 조립·후보/작업116계약·새회귀0·MAIN117 반영. 저장007 조건 보존, 새 실모델0.\n');p.write_text(''.join(lines))
print('MAIN117 documented;',checks,'selected service checks; existing graph errors',len(new_errors))
