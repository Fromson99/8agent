from common import *
import sys,sqlite3
f=read(DES/'freeze.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent.compact_model_input import project
from semantic_runtime.legal_agent.navigation_input import expand_cards
from semantic_runtime.legal_agent.repository import encoded
records=[]
for number,nav in [(2,1),(20,19),(31,30)]:
 path=ROOT/f'04_EXPERIMENTS/ADR/ADR-1082-main105-live-latency/artifacts/run-001/fsc-hard-005/raw/call-{number:03d}-source-law-navigation-{nav}-read-choice/request.json'
 raw=read(path);view=expand_cards(json.loads(raw['messages'][1]['content'])['view']);before=len(raw['messages'][1]['content']);total=len(view['read_candidates']);view['read_candidates']=view['read_candidates'][:20];view['read_candidate_page']={'page':1,'total':total}
 out=project(view,raw['response_format']['json_schema']['schema']);after=len(encoded({'view':out}));assert [s.get('text') for s in view['sources']]==[s.get('text') for s in out['sources']]
 records.append({'call':number,'before_chars_including_spaces':before,'after_chars_including_spaces':after,'reduction_percent':round((1-after/before)*100,3),'source_text_equal':True,'representation_only':True})
put(ART/'archived-measurements.json',records)
assert all(r['reduction_percent']>=50 for r in records)
assert '127 passed' in (ART/'run-001/contracts-final.log').read_text()
reg=read(ART/'run-001/regression-comparison.json');assert reg['new_failures']==0
assert '27 passed' in (ART/'working-tests.log').read_text() and '4 passed' in (ART/'working-api-sql-v2.log').read_text()
for item in read(ART/'integration.json')['files']:assert sha(ROOT/item['path'])==item['after']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(DES/'live-freeze.json')['pointer_sha256']
run1={'status':'complete','contracts_passed':127,'prior_development_failures_preserved':True,'regression':reg,'integrated_checks_passed':31,'actual_SQL_input_preparation':[{'evidence_count':n,'before_selects':5*n+1,'after_selects':2} for n in (1,8,80)],'canonical_rows_and_text_equal':True,'page_corpus_SQL_added':0,'projection_DB_access':False,'archived_measurements':records}
put(ART/'run-001/result.json',run1)
result=read(RUN/'result.json');cell=read(RUN/'fsc-hard-005/result.json');usage={k:sum(x.get(k) or 0 for x in cell['usage']) for k in ('input_tokens','output_tokens','thinking_tokens','cost_usd')}
summary={'worktree_integrated':True,'active_MAIN':105,'MAIN_promoted':False,'GENOS_deployed':False,'contracts':127,'baseline_regression_passed':83,'existing_regression_failures_unchanged':36,'new_regressions':0,'working_checks':31,'live':result,'usage':usage,'sql':run1['actual_SQL_input_preparation'],'archived':records,'first_view_seconds':32.28144469799008,'limitations':['Known in-sample single probe; limited partial answer, legal accuracy not certified','No whole response speedup percentage: investigation count differs','Initial view32.3seconds remains; all SQL bottlenecks not removed','ADR1085 proxy161→1 referred to synthetic adapter queries; actual repository preparation401→2 verified here'],'integration':read(ART/'integration.json')}
put(ART/'RESULT.json',summary)
text=f'''작업 코드 반영·실행 결과 (2026-10-27)

읽기 후보는 매 화면20개입니다. 다음/이전 페이지는 이미 만든 후보 목록을 재사용합니다.
탐색·판단·답변 입력은 같은 공통 변환 함수를 사용하며, 내부 ID·중복 메타데이터를 줄였습니다.
원문·권한·판단 기록·저장 화면과 실제 전송 화면의 일치 검증은 유지했습니다.

SQL
- 근거80개 입력 준비의 실제 SQLite SELECT:401회 →2회.
- 근거1개:6→2,8개:41→2. 원문과 span 행은 동일합니다.
- 페이지 이동/표시 변환에 추가되는 corpus SQL:0회.
- 요청 상태·호출 예산을 기록하는 journal 접근은 유지합니다.
- 새 근거 조각을 저장한 판단 단계는 정확한 DB 행을 다시 일괄 조회합니다.
- 첫 화면 준비32.281초는 남아 있는 병목입니다. 전체 SQL 해결을 뜻하지 않습니다.

실제 공개 질문1회
- HTTP200,9회 모델 호출,191.593초.
- 모델 통신109.338초 / 모델 밖82.254초.
- 최대 입력26,500토큰. 출력상한 필드0개, 토큰 한도 오류0회.
- 입력합계127,192 / 출력합계9,608 / reasoning0토큰.
- 근거62단위:원문 불일치0,권한 위반0. 읽기17조문 좌표,최종 인용1조문 좌표.
- 최종 상태:PARTIAL / LIMITED_ANSWER. 일부 자산 기준·적용 시점은 미확인으로 남았습니다.
- 이전 실행과 조사량이 다르므로 전체 속도/총토큰 개선율은 산출하지 않습니다.

같은 보관 입력에 대한 공백 포함 문자 비교
'''+''.join(f"- 호출{r['call']}: {r['before_chars_including_spaces']:,} → {r['after_chars_including_spaces']:,}자 ({r['reduction_percent']}% 감소)\n" for r in records)+'''
검사
- 후보 관련 계약127개 통과. 기존 회귀83개 통과.
- 기존 실패36개는 변경 전후 같은 항목이며 새 실패0개.
- 작업 코드 반영 후31개 검사 통과 (실제 작업 코드 HTTP 모의1회 포함).

적용 상태
- 작업 코드의 unified-v6:minimal_input=true,read_candidate_page_size=20.
- 선택된 서비스 MAIN105는 그대로입니다. GENOS 배포·Git commit/push는 하지 않았습니다.
- 이번은 알려진 질문의 단일 probe이며 MAIN 승격 자격이나 법률 품질 인증이 아닙니다.

전체 입력 TXT
- 첫탐색_실제모델입력.txt
- 후속탐색_실제모델입력.txt
- 답변판단_실제모델입력.txt
- 수정_및_SQL_관리.txt:다음 수정 위치와 주의할 SQL 경로

주의:TXT 들여쓰기는 읽기용입니다. 위 문자 수는 실제 직렬화 입력의 공백까지 센 값입니다.
앞선 ADR1085의161→1은 합성 어댑터 검사였습니다. 실제 리포지토리의 SQL은 위401→2입니다.
'''
(ART/'실행결과.txt').write_text(text)
m=read(ADR/'실험/manifest.json')
for run in m['runs']:
 path=ROOT/run['artifact_path'];run.update(status='complete',sha256=sha(path))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','scope':'Known unchanged working baseline regression and SQL method; no fresh model','passed':83,'failed':36},'compact':{'status':'complete','criteria_met':True,'contract_passed':127,'live_http_status':200,'quality_certified':False,'answer_coverage':'PARTIAL'}},comparisons=records,usage={'product_model_calls':9,'offline_evaluator_calls':0,**usage},latency={'request_seconds':result['request_seconds'],'model_seconds':result['model_seconds'],'non_model_seconds':result['non_model_seconds'],'speedup_percent':None},error_taxonomy=[{'kind':'DEVELOPMENT_CONTRACT_REPAIRS','notes':'Earlier candidates/logs preserved; no provider request before passing contracts.'},{'kind':'UNRESOLVED_LEGAL_SCOPE','status':'LIMITED_ANSWER','quality_certified':False}])
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-1085-experiment-v1/compact'],'changes':'Original working code held fixed for prior regression and actual SQL baseline','controls':'No new model calls; all current bytes preserved in ADR1085 rev001'}, {'id':'compact','role':'candidate','derived_from':['baseline'],'changes':'Common compact input,20candidate paging,exact wire binding and batched request evidence SQL','controls':'Existing semantic judgment/permissions/source hash/canonical execution retained'}]
m['design']['code_isolation']['candidates'][0].update(runner_path='06_TOOLS/EXPERIMENTS/adr_1086/live.py',runner_sha256=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086/live.py'))
m['integration']={'scope':'working-code-only','receipt_path':str((ART/'integration.json').relative_to(ROOT)),'sha256':sha(ART/'integration.json'),'active_main_unchanged':True}
corpus=15777
m['retrieval_accounting'].update(corpus_total=corpus,before_filter=17,after_filter=1,presented_total=1,presented_mean=1,presented_p50=1,presented_p95=1,golden_recall=None,selectivity=1/corpus)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
case=read(DES/'cases.json')[0];qpath=ADR/'실험/질문-001-fsc-hard-005.md'
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
link='../artifacts/run-002/fsc-hard-005'
parts=['run-002 / compact. 격리 후보의 실제 HTTP API1회. 선택 MAIN105가 아님.',case['question'],'기준답변·정답 좌표는 보내지 않았다. 법률 정답률 미측정.',f'[요청]({link}/request.json), [바인딩](../artifacts/run-002/binding.json), [사전 동결](../artifacts/design/live-freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[단계 원장](../artifacts/run-002/retrieval-ledger.json). 원문17좌표→최종 인용1좌표; 부분 span은 조문 전체 읽음의 증명이 아니다.',f'실제 원문은 `{link}/raw/call-*/request.json`, response.json, canonical/*.json.gz, wire/*.json.gz에 보존했다. [실제 첫 탐색 TXT](../artifacts/첫탐색_실제모델입력.txt).',f'[물리9호출]({link}/calls.json), [단계]({link}/generations.json), [원문 감사]({link}/audit.json).','오프라인 평가0회. known in_sample이며 법률 품질·전체 속도 개선을 인증하지 않는다.',f'HTTP200 / PARTIAL / LIMITED_ANSWER. 일부 쟁점 미확인. [실제 답변]({link}/answer.txt). 원문62단위 불일치0·권한위반0.']
qpath.write_text('# fsc-hard-005\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(zip(heads,parts),1))+'\n')
m['questions']=[{'number':1,'case_id':case['id'],'file':qpath.name,'sha256':sha(qpath)}]
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['공통 입력·20개 페이지·SQL 반복 제거를 작업 코드에 통합했다. MAIN105와 GENOS는 유지했다. 기술 계약을 충족했으나 제한 답변·인샘플이므로 승격 자격은 없다.','ADR1085는 축소 화면을 저장/전송 대조기가 모르기 때문에 기각됐다. 이후 전송 검증을 연결하고 문서 번호의 순서를 안정화했으며 새 근거 조각을 DB의 정확한 행으로 재조회한다.','[기준](artifacts/design/criteria.json)과 [실모델 동결](artifacts/design/live-criteria.json). 외부 호출 전에 계약 통과,원문 보존,숨긴 선택 거부,순수 투영 및 기존 SQL 유지가 필수다.','완료된 ADR1085 compact를 부모로 삼았다. 개발 중 세 개 이전 revision과 실패 로그를 보존했다. rev004가127계약을 통과한 뒤 알려진 공개 질문을1회 실행했다. 작업 코드 이전 회귀와 후보를 각각 순차 검사했다.','[최종 동결](artifacts/design/freeze.json), [실행 결속](artifacts/run-002/binding.json). Qwen3.8 / Parasail FP8 / reasoningnone / 출력상한null / fallback없음 /40호출1024도구1800초. 실제 app HTTP 진입점이며 선택 MAIN 서비스라고 표시하지 않는다.','[읽기용 결과 TXT](artifacts/실행결과.txt)와 [전체 결과 JSON](artifacts/RESULT.json).127계약+83회귀 통과,기존36실패 동일,작업 코드31확인. 실모델9호출191.593초에 제한 답변 완료.','초기 저장/전송 결속 누락,시험 fixture 어댑터·경로 오류,새로 기록한 span에 대한 DB bookkeeping 보존 문제를 수리했고 원본 실패를 보존했다. 최종 모델 답변은 자산 산정 시점 등 미확인을 남겼다. 불확실성을 정답으로 바꾸지 않는다.','실제 journal SQL은 근거80개 입력 준비401→2; 데이터행·원문 동일. ADR1085의161→1은 합성 어댑터 수치로 실제 repository SQL 수와 구분한다. 실모델 최대 입력26500,전체 입력127192/출력9608,9호출.17조문 좌표에서62근거단위 확인,인용1조문. 첫 화면32.281초가 남았다.','표시 단계는 DB가 없는 공통 함수이며 페이지 이동은 준비된 목록을 사용한다. 기존 corpus SQL을 늘리지 않고 요청 journal의 N+1을 제거했다. 서버는 원래 화면과 선택 번호·원문·권한을 유지한다.','알려진 질문1개·PARTIAL·LIMITED_ANSWER·법률 품질 미인증. MAIN105 실패 실행보다 조사량이 적어 전체 응답시간과 총토큰 개선율로 해석하지 않는다. GENOS/Oracle 실제 성능을 인증하지 않는다.','[작업 코드 통합 영수증](artifacts/integration.json). 바이트 일치40파일만 반영하고 이전 read_judgment/복귀 기능을 보존했다. active MAIN105 그대로. 롤백은 ADR1085 rev001의 변경 파일만 복원하고 새2모듈/프로필 및 pin을 함께 되돌리는 검토 패치로 수행한다. 다른 작업 변경을 덮어쓰지 않는다.','contracts_final.py → freeze_live.py → live.py1회 → source_audit.py → ledger.py → delivery_regression.py/baseline → integrate.py → 작업 코드 검사 → report_final.py → status/validate --final/graph. 완료된 live cell을 다시 실행하지 않는다.']
created=m['reservation']['created_at']
(ADR/'README.md').write_text(f'---\nadr_id: ADR-1086\ntitle: 공통 입력·후보20개·SQL 배치 조회 구현과 실모델 검증\nstatus: Accepted\ndecision_date: 2026-10-27\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {created}\nowner: codex\nwork_status: completed\n---\n\n# ADR-1086\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(zip(heads,parts),1))+'\n')
(ADR/'실험/README.md').write_text('# 실행 결과\n\n[전체](../README.md) · [실제 질문](질문-001-fsc-hard-005.md) · [TXT](../artifacts/실행결과.txt). 새 모델9회, MAIN105 그대로.\n')
print(json.dumps({k:summary[k] for k in ('contracts','new_regressions','working_checks','MAIN_promoted')},ensure_ascii=False))
