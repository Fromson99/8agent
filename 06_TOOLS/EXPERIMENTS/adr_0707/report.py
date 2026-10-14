"""Measured candidate report; no model or product changes."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0707-grounded-law-title-entry';O=A/'artifacts/run-001';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');s=read(O/'summary.json');review=read(O/'quality-review.json');trace=read(O/'trace-review.json');dataset=read(D/'dataset.json')
table='| 질문 | 이전 통합 앞단 후보 | 제목 힌트·도구 선택 후보 |\n|---|---:|---:|\n'
for case in dataset['cases']:
 rows={r['arm']:r for r in s['cases'] if r['case_id']==case['case_id']}
 cells=[]
 for arm in ('baseline','title-entry'):
  r=rows[arm];cells.append(f"{r['request_seconds']:.3f}초 / {r['model_calls']}회 / HTTP{r['http_status']}")
 table+=f"| {case['case_id']} | {' | '.join(cells)} |\n"
findings='\n'.join('- '+x for x in review['findings'])
sections=[
 ('결정 요약',review['decision']+'\n\n'+table+'\n기준은 **ADR0706 fused-entry**이며 현재 서비스 MAIN48과의 직접 비교가 아니다. 최신 수정은 격리 후보에 있으며 로컬 MAIN·GENOS는 변경하지 않았다.'),
 ('문제와 변경 전 구조','현재 문서 name은 폴더 경로를 포함하는 표시 이름이다. 실제 document_title을 사용하지 않으면 정식 법명을 부분 일치로 낮추고 미등록 약칭을 놓친다. 기존 앞단은 제목의 어떤 부분이 실제 이름과 맞는지 받지 못했고, 통합 후보는 배경 문맥을 추가 적용 과제로 확대하기도 했다. 활성 MAIN은 구조 우선 정책이며 후보 성공과 구분한다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). 문장과 실제 제목/등록 약칭을 모델 없이 대조하고 같은 요청 해석 호출에서 STRUCTURE/FULLTEXT를 고른다. 잘못된 ID·원문 밖 배경 인용은 호스트가 거절한다. 구조 설명은 선택한 항 전체의 본문/단서/하위 항목 전달을 검사한다. 추가 적용 질문 생성·실패 전환·권한/인용/저장 회귀를 기록한다. 난이도별 예산 조정은 이번 범위에서 제외했다.'),
 ('실험 설계','ADR0707 선점 → 기준/질문/6요청 순서 동결 → MAIN48과 부모 차이 확인 → 후보 snapshot 선별 통합 → 계약 검사 → 해시 freeze → 실제 API 6회. 각 요청은 새 프로세스·독립 runtime, OS 캐시는 비우지 않는다. 1회 관측 probe이며 결과 확인 후 제품 코드·프롬프트·질문을 수정하거나 재실행하지 않는다.'),
 ('데이터·모델·재현성','[동결 지문](artifacts/design/freeze.json): 부모 ADR0706/fused-entry/rev-001; 후보 ADR0707/title-entry/rev-001; 공개65문서와 term-source-8729f978a28924cb8c5b를 공유한다. Qwen3.8 qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none / fallback 없음 / ExperimentClient. 공개 법령 질문과 합성 본문 질문만 사용했다. HTTP 핸들러 TestClient의 요청 시작→최종 응답 시간이며 브라우저·외부 네트워크 시간은 제외된다. 준비/프로세스 시간은 별도 보존.'),
 ('결과',table+'\n[전체 응답 요약](artifacts/run-001/summary.json), [실패 포함 모든 물리 호출](artifacts/run-001/physical-call-ledger.json), [제목 힌트·첫 검색·행동·원문 범위](artifacts/run-001/trace-review.json). 각 result.json에는 최종 응답과 실제 provider 시도별 시간·토큰이 있다. 실패와 보정도 포함한다. LLM 출력 JSON의 행동 수를 모델 호출 수로 세지 않았다.'),
 ('사례별 오류 분석',findings+'\n\n[품질 검토](artifacts/run-001/quality-review.json). HTTP200은 법률 정답 인증이 아니다. 승인 정답/필수 근거 gold와 별도 LLM judge는 사용하지 않았다.'),
 ('비용·지연·회수 규모','[manifest](실험/manifest.json)의 results.usage/latency와 [회수 원장](artifacts/run-001/retrieval-ledger.json.gz)을 따른다. 허용 조문 집합→확보→실제 모델 원문 전달을 측정하고 최종 채택은 별도 기록했다. 제목 힌트는 권한 범위나 회수 대상의 hard filter가 아니다. 표본마다 1회이므로 안정적 평균 개선률·p50/p95·gold recall을 주장하지 않는다.'),
 ('해석','law_title_hints.py는 실제 document_title과 등록 document_aliases만 사용한다. 정확 제목·등록 약칭·제목 부분 일치·미등록 약칭의 글자 순서 유사 후보를 구분하고 문장/제목의 원문 위치를 제공한다. 최대6개와 전체/생략 수를 보내며 미등록 약칭을 정본에 쓰지 않는다. 제목 단서가 없다는 것은 관련 법률이 없다는 뜻이 아니다.\n\nCaseRepository → request_entry.run → 같은 1회 응답의 search 선택 → SourceRecall/law_candidates → law_navigation으로 연결했다. 요청 task는 원문을 보존하고 context_quotes는 별도 기록한다. 구조 좌표와 본문 검색은 선택 가능한 도구다. 기존 묶음 읽기·실제 전달·채택·판단 검사는 유지한다. 제목 힌트만으로 원문을 읽거나 법적 적용을 확정하지 않는다. 코드상 인용/권한 검증은 의미적 정답이나 배경 범위 보존의 증명이 아니다.'),
 ('한계와 일반화 가능 범위','새 경계·검색 도구·기존 묶음 읽기 검사46개 통과. 추가 구조 검색 회귀군에서는 기존 부모와 후보에 같은 4개 실패가 있었다(옛 합성 source choice가 명시 adoption status를 누락). 실패를 통과로 바꾸지 않았고 XML/log를 보존했다. 초기 테스트 실행기의 import 경로/중복 이름 오류도 보존했다. 초기 후보 등록에서 --target-path 대신 --target이 필요했던 실행기 오류는 모델0회 상태에서 수정했다. 새 의미 평가/지연 분산/기존 대화 이력에서 새 정책의 효과/GENOS 성능은 미확인이다.'),
 ('운영 결정·롤백 조건','Proposed / probe / in_sample=true / decision_eligible=false. 실제 제목 매칭과 도구 선택의 구현 후보를 검증한 상태다. 최초 요청 통합은 기존 사건/재개/기억 요청을 기존 경로로 보내는 가드를 유지한다. 신규 난이도별 예산 정책은 만들지 않았다. 제품 작업 파일·활성 릴리스는 변경하지 않으며 Git main 병합·제품 MAIN 승격·GENOS 반입/배포를 수행하지 않는다. 별도 일반화 검증 후 같은 코드의 통합·승격·포인터·실제 서비스 binding을 확인해야 한다.'),
 ('재현 명령','동결 실행기 `06_TOOLS/EXPERIMENTS/adr_0707/run.py --arm <baseline|title-entry> --case <ID>`는 기존 결과 덮어쓰기를 거부한다. 후속 호출은 새 ADR을 사용한다. [계약 검사](artifacts/contracts-passed.xml), [압축 원본](artifacts/run-001/raw.tar.gz), [해시·복원 영수증](artifacts/run-001/raw-archive.json). 모든 실제 provider 입력·schema·원응답과 runtime journal을 해시 검증 후 무손실 압축했다. 복원은 새 빈 디렉터리에서 한다.')]
fm=f'---\nadr_id: ADR-0707\ntitle: 문장과 실제 법령 제목의 일치 힌트 및 검색 도구 선택\nstatus: Proposed\ndecision_date: 2026-10-09\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m["reservation"]["created_at"]}\nupdated_at: {m["reservation"]["updated_at"]}\nowner: Codex\nwork_status: in_progress\n---\n\n'
(A/'README.md').write_text(fm+'\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
for q in m['questions']:
 case=next(c for c in dataset['cases'] if c['case_id']==q['case_id']);cid=case['case_id']
 calls='| 방식 | 호출 | 단계 | 초 | 입력 토큰 | 출력 토큰 |\n|---|---:|---|---:|---:|---:|\n'
 for arm in ('baseline','title-entry'):
  r=read(O/arm/cid/'result.json');us={u['call']:u for u in r['usage']}
  for u in r['attempts']:
   tokens=us.get(u['call'],{})
   calls+=f"| {arm} | {u['call']} | {u['phase']} ({u['status']}) | {u['seconds']:.3f} | {tokens.get('input_tokens','미확인')} | {tokens.get('output_tokens','미확인')} |\n"
 body=f'''# {cid}

## 1. 실행 메타

run-001, baseline(ADR0706 fused-entry), title-entry(ADR0707). 공개 질문 각1회, Qwen3.8 Parasail FP8, 현장 실행 아님.

## 2. 사용자 질문 원문

{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개

승인 gold 미사용, 법률 정확도 미채점. 제목 매칭/도구 선택/전체 실행의 기술 검증이다.

## 4. 제품 입력을 구성한 원값

[제목·검색·읽기 범위 원장](../artifacts/run-001/trace-review.json), [회수·탈락 단계 원장](../artifacts/run-001/retrieval-ledger.json.gz). 모든 실제 입력 원문은 아래 raw archive에 보존한다. 확보/모델 전달/채택을 구분하며 제목 후보는 인용 근거가 아니다.

## 5. 제품 모델 호출 — run·arm별 실제 원문

{calls}

[압축 원본](../artifacts/run-001/raw.tar.gz)의 `<arm>/{cid}/provider/call-*`에 system/user/schema/응답이 exact 원바이트로 있다. [해시·복원](../artifacts/run-001/raw-archive.json). 최종 응답/개별 사용량은 `../artifacts/run-001/<arm>/{cid}/result.json`에 보존한다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair

위 표는 모든 물리 호출을 포함한다. 제목 대조는 모델0회다. 거절/보정도 원본에 보존한다.

## 7. 채점 호출과 반복 판정

judge0회. 알려진 질문1회 관측이며 안정적인 성능·정확도 인증이 아니다.

## 8. 사례 최종 판정

{table}

[수동 검토와 제한](../artifacts/run-001/quality-review.json). MAIN 불변.
'''
 p=A/'실험'/q['file'];p.write_text(body);q['sha256']=sha(p)
m['results']['engineering_checks']=review['engineering_checks'];m['results']['error_taxonomy']=review['errors'];put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 제목 힌트와 검색 도구 선택의 전체 실행\n\n'+table+'\n[실험 기록](../README.md)\n')
p=R/'04_EXPERIMENTS/ADR/README.md';t=p.read_text()
if 'ADR-0707-grounded-law-title-entry/README.md' not in t:p.write_text(t.rstrip()+'\n- [ADR-0707 실제 법령 제목 힌트·도구 선택](ADR-0707-grounded-law-title-entry/README.md) — 격리 후보·공개3질문 두 방식 전체6회, MAIN 불변.\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0707','created_at':m['reservation']['created_at'],
 'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen candidate and E2E traces with failures','contains_raw_prompts_and_outputs':p.name=='raw.tar.gz'} for p in sorted((A/'artifacts').rglob('*')) if p.is_file() and p.name!='manifest.json']})
print(table)
