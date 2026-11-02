from pathlib import Path
import json,hashlib,sys,gzip,datetime
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369';POST=P/'post-stop';U=R/'09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def mutable(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary
r=read(POST/'interruption.json');a=read(POST/'audit.json');post=read(POST/'post-audit.json');sql=read(POST/'sql-audit.json');e=read(O/'ontology-e2e.json');f=read(D/'freeze.json');integrity={p:sha(R/p)==h for p,h in f['files'].items()};assert all(integrity.values());write_summary(O/'post-run-integrity.json',{'checked':len(integrity),'unchanged':True,'files':integrity})
with gzip.open(P/'canonical/001-output.json.gz','rt') as stream:entry=json.load(stream)
assert all(t['structure'] is None and t['selection'] is None for t in entry['search']['scope_decision']['targets'])
case2={'case_id':'cm-009','status':'NOT_RUN','reason':'First case interrupted by resource stop; frozen first-failure stop rule','model_calls':0,'embedding_calls':0};write_summary(O/'cm-009-not-run.json',case2)
summary={'status':'INCOMPLETE_RESOURCE_STOP_MAIN125_GOLD_LIVE','main_generation':125,'release_id':'oracle-scope-20261030-r1','engine_files':489,'transport_boundary_entries':4,'complete_responses':3,'unfinished_request_outcome_unknown':1,'native_UNKNOWN_timeout_observed':False,'resource_stop_reason':'HOST_SWAP_GROWTH','guard_threshold_MiB':128,'exact_resource_values_retained':False,'approx_seconds_from_file_timestamps':r['seconds'],'normal_run_result_missing':True,'final_answer_chars':0,'native_journal_status_not_rewritten':True,'source_evidence_checks':a['source_checks'],'nested_input_checks':a['nested_view_checks'],'source_mismatches':len(a['source_mismatches']),'acl_violations':len(a['acl_violations']),'wire_matches':a['wire_request_matches'],'wire_mismatches':len(a['wire_request_mismatches']),'budget_matches':a['physical_budget_matches'],'reported_cost_usd':a['reported_cost_usd'],'reported_cost_is_partial':True,'vector':post['vector'],'ontology_acquisitions':post['ontology_acquisitions'],'supervisor_unknown_stop_exercised':False,'narrow_scope_fix_exercised_in_model_run':False,'narrow_scope_fix_real_Oracle_component_checked':True,'scope_explanation':'This model chose FULLTEXT+NAMED_SCOPE but document-wide structure=null/selection=null; query_scope.fulltext returns {} before invoking repaired narrow unit-scope port. RECALL completed via existing vector initial path; no forced mode override.','log_SQL_started':sql['log_started'],'log_SQL_acknowledged':sql['log_acknowledged'],'SQL_boundary_seconds':sql['SQL_boundary_seconds'],'SQL_statement_array_lost':True,'integrity_files_unchanged':len(integrity),'next_case':case2,'reruns':0,'database_content_changes':0,'field_deployed':False,'quality_certified':False}
write_summary(O/'result.json',summary);write_summary(U/'live-result.json',summary)
report=f'''Oracle 본문검색 수정·MAIN125 반영·실제 재검증 — 2026-10-30 / ADR1240·1241

결론: 확인된 코드 오류를 수정해 MAIN125와 Gold에 반영했다. 실제 모델 재검증은 호스트 스왑 증가로 중단되어 전체 답변은 미완료다.

수정과 기술 검증
- Oracle UnitIndex에 SQLite execute를 직접 호출하던 본문검색 범위 포트 누락을 수정했다.
- law_candidates.fulltext_scope_keys가 DB별 scope_keys를 호출하도록 연결했다. SQLite/Oracle 구현에서 범위·문서·unit/source ID·원문 hash·판본·권한을 유지한다.
- MAIN125 / oracle-scope-20261030-r1. 제품3+pin31=34변경/489파일. 작업·동결 후보·선택 코드 동일. Gold도 같은 정식 엔진을 사용하며 기존 연결기3파일은 그대로다.
- R18 VCTR_SCTN_ID/DTLS_HASH_VALU, Gold ON/DB, 기본 MAIN 프로필OFF·데이터·모델 유지. DB내용/DDL 변경0.
- 관련114검사 통과. 기존8실패는 MAIN124에서 동일 오류 재현·새실패0. 전체 저장소가 모두 통과했다는 의미는 아니다.
- 후보서비스61, 실제 선택서비스204검사(OFF/ON미설정/ON빈DB 각68), HEALTH3·모의HTTP3 통과.
- 실제 Gold 원문·용어·기존벡터3행/native100후보 SQL73, 온톨로지3게시12앵커9경로 SQL157 통과.
- 수정한 좁은 범위 포트는 실제 Oracle에서4원문·범위SQL2·빈범위0SQL·권한밖문서거절을 확인했다.

속도 후보는 미채택
게시자료 종류를 미리 좁히는 후보는 동일 행·cursor·hash를 보존했으나 owner28행1.019635→1.049969초, page100행1.024931→1.017032초로 속도 개선 근거가 없었다. 원래 연결기를 그대로 유지했다. 반복 게시자료 조회 지연은 남는다.

실제 모델 재검증 / ADR1241
질문: {read(D/'cases.json')[0]['request']['json']['question']}
- 전송 경계 진입4회, 정상 HTTP200/stop 응답3회. 네 번째 요청 결과를 받기 전에 HOST_SWAP_GROWTH로 프로세스 exit125.
- 사전 기준은 시작 대비 호스트 스왑 사용량128MiB 초과다. 정확한 증가량·RSS·RAM 최저값은 메모리에 있던 표본이 저장되지 않아 보고할 수 없다.
- 호스트 전체 지표이므로 이번 작업만이 증가를 유발했다고 단정하지 않는다.
- 요청 저장시각→중단기록 저장시각 약{r['seconds']:.3f}초. 정상 finally의 monotonic 총시간이 아니다.
- 네 번째 요청은 공급자의 수락·완료 여부 미확인이다. 이전 실험의 공백 응답/180초 timeout UNKNOWN과 구분한다. 재전송0·후속모델0.
- native journal은 마지막 요청 SENT 상태로 보존했다. 사후에 FAILED/성공으로 바꾸지 않았다. 최종 API 응답·ASSESS 입력·저장답변0.
- 새임베딩1회, 벡터 후보100개(권한 안·순위/거리 정렬 확인), 후보 중 확보원문1개. 전체 SQL문 배열은 종료로 유실되어 VECTOR_DISTANCE 물리SQL 개수는 별도로 확정하지 않았다.
- 온톨로지369묶음 실제 ACQUIRED 이벤트1. 최종 ASSESS 입력과3경로/3최종주장 연결은 미도달·미검증.
- 확보원문{a['source_checks']}·중첩입력{a['nested_view_checks']} 대조, 원문불일치0·권한위반0. 네 전송요청 canonical/wire 일치, 예약예산4 일치.
- 보존 SQL로그 {sql['log_started']}시작/{sql['log_acknowledged']}완료, 미닫힘{sql['unclosed_log_calls']}·SQL오류0. 매핑 메타SELECT1 별도.
- SQL 시작→완료 경계 합계{sql['SQL_boundary_seconds']:.3f}초(Oracle CPU만이 아님). 문서페이지 조회115회/{sql['top_shapes'][0]['seconds']:.3f}초 반복.
- 완료된3회 보고비용 ${a['reported_cost_usd']:.8f}, 보고입력{a['input_tokens']}·출력{a['output_tokens']}토큰, 완료통신{a['model_seconds']:.3f}초. 중단된4번째 비용·통신시간 미확인.
- 첫 중단 규칙으로 CM009 미실행. 실패한 두 번째 표본으로 세지 않는다.

수정 효과 해석의 경계
이번 실모델은 FULLTEXT+NAMED_SCOPE를 선택했지만 조문 범위 대신 상법 문서 전체(structure=null/selection=null)를 지정했다. query_scope.fulltext는 이때 좁은 범위 함수 호출 전에 반환한다. 기존 vector 초기 경로로 RECALL을 완료하고 원문 조사까지 진행했다.
따라서 '이전 단계 이후로 진행했다'는 관찰을 '실모델에서 정확히 같은 결함 경로를 재호출하여 통과했다'로 확대하지 않는다. 좁은 범위 수정의 직접 근거는114계약과 실제 Oracle 구성요소 검사다. 검색 결정을 강제로 바꾸거나 실패를 숨기지 않았다.
감독 UNKNOWN 전파·중단 수정의 실제 실효도 이번에는 미검증이다. 프로세스 자원감시 종료와 제품 감독 종료는 다르다.

기록과 적용 상태
전후 동결{len(integrity)}파일 동일. MAIN124·이전실험1239·기술검증1240 보존. 현장GENOS·Git·메일 변경0.
정상 종료 산출물(result/resources/sql-statements/sqlite-opens)은 생성되지 않았다. 남은 checkpoint·journal·원시요청/응답·로그만 post-stop/에서 읽기 전용 분석했고, 없는 측정값을 채우지 않았다.
준비 검사에서 사용하지 않은 ADR 질문 scaffold2개와 목록 요약의 자료형 오류는 원문 보존·정정했다. 모델실행/제품에는 영향없다.

남은 작업
1. 호스트 자원 안정화 후 새 실험에서 최종 답변·온톨로지 최종 입력·벡터 원문 최종 사용을 검증해야 한다.
2. 반복 문서페이지 조회115회 등 실제 병목을 별도로 줄여야 한다. 이번에 속도가 개선됐다고 주장하지 않는다.
3. 실험 감시기가 강제 종료할 때도 마지막 자원 표본과 진행 중 통신 상태를 지속 저장하는 보강이 필요하다. 이번 실행기와 실패기록은 수정하지 않았다.
법률 의미 정확성·벡터 검색품질·온톨로지 인과효과 인증은 아니다.

근거
04_EXPERIMENTS/ADR/ADR-1240-oracle-fulltext-scope-repair/README.md
04_EXPERIMENTS/ADR/ADR-1241-main125-gold-live-revalidation/README.md
{POST.relative_to(R)}/ : 보존된 checkpoint 사후 분석
{P.relative_to(R)}/raw/ 및 canonical/ : 실제 요청/응답 무손실 gzip
09_ARTIFACTS/AUDITS/20261030-oracle-fulltext-repair/selected/ : 선택 MAIN/Gold 실제 구성요소 검사
'''
(U/'수정과_실제재검증_결과.txt').write_text(report)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True,'source':'ADR1240 technical port validation'},'live':summary},comparisons=[],usage={'transport_boundary_entries':4,'complete_responses':3,'unfinished_outcome_unknown':1,'reported_cost_usd':a['reported_cost_usd'],'cost_partial':True},latency={'approx_artifact_window_seconds':r['seconds'],'normal_timer_unavailable':True,'SQL_boundary_seconds':sql['SQL_boundary_seconds'],'population_claim':False},error_taxonomy=[{'category':'RESOURCE_INTERRUPTION','reason':'HOST_SWAP_GROWTH','native_model_or_contract_error':False},{'category':'INCOMPLETE_TELEMETRY','detail':'Hard exit loses in-memory final measurements; only durable data audited'}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,case in zip(m['questions'],read(D/'cases.json')):
 live=case['id']=='gold-369';vals=['run-001/live; frozen rev001; selected MAIN125489',case['request']['json']['question'],'기준답변 제품 미제공·채점모델0.','[동결입력](../artifacts/design/cases.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n벡터100후보→해당원문1확보, 전체원문7대조·최종입력0. CM009미실행.','[실제 원시기록](../artifacts/run-001/live/gold-369/). 전송경계4/정상3/중단중1.' if live else '미실행.','제품 추가호출0·사후모델0.','법률 채점 없음. 보존된 원문/권한/전송/SQL만 사후확인.',summary['status'] if live else 'NOT_RUN'];p=A/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
mutable(A/'실험/manifest.json',m);(A/'실험/README.md').write_text('# 실험 인덱스\n\n'+ '\n'.join('- ['+q['case_id']+']('+q['file']+'): '+('RESOURCE_INTERRUPTED' if q['case_id']=='gold-369' else 'NOT_RUN') for q in m['questions'])+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령'];vals=['Rejected: 호스트 스왑 증가로 중단·전체 모델 답변 미완료. 기술 MAIN125 선택 근거와 별개.','Oracle 좁은 범위 포트 누락을1240에서 수정한 뒤 실제 모델 재검증.','[criteria](artifacts/design/criteria.json) 사전동결;128MiB 초과 스왑 증가·첫실패 중단.','Gold369 실제1회, CM009는 첫사례 미완료로 NOT_RUN. 모델 검색선택 강제0.',f'MAIN125489·Gold ON/DB·R18·Qwen3.8/Parasail우선. 동결{len(integrity)}파일 전후동일.','[결과](artifacts/run-001/result.json).\n\n'+report,'자원감시 exit125, 요청4 결과미확인. native UNKNOWN공백/timeout 또는 Oracle 구현실패로 분류하지 않는다. 완료결과 파일을 합성하지 않았다.','전송경계4/stop3·벡터임베딩1/100후보·SQL2576완료·보고$0.00730248(부분).','이번 모델의 문서전체 범위는 수정한 좁은 범위 함수 호출을 우회한다. 직접 수정검증은1240 실제Oracle 구성요소에 한정.','최종/법률의미/벡터품질/온톨로지최종전달/감독UNKNOWN 미검증. 자원최댓값 미저장.','실험 중 제품/MAIN/DB 변경0. MAIN125 유지·현장GENOS/Git/메일0. 후속실모델은새ADR,이번실행재시도0.','setup→checks→preflight→freeze→run gold-369(resource stop)→interrupted_audit→finish_interrupted. 정상 finish.py는 미실행. 완료실험 재실행 금지.']
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected');(A/'README.md').write_text('---'+front+'---\n\n# ADR-1241: MAIN125 Gold 실제 재검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=A/'artifacts/manifest.json';v=read(p);v['files']=[{'path':str(x.relative_to(R)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen design, partial actual run or explicitly derived read-only interruption audit','contains_raw_prompts_and_outputs':'/raw/' in str(x) or '/canonical/' in str(x)} for x in (A/'artifacts').rglob('*') if x.is_file() and x!=p];v.pop('notes',None);mutable(p,v)
print(summary['status']);print(U/'수정과_실제재검증_결과.txt')
