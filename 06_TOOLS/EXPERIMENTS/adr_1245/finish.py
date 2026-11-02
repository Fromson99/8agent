from pathlib import Path
import json,hashlib,sys
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1245-main128-oracle-records-live';D=A/'artifacts/design';O=A/'artifacts/run-001';P=O/'live/gold-369';U=R/'09_ARTIFACTS/AUDITS/20261030-main128-oracle-records-live'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
sys.path.insert(0,str(R/'06_TOOLS/maintenance'));from experiment_json import write_summary as put
x=read(O/'audit-decoded.json');sql=read(O/'sql-audit.json');cap=read(O/'capacity-after.json');run=read(P/'result.json') if (P/'result.json').exists() else {'normal_result_unavailable':True,'resource_stop':read(P/'resource-stop.json') if (P/'resource-stop.json').exists() else None,'process_crash':read(O/'process-crash.json')};dup=read(P/'duplicate.json') if (P/'duplicate.json').exists() else None
attempts=x['attempts'];gates={'api_saved_answer':x['http_status']==200 and x['answer_present'] and any(v.get('status')=='PUBLISHED' for v in x['publications']), 'oracle_structured_attempts':bool(attempts) and all(v['request_is_diagnostic_reference'] for v in attempts) and x['structured_proposals']>0 and not x['raw_response_leaks'],'fresh_process_reopen':x['fresh_process'] and bool(x['journals']) and all(v>0 for v in x['oracle_tables'].values()),'no_disk_journal':not x['physical_runtime_exists'],'duplicate_no_model':bool(dup and dup['status']==200 and dup['same_answer'] and dup['extra_model_calls']==0),'nfs_unconfigured':bool(attempts) and all(v['capture_status']=='UNCONFIGURED' for v in attempts),'actual_original_acl':x['source_checks']>0 and not x['source_mismatches'] and not x['acl_violations'],'unknown_no_later_calls':x['post_unknown_calls']==0,'budget_matches':x['physical_budget_matches'],'resources':x['resources']['resource_stop'] is None,'capacity':cap['within_limit'],'code_unchanged':not x['changed_frozen_files'],'process_completed':(P/'result.json').exists() and run.get('http_status') is not None}
success=all(gates.values());result={'status':'KNOWN_FUNCTIONAL_PASS' if success else 'INCOMPLETE_FUNCTIONAL_E2E','gates':gates,'main_generation':128,'release_id':'oracle-structured-20261030-r1','serving_files':495,'actual':run,'actual_model_calls':x['physical_model_calls'],'unknown_outcomes':x['unknown_outcomes'],'source_checks':x['source_checks'],'structured_proposals':x['structured_proposals'],'oracle_tables':x['oracle_tables'],'reported_cost_usd':x['reported_cost_usd'],'cost_partial':x['missing_usage_calls']>0,'resources':x['resources'],'capacity':cap,'fresh_process_readback':True,'storage':read(O/'storage-size.json'),'process_crash':read(O/'process-crash.json'),'new_ddl':0,'gold_source_writes':0,'agent_structured_writes':True,'actual_nfs_verified':False,'field_ords_or_genos_verified':False,'quality_certified':False,'main_changed':False}
put(O/'result.json',result);U.mkdir(parents=True,exist_ok=True);put(U/'result.json',result)
failed=[k for k,v in gates.items() if not v];seconds=run.get('seconds');size=read(O/'storage-size.json');before=read(D/'capacity-before.json');growth=cap['sidda_used_bytes']-before['sidda_used_bytes']
text=f'''MAIN128 실제 모델·Oracle 구조화 기록 실험 — ADR1245 / 2026-10-30

결과: {result['status']}
질문: {read(D/'cases.json')[0]['request']['json']['question']}
실제 모델 {x['physical_model_calls']}회 / 정상 응답 {x['complete_responses']}회 / 결과 미확인 {x['unknown_outcomes']}회.
HTTP {x['http_status']} / 답변 {x['answer_chars']}자 / 정식 단조시계 실행시간 {seconds}초.
모델 통신 누적 {x['model_seconds']:.3f}초. 보고 비용 ${x['reported_cost_usd']:.8f}; 사용량 미보고 {x['missing_usage_calls']}회.
통과하지 않은 기준: {', '.join(failed) or '없음'}.

프로세스 충돌과 실제 모델 계약 실패
커널은 AnyIO worker thread의 libsqlite3 내부 SIGSEGV, 프로세스는139로 종료됐다. C stack/core가 없어 C 내부 근본 원인은 확정하지 않는다.
그 전에 최종 최초/보완 모두 NEED_TARGET_INCOMPLETE/NEED_RESOLUTION_CLAIM 계열 필요-근거 연결 검증에 거절됐다.
Oracle에는 SOURCE_INVESTIGATION_INCOMPLETE / ASSESSMENT_CONTRACT_UNRESOLVED / FAILED/END가 보존됐다.
모델 HTTP200/stop8과 최종 답변 성공은 다른 결과다. UNKNOWN0, 추가 전송0.
정상 finally의 시간/응답 파일이 없으므로 약9분(마지막내구표본 {read(O/'process-crash.json')['last_durable_elapsed_seconds']:.3f}초)을 정식 총시간으로 보고하지 않는다.

저장 확인
Oracle Agent namespace: adr1245-main128-live / scope {x['scope']}.
실제 Oracle 행수: {json.dumps(x['oracle_tables'])}.
별도 새 프로세스가 Oracle에 연결해 저널 {len(x['journals'])}개를 재조회했다.
모델 시도 {len(attempts)}건: 요청은 NFS 진단 참조, 구조화 제안 {x['structured_proposals']}건.
원시 응답의 SSE/reasoning/debug 유출 {len(x['raw_response_leaks'])}건, 실제 runtime 디스크 생성 {x['physical_runtime_exists']}.
확보 원문 {x['source_checks']}대조 / 불일치 {len(x['source_mismatches'])} / 권한 위반 {len(x['acl_violations'])}.
중복 요청 검사: {json.dumps(dup,ensure_ascii=False)}.
UNKNOWN/미확인 이후 추가 물리 호출 {x['post_unknown_calls']}회.

NFS 경계
현재 로컬에는 NFS/CIFS 마운트가 없다. 실제 마운트 검사 우회0.
제품 상세 기록은 UNCONFIGURED 참조이며 NFS 저장 성공을 주장하지 않는다.
원시 요청/응답은 별도 로컬 실험 감사 raw/canonical/experiment-client에 보존했다.
이 실험 폴더가 제품 상세로그의 로컬 대체 저장소라는 뜻이 아니다.
현장 NFS 정상/장애·ORDS·Oracle19·GENOS 검증은 미수행이다.

지연·사용률
SIDDA 할당 {before['sidda_used_percent']:.3f}%→{cap['sidda_used_percent']:.3f}%, +{growth/1024**2:.3f}MiB.
이번 고유 scope의 BODY {size['body_parts']}조각/{size['unique_bodies']}고유본문, JSON envelope {size['body_json_characters']}문자.
52,742행은 실행 수가 아니라 본문 저장 조각 수다. 전체 SIDDA BODY scope는 이번 scope 하나만 존재했다.
상세 프롬프트를 옮기지 않아도 구조화 blob/개정이력·청크의 저장 증폭이 크므로 반복 실행 전에 줄여야 한다.
SQL경계 집계: {json.dumps(sql['groups'],ensure_ascii=False)}.
SQL 시작→완료 경계는 전송/직렬화/DB를 포함하며 Oracle CPU만의 시간이 아니다.
현재 Gold 연결기 시험은 source/Agent 각1만 SQL 예산이고 일반 DP Factory는 둘을 합쳐1만 예산이다. 일반 DP/ORDS의 정확한 부하 시험은 아니다.
단일 질문이며 SQLite 대비 지연 차이·부하 성능 인증은 아니다.
가용 RAM 최저 {x['resources']['min_available_GiB']}GiB, RSS최대 {x['resources']['max_RSS_GiB']}GiB, 호스트swap증가최대 {x['resources']['max_host_swap_growth_MiB']}MiB.
자원 중단: {json.dumps(x['resources']['resource_stop'],ensure_ascii=False)}.
SIDDA {cap['sidda_used_percent']:.3f}% / 디스크 {cap['disk_used_percent']:.3f}%, 사용자 한도90% 이내={cap['within_limit']}.
스왑은 호스트 전체 지표이며 이번 프로세스만의 원인으로 단정하지 않는다.

동결·변경 범위
동결 {x['frozen_files']}파일 변경 {len(x['changed_frozen_files'])}개. 선택MAIN128/제품495파일 유지.
Gold 원문/벡터/온톨로지 내용 변경0·신규 DDL0·이전기록 이관/삭제0·현장배포/Git/메일0.
Agent Oracle에는 이번 실행의 실제 구조화 기록을 고유 namespace에 남겼다.
동결 freeze.json의 read_only_database_access=true는 이전 실행기에서 복사된 부정확한 메타 필드다.
실행 전 criteria.scope와 본문은 Gold 읽기전용/Agent 새기록 쓰기를 명시했으며 전체DB읽기전용으로 해석하지 않는다. 원래 동결 파일은 수정하지 않았다.
첫 준비의 RecordSQL 예산30000은 허용최대10000에 걸려 API/모델/Agent쓰기 전에 거절됐다.
실패 원본을 preparation-failure-001에 보존한 뒤 실제 첫 호출 전에 rev003/10000으로 다시 동결했다.
실모델 완료/실패 뒤 동일 질문 재실행0. 법률품질·온톨로지 인과 효과 인증 없음.

원본: {A.relative_to(R)}
''';(U/'실제실험_결과.txt').write_text(text)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True,'actual_new_model_calls':0,'source':'ADR1244 scripted-model Oracle contracts, not an actual model control'},'live':result},comparisons=[],judge_disagreements=0,usage={'physical_model_calls':x['physical_model_calls'],'reported_input_tokens':x['reported_input_tokens'],'reported_output_tokens':x['reported_output_tokens'],'reported_cost_usd':x['reported_cost_usd'],'missing_usage_calls':x['missing_usage_calls']},latency={'seconds':seconds,'model_seconds':x['model_seconds'],'p50_p95':'Not estimated from one known case','sql':sql['groups']},error_taxonomy=[{'category':'functional_gate','failed':failed}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정'];vals=['run-001/live; selected MAIN128495, frozen rev003; real local Oracle source+Agent; no real NFS.',read(D/'cases.json')[0]['request']['json']['question'],'기준답변 미제공·채점모델0. 저장/해시/권한/상태 검증만 수행.','[동결 질문](../artifacts/design/cases.json), [입력 동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n기존 검색 정책 불변, 검색효과 비교 아님. 확보 원문과 전송 원문의 좌표/해시는 [audit](../artifacts/run-001/audit-decoded.json).','[실제 원시 요청/응답](../artifacts/run-001/live/gold-369/raw/) 및 [canonical](../artifacts/run-001/live/gold-369/canonical/) gzip/ref.json에 완전 보존. 제품 NFS 성공과 구분.','[실제 호출 원장](../artifacts/run-001/live/gold-369/calls.json), [구조화 제안](../artifacts/run-001/live/gold-369/canonical/).','judge0·자동 재채점/재실행0. 법률 정답률 미측정.',result['status']+' / failed='+', '.join(failed)]
for q in m['questions']:
 p=A/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
(A/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');(A/'실험/README.md').write_text('# 실험 인덱스\n\n- [gold-369](질문-001-gold-369.md): '+result['status']+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령'];vals=[result['status']+'; 전체 실모델/저장 기준의 판정과 현재 MAIN 유지.','MAIN128에서 구조화 상태와 원시 상세로그를 Oracle/NFS로 분리한 뒤 실제 모델 연결을 점검.','[사전 기준](artifacts/design/criteria.json). 결과 뒤 성공 기준 변경0.','기존 Gold369 알려진 질문1회, 코드/질문/모델 사전 동결. NFS 미구성 모드만 실행. 비교 대조 실모델0.',f'Qwen3.8 / Parasail FP8 우선, 확정429만 NearAI1전환, 출력상한없음. MAIN128495/R18/GoldON DB. 동결{x["frozen_files"]}파일 변경0.',text,'[Oracle 새 프로세스 감사](artifacts/run-001/audit-decoded.json), [SQL 감사](artifacts/run-001/sql-audit.json). 실패 기준: '+', '.join(failed),'실제 호출/원문/지연/자원/용량을 위 결과에 분리. 단일 질문으로 속도 개선율/법률 정답률 미측정.','Oracle 영속화와 모델 제안의 의미 정확성은 별개다. 실패/미완료를 빈 성공으로 바꾸지 않았다.','현장 NFS/GENOS/ORDS/Oracle19·과거 대량이관·부하성능 미검증. 알려진1질문 in-sample, decision_eligible=false.','MAIN128/Gold 내용 유지. 이번 고유 Agentnamespace 새기록만 남음·이전 데이터 삭제0·Git/메일0.','preflight.py → capacity.py design/capacity-before.json → freeze.py → run.py gold-369 → audit.py → sql_audit.py → capacity.py run-001/capacity-after.json → finish.py. 완료 실행 재전송 금지.']
front=(A/'README.md').read_text().split('---',2)[1];front=front.replace('status: Proposed','status: '+('Proposed' if success else 'Rejected'));(A/'README.md').write_text('---'+front+'---\n\n# ADR-1245: MAIN128 실제 모델과 Oracle 구조화 기록 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=A/'artifacts/manifest.json';v=read(p);v['files']=[{'path':str(x.relative_to(R)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen pre-dispatch design, actual inference evidence or read-only post-run audit','contains_raw_prompts_and_outputs':any(k in str(x) for k in ('/raw/','/canonical/','/experiment-client/'))} for x in (A/'artifacts').rglob('*') if x.is_file() and x!=p];p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');print(result['status'],failed);print(U/'실제실험_결과.txt')
