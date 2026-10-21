"""Summarize completed observations and losslessly seal closed test state."""
from pathlib import Path
import gzip,hashlib,json,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0855-fulltext-schema-live-audit-v2'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
s=read(A/'artifacts/summary.json');boundaries=read(A/'artifacts/boundary-audit.json');calls=[];raw=[]
for case in s['cases']:
 D=A/'artifacts'/case['run_id']
 calls += [{**c,'run':case['run_id']} for c in read(D/'calls.json')]
 for path in (D/'provider').glob('call-*/response.json'):
  r=read(path);ch=(r.get('choices') or [{}])[0]
  raw.append({'run':case['run_id'],'call':int(path.parent.name.split('-')[1]),'finish_reason':ch.get('finish_reason'),'response_file':str(path.relative_to(R)),'sha256':sha(path),'model':r.get('model'),'provider':r.get('provider')})
missing=[b for b in boundaries if "'queries' is a required property" in str(b.get('reproduced_reconstruction_error'))]
targets=[b for b in boundaries if "is not one of" in str(b.get('reproduced_reconstruction_error'))]
lengths=[r for r in raw if r['finish_reason']=='length']
assert len(missing)==9 and len(targets)==1 and len(lengths)==2
assert all(b['raw_matches_wire_schema'] and b['wire_matches_selected_projection'] for b in boundaries)
d={'verdict':'SCHEMA_RECONSTRUCTION_MISMATCH_REPRODUCED','cases':2,'actual_model_calls':s['model_calls'],'public_model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','fulltext_preflight_pass':2,'canonical_rejections':len(boundaries),'missing_queries_rejections':len(missing),'action_target_rejections':len(targets),'length_stops':len(lengths),'all_returned_complete_outputs_match_wire_schema':all(not c.get('raw_output_schema_errors') for c in calls),'all_captured_schemas_valid':all(c.get('schemas_valid') for c in calls),'answer_count':s['answer_count'],'provider_raw_receipts':raw,'observed_cause':'_union intersects required keys across projected alternatives. A fixed-empty queries alternative removes queries from its wire required/properties, making queries optional in the combined menu. READ/OPEN/FOLLOW alternatives still require queries in the canonical parent and do not have a fixed literal to reconstruct; model omission passes the wire and fails expand().','secondary_boundary':'Combined target enum accepts values belonging to other actions; actual canonical action validation correctly rejects READ_SCOPE with an incompatible target. This is permissive generation with preserved authorization, not evidence of an unauthorized action executing.','user_visible_failure':'run-002 returns HTTP422 review_incomplete with a request-to-clarify message although the actual failure is queries reconstruction.','photograph_causality':'Not established. Field timeout had no response/HTTP status; field serving hash and exact schema unavailable. No claim that this reproduces GENOS 180s transport timeout.','timing_limitations':'End-to-end times include cold initialization/preflight and audited recording. Runs overlapped during part of run-001. Not an isolated latency benchmark or before/after comparison.','repair_direction':['For actions that do not consume search queries, explicitly define queries as a fixed empty array and reconstruct it in the host; do not invent missing search terms for search actions.','Preserve conditional action-target constraints in the compact wire or an equally explicit action selection contract.','Separate output-schema/codec failure from question insufficiency in the displayed failure classification.','Validate a separately frozen candidate against these recorded boundaries and fresh fulltext calls before updating MAIN or rebuilding GENOS handoff.'],'production_mutations':False,'genos_execution':False}
put(A/'artifacts/schema-diagnosis.json',d)
findings='''MAIN82 fulltext 실제 스키마 실험 결과 — ADR-0855

결론: 현재 압축 버전에 모델 전송 스키마와 서버 복원 계약의 불일치가 재현됐다.

1. 범위
현재 활성 MAIN82의 코드370파일·프로필·선택 원문·fulltext를 고정했다.
공개 합성 질문2개, 외부 Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음.
GENOS 현장 실행이나 사진 속 동일 요청의 재현은 아니다.

2. 실제 결과
- fulltext 색인 스키마와 실제 scoped 조회: 2/2 통과. UnitFulltextIndex가 선택된 semantic-unit-fulltext-v1을 읽었다.
- 고난도 금융투자상품 질문: 모델20회, 약643.37초, 최종HTTP200·답변1731자. 법률 정답률은 채점하지 않았다.
- 이해상충·정보교류 차단 질문: 모델3회, 약62.59초, 최종HTTP422·답변 없음.
- 총23회. 서버 출력 스키마 거절10회: queries 누락9회 + 행동별 대상 불일치1회.
- 그 외 로컬 출력6400토큰 한도 종료2회. GENOS의 한도와 같다는 의미는 아니다.
- 전체 입력346452 / 출력26726토큰, 기록된 비용USD0.1355404.

3. 재현된 불일치
모델이 받은 압축 스키마: queries 선택값.
서버의 원래 JSON 계약: queries 필수값.
모델이 READ_ARTICLES, READ_SCOPE 등의 행동에서 queries를 생략하면,
전송받은 스키마는 통과하지만 minimal_output.expand에서 거절된다.
'queries' is a required property 오류가 실제 원응답과 선택 코드로 재현됐다.
모든 완성된 원응답은 모델에 전달한 스키마를 통과했다. JSON 문법 자체의 문제가 아니다.

압축 과정에서 행동별 required의 교집합을 취한다. 일부 행동의 고정 빈 배열을
모델 출력에서 제거하면서, 다른 행동에서 여전히 필요한 필드까지 공통 필수 목록에서
빠진다. 모델에게는 불필요한 선택값을 쓰지 말라고 지시한 반면 서버는 이를 요구한다.

4. 추가 관찰
행동별 대상 enum을 하나로 합쳐, 다른 행동의 대상을 고르는 출력도 전송 스키마는
통과할 수 있다. 서버는 실제 행동의 허용 대상과 대조해 거절했다. 권한 우회 실행은 관찰되지 않았다.
두 번째 질문의 사용자 응답은 질문을 더 구체화하라는 문구였지만 실제 원인은 위 복원 오류였다.

5. 현장 사진과의 관계
사진의 response_format 78856B와 timeout만으로 LLM 과부하를 확정할 수 없다.
이번 첫 탐색 전송 스키마는4291B(포맷 포함4384B)였지만 원본 계약은105245B였다.
스키마 크기가 줄어도 복원 계약이 어긋나면 수정 호출·조사 중단이 발생함을 확인했다.
사진의 현장 코드 해시와 정확한 스키마가 없으므로, 180초 timeout의 동일 원인이라고 단정하지 않는다.

6. 수정 방향과 적용 상태
검색어가 필요 없는 행동의 빈값은 시스템이 확정 조립하고, 검색 행동의 실제 검색어는
모델 필수값으로 유지해야 한다. 행동별 대상 제약도 압축된 계약에 명시해야 한다.
완료된 이 실험에서 제품 코드·MAIN82 포인터·데이터·기존 GENOS ZIP은 변경하지 않았다.
후속 수정 후보를 별도 동결·검증한 뒤 MAIN/ZIP 갱신이 필요하다.

7. 근거
artifacts/schema-diagnosis.json: 판정·원인·원응답 해시
artifacts/boundary-audit.json: 실제 전송 스키마 통과/서버 복원 실패 대조
artifacts/summary.json: 질문별 결과·토큰·비용·지연
실험/README.md: 질문별 원본 입력·중간 호출·원응답·회수 원장

시간은 사전 조회·초기화·감사 기록을 포함하며 일부 구간 두 요청이 겹쳤다.
이 수치를 GENOS 성능 또는 단독 요청의 속도 인증으로 해석하지 않는다.
'''
(A/'FINDINGS.txt').write_text(findings)
p=A/'README.md';text=p.read_text().replace('status: Proposed','status: Rejected',1)
start=text.index('## 1. 결정 요약');end=text.index('## 2. 문제와 변경 전 구조')
text=text[:start]+'''## 1. 결정 요약

**스키마/복원 일치 가설은 기각했다.** 실제 fulltext 사전 조회는2/2 통과했지만, 압축 출력에서 `queries`를 생략하면 원래 필수 계약과 충돌했다. 완성된 모델 응답은 모두 전송받은 스키마를 만족했다. 서버 거절10회(queries9, 행동별 대상1), 로컬 출력 한도 종료2회가 발생했다. 질문별로 모델20회/643.37초/HTTP200, 모델3회/62.59초/HTTP422였다. 답변의 법률 정확도는 채점하지 않았다.

[읽기 쉬운 결과](FINDINGS.txt) · [기계 검증 근거](artifacts/schema-diagnosis.json) · [실제 복원 경계](artifacts/boundary-audit.json)

MAIN82·데이터·GENOS·기존 ZIP은 변경하지 않았다. 이 실험은 현재 경로의 결함 진단이며 수정본 승격이 아니다.

'''+text[end:]
start=text.index('## 9. 해석');end=text.index('## 10. 한계와 일반화 가능 범위')
text=text[:start]+'''## 9. 해석

`minimal_output._union`은 압축 대안의 필수 키 교집합을 취한다. 고정 빈 배열을 생략하는 대안 때문에 `queries`가 전송 스키마에서 선택값이 되지만, 다른 행동의 원본 계약에는 필수이며 고정값도 없어 복원되지 않는다. 첫 사례7회·두 번째2회 재현했다. 실제 원응답을 바꾸지 않고 선택 코드의 Projection에 입력해 같은 오류를 확인했다. 행동별 대상의 합집합으로 생긴1건의 잘못된 선택은 서버에서 정상 차단했다.

두 번째 사례의 최종 문구는 질문을 구체화하라는 안내지만, 원시 실패는 복원 오류다. 사용자 질문이 부족하다는 근거로 보지 않는다. 사진의 timeout과 같은 원인임은 입증하지 못했다. 실행 일부가 겹쳤고 감사·초기화 비용을 포함하므로 속도 비교 지표로 사용하지 않는다.

'''+text[end:];p.write_text(text)
# Only databases under these two completed audit runtimes are archived. No selected
# source data, release, personal state, or shared cache is removed.
archives=[]
for run in ('run-001','run-002'):
 for folder in ('runtime','preflight-runtime'):
  for p in sorted((A/'artifacts'/run/folder).rglob('*')):
   if not p.is_file() or p.is_symlink() or '.sqlite' not in p.name or p.name.endswith('.gz'):continue
   h=sha(p);n=p.stat().st_size;out=p.with_name(p.name+'.gz');assert not out.exists()
   with p.open('rb') as src,gzip.open(out,'wb',compresslevel=9) as dst:shutil.copyfileobj(src,dst)
   with gzip.open(out,'rb') as z:assert hashlib.file_digest(z,'sha256').hexdigest()==h
   archives.append({'original':str(p.relative_to(R)),'sha256':h,'bytes':n,'archive':str(out.relative_to(R)),'archive_sha256':sha(out),'archive_bytes':out.stat().st_size,'restore':'Decompress to original filename in an isolated inspection directory; restore all accompanying WAL/SHM before opening. Never overwrite serving state.'});p.unlink()
put(A/'artifacts/runtime-archives.json',archives)
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json']+list((R/'06_TOOLS/EXPERIMENTS/adr_0855').glob('*.py'))+[A/'FINDINGS.txt']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0855','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(files)]})
print(json.dumps({'verdict':d['verdict'],'missing_queries':len(missing),'other_schema_rejections':len(targets),'length_stops':len(lengths),'archives':len(archives),'bytes_saved':sum(x['bytes']-x['archive_bytes'] for x in archives)},ensure_ascii=False))
