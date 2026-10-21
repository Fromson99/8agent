"""Record exact selected MAIN, service, data and resource evidence after promotion."""
from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[2];A=R/'04_EXPERIMENTS/ADR/ADR-0870-host-owned-enum-contract';D=A/'artifacts/design';L=R/'04_EXPERIMENTS/ADR/ADR-0871-host-owned-fulltext-live'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):
 assert not p.exists(),p
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==83 and pointer['release_id']=='host-assembled-output-20261018-r1'
manifest=R/pointer['manifest_path'];assert sha(manifest)==pointer['release_manifest_sha256'];release=read(manifest);O=manifest.parent
base=read(D/'baseline.json')['release'];freeze=read(D/'freeze.json');C=R/freeze['code_root'];selected=R/release['code_root'];cm=read(R/freeze['candidate']['manifest_path'])
assert len(release['files'])==370 and all(sha(C/n)==sha(selected/n)==h for n,h in release['files'].items())
assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
assert release['data_path']==base['data_path'] and release['data_manifest_sha256']==base['data_manifest_sha256']
active=read(A/'artifacts/active-consumer.json');assert active['status']=='PASS' and not active['app_injected'] and active['code_root']==release['code_root'] and len(active['checks'])==10 and all(active['checks'].values())
assert all(read(A/f'artifacts/{mode}-consumer.json')['search_selection_fingerprint']==active['search_selection_fingerprint'] for mode in ['candidate','working'])
log=(A/'artifacts/working-api.log').read_text();passed=int(re.findall(r'(\d+) passed',log)[-1]);assert passed==415 and not re.search(r'\b\d+ failed',log)
resources=[]
for root in [A,L]:
 for p in sorted((root/'artifacts').glob('*resources.json')):
  v=read(p);assert v['returncode']==0 and not v['stop_reason'];resources.append({'record':bound(p),**{k:v[k] for k in ['peak_group_rss_bytes','min_available_bytes','seconds']}})
live=read(L/'artifacts/summary.json');assert live['schema_error_count']==0
resource_stop=bound(A/'artifacts/working-resource-stop-001/RECEIPT.json')
result={'status':'LOCAL_MAIN_SELECTED_AND_SERVICE_VERIFIED','release':bound(manifest),'pointer':pointer,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'candidate':freeze['candidate'],'working_candidate_files_equal':len(cm['files']),'selected_candidate_files_equal':len(release['files']),'integration':bound(A/'artifacts/working-integration.json'),'qualified_contract_tests':413,'working_contract_tests':passed,'actual_service_checks':10,'actual_service':bound(A/'artifacts/active-consumer.json'),'actual_service_binding':active['health'],'unchanged_data':{'path':release['data_path'],'manifest_sha256':release['data_manifest_sha256'],'search_selection_fingerprint':active['search_selection_fingerprint']},'fulltext_model_audit':{'record':bound(L/'artifacts/summary.json'),'calls':live['model_calls'],'answers':live['answer_count'],'schema_errors':live['schema_error_count'],'environment':'isolated exact candidate bytes, external Qwen3.8 Parasail FP8, approved public sources; not GENOS'},'resources':resources,'preserved_resource_stop':resource_stop,'genos_field_status':'NOT_VERIFIED','git_main_merge':'NOT_PERFORMED','git_push':'NOT_PERFORMED','existing_service_process_restarted':False,'remaining_limits':['Legal relevance and insufficient originals are model judgments, not schema proof or legal certification.','No GENOS internal model/grammar, Oracle field connection, production commit/push/revision/editor/workflow test access.','Old live processes, if present, must reload the selected release.','Prior failures and unrelated global ADR graph errors retained.']}
put(O/'IMPLEMENTATION_RESULT.json',result)
text=f'''MAIN83 시스템 조립·fulltext 검증 반영 (2026-10-18)

선택 릴리스: {release['release_id']} / generation83
최근 MAIN82의 대사 워크플로우1.9.0, 내규 근거 발굴1.0.0, 근거 관계 원장, Oracle 경로를 유지했다. 전체 MAIN의 입력·구조화·용어 연결·색인·RAG·피드백 책임은 바꾸지 않았다.
원문 데이터 세대·검색 선택·모델 정책·실패 예산은 그대로다.

모델은 필요한 판단과 선택만 반환한다. 스키마가 확정하는 고정값·상태/표시 ID·빈 항목과 쟁점 원문 연결은 시스템이 채운다.
단일 대상 행동은 targets에서 한 번 선택하고 exploration.target을 조립한다. 여러 원문을 읽을 때는 exploration에서 선택하고 중복 targets/issue_refs를 조립한다. 서로 모순되는 구 응답은 임의로 바꾸지 않는다.
행동별 필수값과 대상 목록, 부모/중첩 분기 제약, enum/const의 시스템 소유 표시, 객체 개수 제약을 유지한다. 인용·권한·상태·예산 검사를 끄지 않았다.

검증: 후보413개, 통합 작업415개, 정적 스키마594노드. 후보·작업·선택 릴리스 각각 실제 데이터/서비스10검사.
711개 검증 후보와 작업 파일 일치,370개 서빙 파일과 선택 릴리스 일치. 작업 변경40파일은 제품3개+서빙pin31개+비서빙engine pin6개다.
실제 외부 모델 fulltext: {live['model_calls']}호출, 최종 답변{live['answer_count']}/2, 출력 스키마/복원 오류{live['schema_error_count']}회. 자세한 최종 상태와 불충분 판단은 ADR0871 summary.json에 그대로 기록했다. 법률 정답률·속도 개선 인증이 아니다.
MAIN 승격 후 실제 service.application의 새 프로세스에서 선택 릴리스와 API 연결을 확인했다. 기존 실행 프로세스를 임의로 재시작하지 않았다.

자원: 대형 원문·색인은 복제하지 않았다. 무거운 검사는 하나씩 실행하고 프로세스 합산RSS8GiB,가용RAM2GiB,물리디스크10GiB의 중단 경계를 적용했다. 일반 단위검사는 더 작은2GiB 한도다. 실제 색인을 읽는 서비스 검사가 이 한도를 넘어 자동 중단된 기록은 보존하고, 그 검사만 별도8GiB 프로세스로 분리해 순차 재검증했다. 실제 최대 사용량은 IMPLEMENTATION_RESULT.json의 실행별 영수증으로 확인한다.
저장공간/RAM 선호는 AGENTS.md에 지속 기록했다. 이전 실패·부분 완료·비용·unknown 결과와 완료 릴리스는 보존한다.

GENOS: 새 ZIP과 실행TXT를 별도로 전달한다. ~/DEV 적용, 실제 업로드TRANSFER 상대경로, Python3,백업·재실행·복구·commit별gate를 사용한다. 현장 코드 적용·Git push·서빙리비전·워크플로우편집기·내부모델 검증은 미수행이다.
사진의180초timeout 원인을 모델busy로 확정하지 않는다. 외부 모델 실행에서 확인한 생성/복원 계약 결함과 중복 필드 충돌을 수정한 것이다.

롤백: 현재 포인터가 이 release/generation83인 것을 먼저 확인하고 stable rag_main_promotion.py rollback --confirm-main을 사용한다. 새 승격 뒤에는 이 안내를 무조건 재사용하지 않는다. 원문·원장·실패 이력은 삭제하지 않는다.
'''
(O/'IMPLEMENTATION.txt').write_text(text)
print('MAIN83 exact selection verified:415working tests,10active service checks,370serving/711candidate files')
