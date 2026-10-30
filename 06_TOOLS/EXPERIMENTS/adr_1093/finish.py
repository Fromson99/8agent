"""Close the diagnostic, preserving raw replay in a verified lossless archive."""
from common import *
from datetime import datetime,timezone
import re,tarfile,shutil
result=read(ART/'run-001/result.json');assert result['completed'] and result['answer_exact'] and result['active_pointer_unchanged']
h=read(ART/'historical-attribution.json');p=read(ART/'profile-attribution.json');d=read(ART/'prompt-repair-diagnosis.json')
runtime=ART/'run-001/runtime';archive=ART/'run-001/runtime.tar.gz'
assert not archive.exists()
entries={str(x.relative_to(runtime)):sha(x) for x in runtime.rglob('*') if x.is_file()}
assert entries and not any(x.is_symlink() for x in runtime.rglob('*'))
with tarfile.open(archive,'w:gz',compresslevel=6) as tar:tar.add(runtime,arcname='runtime')
with tarfile.open(archive,'r:gz') as tar:
 checked={}
 for member in tar:
  if member.isfile():
   with tar.extractfile(member) as stream:checked[str(Path(member.name).relative_to('runtime'))]=hashlib.file_digest(stream,'sha256').hexdigest()
assert checked==entries
put(ART/'run-001/archive-receipt.json',{'archive':bound(archive),'files':entries,'file_count':len(entries),'all_hashes_verified_before_temp_removal':True,'original_live_runtime_untouched':True,'restore':'tar -xzf runtime.tar.gz (in this run-001 directory); verify each file using the files mapping in archive-receipt.json','temporary_runtime_removed':True})
shutil.rmtree(runtime)

sql=read(ART/'run-001/sql-counts.json')
summary={'source_point_selects':sum(r['count'] for r in sql if r['sql']=='SELECT * FROM source_block WHERE document_id=? AND block_id=?'),
 'term_scope_queries':sum(r['count'] for r in sql if 'WHERE o.term_id' in r['sql']),
 'all_sql_trace_callbacks_including_fts_internal':sum(r['count'] for r in sql),
 'note':'Counts include separate SQLite FTS internals; not equivalent to remote DB round trips. Trace instrumentation raised run duration; use original22.930seconds for historical timing.'}
put(ART/'sql-summary.json',summary)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=True)
m['retrieval_accounting']['stage_ledger']['summary_run_id']='run-001'
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'Previously recorded1086trace, no fresh baseline rerun','residual_seconds':h['residual_seconds']},'observed':{'status':'complete','protected_requests_exact':9,'recorded_responses_used':9,'views':4,'final_answer_exact':True,'one_second_target_achieved':False}},comparisons=[{'kind':'input/output equivalence diagnostic','result':'9/9requests and final limited answer exact; no performance improvement comparison'}],usage={'new_model_calls':0,'new_tokens':0,'new_cost_usd':0},latency={'historical':h,'profile_request_seconds':result['request_seconds'],'trace_instrumentation_overhead_present':True,'performance_improvement_claimed':False},error_taxonomy=[{'kind':'historical_judgment_id_duplicate_missing_wrong_basis','observed':True},{'kind':'historical_repair_generic_diagnostics_and_unchanged_bad_judgments','observed':True},{'kind':'historical_alias_number_changes_with_stale_prose','observed':True},{'kind':'profile_trace_high_overhead','observed':True},{'kind':'setup_raw_response_envelope_assumption','observed':True,'when':'before freeze or execution; corrected raw choices path; no product calls'}],main_wiring='unchanged',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
meta=re.sub(r'(?m)^status:.*$','status: Accepted',meta)
parts=[
('결정 요약','기존22.930초를 원래 이벤트로 분해하고 같은9응답 native재생에서 병목과 ID복구 결함을 확인했다. Accepted는 진단의 재현성에 대한 결정이며 속도 개선·정답률·1초 달성 인증이 아니다. MAIN106 불변. 읽기 문서는 [TXT](artifacts/22초와_ID복구_진단.txt).'),
('문제와 변경 전 구조','MAIN106에 통합된1086제품 바이트를 원래 binding으로 실행했다. 용어집을 제외하고1초를 목표로 하지만 화면41.269초와 잔여22.930초 모두 줄여야 한다. 현재 후보20제시는 메뉴 준비 후 페이지를 자르는 단계다.'),
('가설과 사전 판정 기준','design/criteria.json과 freeze.json에 원본9입력/응답·코드·프로필·데이터·스크립트·리소스 한도를 동결했다. 생성뷰ID와 확인된 실행/질문ID 외 보호입력·최종답변이 같아야 하며 새 모델0회, 재생1회, 최초 불일치 중단이다.'),
('실험 설계','baseline은 완료1086/compact의 기존 기록, observed는 같은 코드·데이터·선택을 재생한 계측만이다. 제품 후보/스키마/프롬프트를 새로 바꾸지 않아 code_isolation not_applicable이다. 알려진 질문1개이며 decision_eligible=false다.'),
('데이터·모델·재현성','fsc-hard-005의 literal응답9개, 실제 native HTTP, 네트워크 차단. 원래431? 등의 추정 없이 freeze의430연구코드와 선택MAIN106의429서빙 해시를 대조했다. 새 모델·토큰0. 원문·권한·상태 검증을 실행했다. 법률 기준답변 재평가 없음.'.replace('원래431? 등의 추정 없이 ',' ')),
('결과',f'보호입력9/9·최종답변 동일,4화면. 원래잔여{h["residual_seconds"]:.6f}초: PLAN3.437, RECALL6.562, SELECT나머지9.676, READ0.373, 평가/답변1.024,기타1.858. 전체초기준비를 빼도64.200초다. trace재생134.398초는 측정부하가 커 속도비교에 사용하지 않는다.'),
('사례별 오류 분석','새J6필요에 기존6개까지7행을 작성하며J1중복·J6누락·J2/J1근거오연결. 보완은 일반오류만 제공, 잘못된7행 그대로 반복. D4가 다른 문서로 바뀌어도 과거finding문장D4는 남아 있다. 보완예산 공유로 추가조사재진입 행동0. raw response포맷 준비 오류는 동결 전에 수정했으며 호출·결과를 바꾸지 않았다.'),
('비용·지연·회수 규모','새모델0·비용0. 원래회수정책·목록·정렬 불변, 완료부모 회수원장을 상속했다. 단건원문조회92,298회·용어범위107회. FTS내부까지 포함한trace총수와 원격DB횟수를 구분한다. 상세 samples와 중첩 spans는 더하지 않는다. peakRSS3.09GiB,종료가용6.66GiB.'),
('해석','PLAN에서documents만쓰는데전체용어범위까지조회, 반복FTS와scope캐시우회, 원문단건조회/파일확인, 스키마자기검사 반복이 병목이다. 모델출력ID의 관계조립 부담과 구체오류진단 부재가 확인됐다. 이 구조가 성공률에 미치는 인과효과는 별도후속 검증 대상이다.'),
('한계와 일반화 가능 범위','기존1질문 재생이며 새질문 품질·GENOS Oracle 현장성능·1초달성 미검증. SQLtrace가18백만여내부콜백까지 계측해 부하가 커졌다. 원래22.930초 배분은 원래시각만 사용하고 샘플수치는 병목위치 추정에 한정한다.'),
('운영 결정·롤백 조건','제품수정/새MAIN승격 없음. 후속은 PLAN법령명전용, 범위결속FTS결과재사용, 현재20개메뉴만본문계산, 묶음원문/검증기재사용, 안정별칭/새판단전용응답/행별복구진단 순으로 설계한다. 원문·권한·상태검증을 제거하거나 실패예산을 무제한 초기화하지 않는다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_1093/prepare.py → profile.py → analyze.py → finish.py. 완료경로는 덮어쓰지 않는다. 후속 재생은 새ADR로 동결한다. 실행runtime은 압축해 파일별해시를 검증했고 원본1086실패기록은 보존했다. stable validate --final, graph 검사 기록을 artifacts에 남긴다.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 비LLM 잔여시간·판단 ID 진단\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(parts,1))+'\n')
(ADR/'실험/README.md').write_text('# 단일 보관응답 진단\n\n[읽기용 TXT](../artifacts/22초와_ID복구_진단.txt) · [고정 입력](../artifacts/design/freeze.json) · [재생 결과](../artifacts/run-001/result.json). 새 모델0회,9개입력·최종제한답변 동일. 품질 평가나1초달성 결과가 아니다.\n')
paths=[x for x in ART.rglob('*') if x.is_file() and x!=ART/'manifest.json']+list(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1093','created_at':m['reservation']['created_at'],'updated_at':datetime.now(timezone.utc).isoformat(),'files':[dict(bound(x),bytes=x.stat().st_size,description='Historical nonmodel attribution and literal replay diagnostic',contains_raw_prompts_and_outputs=x.suffix in ('.gz',)) for x in paths]})
print('Diagnostic completed, literal9responses preserved, runtime archive verified, MAIN106 unchanged')
