from common import *
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-final-answer-main116'
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/pointer['manifest_path']);result=read(RUN/'result.json')
assert pointer['generation']==116 and pointer['release_id']=='final-answer-20261029-r1'
consumers={m:read(O/f'consumer-{m}.json') for m in ('off','on','db')}
assert all(v['passed'] for v in consumers.values())
counts={m:len(v['checks']) for m,v in consumers.items()}
old_graph=(ROOT/'09_ARTIFACTS/AUDITS/20261029-final-scope-prompt-live/adr-graph.log').read_text();new_graph=(O/'adr-graph.log').read_text()
old_errors=[s for s in old_graph.splitlines() if s.startswith('ERROR:')];new_errors=[s for s in new_graph.splitlines() if s.startswith('ERROR:')]
assert len(new_errors)==16 and set(old_errors)==set(new_errors)
text=f'''최종 답변 누적 수정 MAIN116 반영 완료 — 2026-10-29

선택 릴리스: MAIN116 / workflow1.20.8 / final-answer-20261029-r1
정본: 01_DATA/ACTIVE/local/ACTIVE_RELEASE.json
실제 코드: {release['code_root']}

무엇을 반영했는가
MAIN115의 확정 원문 선집행, 응답 형식 보완, 독립 조사 복구, 목표 포함/종료, 표제 기반 목표 발견, 요구별 충족 검토, 확정429 공급자 전환, 물리 호출 차감, 절대기한을 유지한다.
여기에 ADR1192의 최종 ASSESS·보완 프롬프트를 통합했다. 주체·대상·지역·시점, 산정 기준·단위·상한·기한, 조건·예외를 실제 주장에 유지하고 원문과 역대조한다. 특정 조문·문서·정답 하드코딩은 없고 모델 단계·스키마·재시도 추가0이다.
서버가 조사 중단 이력만으로 붙이던 “확인한 원문 범위에서 답변하며, 나머지 범위는 확인하지 못했습니다.”를 제거했다. 구체 material gap, 실제 사실/원문 부족, 최종 검토 출력한도 미완료 경고는 유지한다. stop_reason과 과거 UNKNOWN·실패 로그를 삭제하거나 성공으로 변경하지 않는다.

검증 결과
후보 고유130계약 통과. 최초122통과/8검사오류, 보완5통과/3검사오류 후 남은3통과를 구분 보존했다. 오류는 공개/내부응답 접근, fixture ROOT, 후보에 없는 압축리더 import였다. 제품466파일은 처음 동결한 내용 그대로다.
병합한 작업 코드130계약 통과. 기존211회귀: MAIN115와 후보 모두189통과·기존9실패·준비오류13, 항목별 동일·새회귀0.
저장007 답변 재생: 2392→2344자로 마지막 일반 문구만48자 제거, 주장5·근거·조건·gaps·검토·중단 이유 동일. 이전 저장 답변의 검증도 통과. 알려진 사례의 표시 진단이며 새로운 모델 실험/법률 정답률 근거가 아니다.
466서빙파일 중 제품3+종속pin31=34변경. 실제 서비스의 OFF/ON미설정/ON빈DB 각{list(counts.values())}, 총{sum(counts.values())}확인 통과. HEALTH3·모의HTTP3·실제 외부모델0. 선택 코드·새 프롬프트·불필요 문구 제거·실제 부족 보존·기한/라우팅/권한/데이터 설정을 확인했다.
ADR1194 최종 검증 통과. 전역 graph 기존16오류 동일·새오류0이며 전체 graph 통과는 아니다.

보존 및 한계
작업의 completion_execution.py는 프롬프트 상수만 병합하여 기존 journal_text 저장압축 읽기를 보존했다. 그 외432파일을 건드리지 않았다. 다른 작업의 저장압축 전체·온톨로지 추가 후보를 이번 릴리스에 자동 승격한 것은 아니다.
Qwen3.8, Parasail FP8 우선/확정429만 Near AI FP8 1회, 40모델/1024도구/1800초·개별180초·출력상한없음·온톨로지기본OFF·기존 데이터 동일.
VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false.
1193에서 발생한 감독 호출의 공백/UNKNOWN은 해결되지 않았다. CM007 전체미통과·CM009미실행 기록을 유지한다. 이번 새 CM007/009·모델 품질/속도 비교·GENOS 현장 배포·Git·메일 미수행.

운영·롤백
선택 서비스는 새 프로세스로 MAIN116 결속을 확인했다. 계속 실행 중인 별도 로컬 서비스 프로세스는 관찰되지 않았다. 별도 장기 프로세스가 있다면 재시작해야 선택 릴리스가 갱신된다.
문제가 생기면 공식 명령으로 직전 parasail-primary-20261029-r1로 되돌리고 필요한 서비스 프로세스를 재시작한다:
.venv/bin/python 06_TOOLS/run_tool.py rag_main_promotion.py rollback --confirm-main
MAIN115 코드와 활성화 이전 영수증은 보존했다. 작업 파일 원본은 ADR1194/artifacts/working-backup에 보존했으며, 병행 변경을 확인하지 않고 일괄 복원하지 않는다.
'''
(O/'반영과_검증결과.txt').write_text(text)
put(O/'completion.json',{'status':'complete','release_id':pointer['release_id'],'main_generation':116,'files':466,'changed_files':34,'candidate_checks':130,'working_checks':130,'regression_total':211,'new_regressions':0,'selected_service_checks':sum(counts.values()),'new_model_calls':0,'mock_http_calls':3,'quality_certified':False,'performance_certified':False,'genos_deployed':False,'graph_existing_errors':16,'graph_new_errors':0,'evidence':[bind(p) for p in [ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',ROOT/pointer['manifest_path'],O/'authorization.json',O/'validation.json',*[O/f'consumer-{m}.json' for m in consumers],O/'adr-final-validation.log',O/'adr-graph.log',O/'반영과_검증결과.txt']]})
summary=f'''**2026-10-29 — 최종 답변 누적 수정 MAIN116 반영:** [반영·검증·롤백 TXT](09_ARTIFACTS/AUDITS/20261029-final-answer-main116/반영과_검증결과.txt) · [ADR1194](04_EXPERIMENTS/ADR/ADR-1194-final-answer-main-integration/README.md). 사용자 요청으로 **MAIN116 / final-answer-20261029-r1**을 선택했다. MAIN115 누적 원문·응답·요구검토·공급자·기한 수정을 유지하고1192 최종 ASSESS/보완 프롬프트2곳과 서버 일반 미확인 문구 제거를 통합했다. material gap·최종 검토 미완료 경고·stop_reason·UNKNOWN 기록 보존. 466서빙파일 중 제품3+pin31변경, 후보 고유130·작업130계약 통과. 211회귀189통과/기존9실패/준비오류13 동일·새회귀0. 저장0072392→2344자로 일반 문구48자만 제거, 주장·원문·조건·중단 이력 동일. 실제 선택service OFF/ON미설정/ON빈DB 총{sum(counts.values())}확인·HEALTH3·모의HTTP3 통과. 초기 검사 준비 오류는 원본 보존 후 동일제품으로 정정 검증했다. 작업의 저장압축 읽기와 다른432파일 보존. ADR최종검사통과·전역graph기존16오류동일. **새모델0·감독공백/UNKNOWN 미해결·007전체미통과/009미실행 기록 유지·GENOS/Git/메일 미수행**. 모델·데이터·예산·출력상한없음·온톨로지기본OFF 동일. `VALIDATED_ADR_PROMOTION / quality_gate_override=false / quality_certified=false`. MAIN115 롤백 보존.'''
p=ROOT/'AGENTS.md';s=p.read_text();assert 'FINAL_ANSWER_MAIN116' not in s
s=s.replace('# 8-AGENT 작업 가이드\n','# 8-AGENT 작업 가이드\n\n<!-- FINAL_ANSWER_MAIN116 -->\n'+summary+'\n<!-- /FINAL_ANSWER_MAIN116 -->\n',1)
s=s.replace('<!-- CURRENT_LOCAL_RAG_RELEASE -->\n','<!-- CURRENT_LOCAL_RAG_RELEASE -->\n\n'+summary+'\n\n직전 MAIN115 단계의 보존 기록:\n',1)
s=s.replace('현재 MAIN115는 ADR1190의 Parasail 우선 정책을 사용한다.','현재 MAIN116은 ADR1190의 Parasail 우선 정책을 그대로 사용한다.')
p.write_text(s)
p=ROOT/'04_EXPERIMENTS/ADR/README.md';s=p.read_text();lines=s.splitlines(True);lines.insert(2,'- [ADR1194 최종 답변 MAIN116 통합](ADR-1194-final-answer-main-integration/README.md) — 최종 프롬프트·일반 미확인 문구 제거,130계약·211회귀 비교·실제 선택서비스 검증. 새모델0·GENOS미수행.\n');p.write_text(''.join(lines))
print('Documented MAIN116, selected checks',sum(counts.values()))
