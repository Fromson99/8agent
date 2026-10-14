"""Publish measured full-request results and bounded engineering conclusions."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0706-fused-request-entry-e2e';O=A/'artifacts/run-001';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');s=read(O/'summary.json');q=read(O/'quality-review.json');f=read(D/'freeze.json');dataset=read(D/'dataset.json')
table='| 질문 | 기존 전체 시간·LLM | 통합 전체 시간·LLM | 최종 응답 |\n|---|---:|---:|---|\n'
for case in dataset['cases']:
 rows={x['arm']:x for x in s['cases'] if x['case_id']==case['case_id']};b=rows['baseline'];c=rows['fused-entry']
 table+=f"| {case['case_id']} | {b['request_seconds']:.3f}초 · {b['model_calls']}회 | {c['request_seconds']:.3f}초 · {c['model_calls']}회 | 기존 {'답변' if b['answer_completed'] else '실패'} / 후보 {'답변' if c['answer_completed'] else '실패'} |\n"
front='| 질문·방식 | 앞단 호출·시간 | 모델 전체 시간 | 요청 중 나머지 처리 |\n|---|---:|---:|---:|\n'
for x in s['cases']:
 g=x['groups'].get('front',{});front+=f"| {x['case_id']} / {x['arm']} | {g.get('calls',0)}회 · {g.get('seconds',0):.3f}초 | {x['model_seconds']:.3f}초 | {x['non_model_seconds']:.3f}초 |\n"
findings='\n'.join('- '+v for v in q['findings'])
sections=[
 ('결정 요약','앞단 4콜→1콜 연결은 작동했지만 **이 후보는 채택하지 않는다**. CM018에서 배경 문맥을 적용 질문으로 확대해 전체 시간·호출이 증가했다. 일반 새 질문의 앞단을 격리 후보에 구현하고, 실제 `/v1/rag/ask` 핸들러에서 기존/후보 각각 3질문을 최종 응답까지 실행했다. 앞단 단독 시간으로 성능을 주장하지 않는다. MAIN48·작업 제품 파일·GENOS는 변경하지 않았다.\n\n'+table),
 ('문제와 변경 전 구조','현재 MAIN48의 새 법률 질문은 source-request-route → memory-resolve → memory-command-check → memory-intent의 네 모델 호출 뒤에 탐색을 시작한다. 앞단을 합치더라도 자료 초기 준비와 반복 탐색·판단 비용은 남는다.'),
 ('가설과 사전 판정 기준','[사전 동결 기준](artifacts/design/criteria.json): 새 사건의 분류·명령·INTENT를 한 번에 받고 형식·권한·상태는 서버가 검사한다. 완료하던 질문의 실패 전환·명시 요구 삭제·인용/권한/상태 회귀를 확인하며, 전체 시간과 실제 호출 수는 실패를 포함해 기록한다. 기존 대화의 정정·복원·경험 재사용·실패 재개는 기존 경로를 유지한다. 이 probe는 일반 품질 인증이나 MAIN 승격 근거가 아니다.'),
 ('실험 설계','ADR0706 선점 → 공개 질문·6회 순서·기준 동결 → MAIN48에서 후보 snapshot → 계약 검사 → 코드/실행기 freeze → 준비 검사0콜 → 같은 API의 전체 실행6회. 반복 측정과 별도 모델 채점은 하지 않았다. 각 요청은 새 프로세스와 독립 runtime·세션을 사용했고 OS 파일 캐시를 비우지 않았다. 같은 프로필·65개 공개 문서·자료 세대·모델을 사용한다. 후보의 request_entry_policy만 fused-v1이며 검색·읽기·ASSESS 프롬프트·COMPOSE 동작은 바꾸지 않았다. 앞단이 만드는 검색어·쟁점은 달라질 수 있다.'),
 ('데이터·모델·재현성','[질문과 실행 순서](artifacts/design/dataset.json), [코드·데이터·실행기 해시](artifacts/design/freeze.json). MAIN48 compact-progress-20261009-r1 / 원문 term-source-8729f978a28924cb8c5b / 공개 허용65문서. H02·H03의 공개 법령 질문과 기존 CM018을 선택한 in-sample probe다. 비공개 질문·정답은 제품에 전달하지 않았다. Qwen3.8 / qwen/qwen3.8-27b, OpenRouter Parasail FP8 단독, reasoning none, fallback 없음, ExperimentClient 사용. 로컬 API의 요청 시작부터 최종 JSON 응답까지이며 브라우저/외부 HTTP 네트워크 지연은 포함하지 않는다. 앱 생성 시간은 각 result.json에 별도 기록한다. cProfile은 사용하지 않았다.'),
 ('결과',table+'\n'+front+'\n[집계와 호출별 원장](artifacts/run-001/summary.json). 각 요청의 result.json에 물리 호출의 작업·시간·입출력 토큰·provider 결과, 최종 실행 통계를 남겼다. 요청이 실패한 경우에도 실패 직전까지의 모든 호출을 포함한다. 앞단 시간과 전체 시간은 중복 합산하지 않는다.'),
 ('사례별 오류 분석',findings+'\n\n[검토 범위와 관측 근거](artifacts/run-001/quality-review.json). HTTP200·인용 계약 통과는 법률 정답 인증이 아니다. 필수 근거 gold를 불러오지 않아 정답률·gold recall은 미측정이다. 실패 원문과 거절·수정 이력도 압축 원본에 보존했다.'),
 ('비용·지연·회수 규모','[실험 manifest](실험/manifest.json)의 results.usage와 latency에 arm별 실제 합계를 기록했다. [회수 원장](artifacts/run-001/retrieval-ledger.json.gz)은 허용 조문 catalogue → 실제 확보 → 모델 원문 전달을 구분하며 최종 채택은 각 diagnostic.json에 따로 남긴다. 확보와 전달 수는 문서 전체 열람이나 법적 근거 채택 수가 아니다. 서로 다른 질문 각1회이므로 모집단 p50/p95나 안정적인 평균 개선률로 일반화하지 않는다.'),
 ('해석','통합 앞단은 모델의 분류·새 명령·쟁점 출력을 한 번에 받아 기존 7개 단계 저장 경로로 넘긴다. 별도 의미 검증 LLM을 생략하는 대신 닫힌 출력 계약, 명령 정규화, 허용 문서 범위, 사용자 사실의 인용 원문, 중복 쟁점, 요청·주체·프로필/코드/데이터·상태 해시를 검사한다. 이는 의미 정확성의 증명은 아니다. 잘못된 제안은 비공개 로그에 남기고 한 번만 수정 요청하며, 두 번째 거절은 실패 처리한다. 기존 경로로 몰래 되돌아가거나 다른 모델을 부르지 않는다.\n\nrequest_entry.py가 새 기능의 담당 모듈이고 CaseRepository.direct_request/resolve → ShortcutCases → CompletionExecution.INTENT가 실제 소비 경로다. 새 결과는 현재 요청에만 결속된다. 영속된 사건·노드·판단 수락·최종 공개 계약은 그대로다. 새 요청 이후의 정정/복원/재개는 이번 통합 대상이 아니다.'),
 ('한계와 일반화 가능 범위','새 경계 검사20개 통과. 추가 기존 대화 회귀 검사는 양쪽 각각25통과·12실패로 동일했다. 12개는 캐시 재요청에서도 최초 응답 전체가 동일해야 한다는 오래된 단언에 새 실행 통계(최초1콜/재요청0콜 및 실제시간)가 포함돼 생긴 실패다. 테스트 파일을 바꾸거나 통과로 재분류하지 않았고 XML·로그를 보존했다. 새로운 데이터의 out-of-sample 품질·반복 지연 분산·운영 대화 이력·GENOS 내부 모델 성능은 미확인이다. 검색어·쟁점 출력과 후속 모델 판단도 달라질 수 있으므로 전체 시간 차이를 오직 없앤 세 호출의 효과로 단정하지 않는다. 새 phase request-entry의 공개 실행 통계 목적명은 현재 일반 model 라벨이며, 실제 단계명과 개별 시간은 원시 원장에 보존된다. 표시명 개선은 후속 범위다.'),
 ('운영 결정·롤백 조건','상태 Proposed, phase probe, in_sample=true, decision_eligible=false. 결과를 본 뒤 후보/프롬프트/질문을 수정하거나 같은 ADR에서 재실행하지 않았다. 통합 코드는 candidate snapshot과 frozen revision에만 있다. 활성 포인터 generation48과 기존 작업 제품 파일의 해시를 다시 확인했다. 운영 활성화가 없어 서비스 롤백은 필요하지 않으며 후속 개선은 새 ADR에서 동결한다. Git main 병합·제품 MAIN 승격·GENOS 반입·배포는 모두 수행하지 않았다.'),
 ('재현 명령','동결 실행기 `06_TOOLS/EXPERIMENTS/adr_0706/run.py --arm <baseline|fused-entry> --case <ID>`는 기존 결과 디렉터리 덮어쓰기를 거부한다. 재실행/새 표본은 새 ADR에서 진행한다. [동결 코드](artifacts/design/freeze.json), [계약 검사](artifacts/entry-contracts.xml), [압축 원본](artifacts/run-001/raw.tar.gz), [해시·복원 영수증](artifacts/run-001/raw-archive.json)을 보존했다. 모든 provider system/user/schema/원응답과 runtime journal은 원바이트로 압축·검증한 뒤 중복 복사본만 정리했다. 새 빈 디렉터리로 복원해 검증할 수 있다.')]
fm=f'---\nadr_id: ADR-0706\ntitle: 앞단 요청 해석 통합의 실제 API 전체 실행 비교\nstatus: Proposed\ndecision_date: 2026-10-09\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m["reservation"]["created_at"]}\nupdated_at: {m["reservation"]["updated_at"]}\nowner: Codex\nwork_status: in_progress\n---\n\n'
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
for question in m['questions']:
 case=next(c for c in dataset['cases'] if c['case_id']==question['case_id']);ident=case['case_id']
 calltable='| 방식 | 호출 | 단계 | 초 | 입력 토큰 | 출력 토큰 |\n|---|---:|---|---:|---:|---:|\n'
 for arm in ('baseline','fused-entry'):
  r=read(O/arm/ident/'result.json')
  for u in r['usage']:calltable+=f"| {arm} | {u['call']} | {u['phase'].split('-',2)[2]} | {u['seconds']:.3f} | {u['input_tokens']:,} | {u['output_tokens']:,} |\n"
 links='\n'.join(f'- {arm}: [실제 요청](../artifacts/run-001/{arm}/{ident}/request.json), [최종 반환·개별 사용량](../artifacts/run-001/{arm}/{ident}/result.json), [경로·근거·앞단 출력 진단](../artifacts/run-001/{arm}/{ident}/diagnostic.json)' for arm in ('baseline','fused-entry'))
 body=f'''# {ident} · 앞단 통합의 전체 요청 비교

## 1. 실행 메타

run-001 / baseline, fused-entry / 각각 새 프로세스1회 / Qwen3.8 Parasail FP8. 알려진 질문 probe, 제품 호출 후 후보 변경 없음.

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

승인 정답·필수 근거를 불러오지 않았다. 목적은 실제 전체 요청의 시간/호출과 앞단 요구 보존 확인이며 법률 정답률은 채점하지 않는다.

## 4. 제품 입력을 구성한 원값

{links}

### 회수·탈락 단계 원장 — run·arm별

[조문별 확보·전달 원장](../artifacts/run-001/retrieval-ledger.json.gz), 각 diagnostic.json의 최종 채택 ID를 구분한다. gold recall은 미측정이다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

{calltable}

각 실제 system/user/schema/provider 원응답은 [압축 원본](../artifacts/run-001/raw.tar.gz)의 `<arm>/{ident}/provider/call-*`에 보존했다. [해시·복원](../artifacts/run-001/raw-archive.json). 원문을 보고서마다 반복 복사하지 않는다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

위 표는 앞단·탐색·판단·수정의 모든 물리 호출이다. 실패·재시도도 포함했다. 코드 함수 실행·SSE 카드 갱신을 LLM 호출로 세지 않았다.

## 7. 채점 호출과 반복 판정

별도 judge 호출0회. 1회 관측으로 품질 인증이나 반복 지연 통계를 만들지 않았다.

## 8. 사례 최종 판정

{table}

[수동 검토와 남은 문제](../artifacts/run-001/quality-review.json). 모든 후보는 연구 snapshot이며 MAIN 불변이다.
'''
 path=A/'실험'/question['file'];path.write_text(body);question['sha256']=sha(path)
m['results']['error_taxonomy']=q['errors'];m['results']['engineering_checks']=q['engineering_checks'];put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 앞단 통합 전체 실행 비교\n\n'+table+'\n원시 호출·실패·제약은 [상위 기록](../README.md)을 따른다. MAIN 변경 없음.\n')
index=R/'04_EXPERIMENTS/ADR/README.md';old=index.read_text()
if 'ADR-0706-fused-request-entry-e2e/README.md' not in old:index.write_text(old.rstrip()+'\n- [ADR-0706 앞단 요청 해석 통합 E2E](ADR-0706-fused-request-entry-e2e/README.md) — 새 질문 앞단 통합 후보, 공개3질문 두 방식 전체 요청6회; MAIN 불변.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0706','created_at':m['reservation']['created_at'],
 'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,
           'description':'Frozen entry comparison, actual end-to-end requests, source/call accounting and preserved failures',
           'contains_raw_prompts_and_outputs':p.name=='raw.tar.gz'} for p in sorted((A/'artifacts').rglob('*')) if p.is_file() and p.name!='manifest.json']})
print(table)
