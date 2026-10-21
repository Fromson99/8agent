"""Seal the forced-graph inspection after both prospectively frozen requests."""
from pathlib import Path
import hashlib
import json
import shutil

R = Path(__file__).resolve().parents[3]
A = R / "04_EXPERIMENTS/ADR/ADR-0954-risk-photo-forced-graph"
O = A / "artifacts/run-001"
D = A / "artifacts/design"
load = lambda p: json.loads(p.read_text())
put = lambda p, v: p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
result = load(O / "result.json")
trace = load(O / "graph-trace.json")
review = load(O / "manual-review.json")
criteria = load(D / "criteria.json")
cases = load(D / "cases.json")
ledger = load(O / "retrieval-ledger.json")
totals = result["by_arm"]["linked"]
summary_rows = []
trace_rows = []
for c in cases:
    name = c["id"]
    v = result["cases"]["linked"][name]
    t = trace["cases"][name]
    summary_rows.append(f"| {name} | {v['status']} | {v['comparison_rows']} | {v['model_calls']} | {v['elapsed_seconds']:.2f}초 |")
    trace_rows.append(f"| {name} | {t['selected_links']} | {t['selected_endpoints']} | "
                      f"{sum(e['read_all_linked_spans'] for e in t['edges'])} | "
                      f"{sum(e['parent_received_all_linked_spans'] for e in t['edges'])} | "
                      f"{sum(e['literal_citation_count'] > 0 for e in t['edges'])} |")
findings = "\n".join(f"- {x}" for x in review["findings"])
checks = []
for c in cases:
    name = c["id"]
    a = load(O / "linked" / name / "citation-audit.json")
    checks += a["primary_quote_checks"]
front = (A / "README.md").read_text().split("---", 2)[1]
doc = f"""---{front}---

# 내규를 먼저 찾고 연결 외규를 회수하는 소범위 대사

## 1. 결정 요약
{review['conclusion']}
이번 사용자 요청으로 알려진 조문 위치를 그래프 입력으로 직접 넣었다. 자동 관계 발견 성능은 측정하지 않았다.
Proposed / in_sample / decision_eligible=false. 운영 MAIN·Oracle·GENOS 미변경.

## 2. 문제와 변경 전 구조
ADR0953/live는 내규를 읽은 뒤에도 외규 task의 basis_targets가 빈 상태였다.
유동성의 목표 조문 제3-24조의4 제2항을 놓치고 다른 적용 대상 제3-64조를 주요 근거로 선택했다.
이번에는 동일 제품 코드의 basis-link API·DB resolver·read_node 경로에 수동 연결만 제공했다.

## 3. 가설과 사전 판정 기준
가설: {criteria['hypothesis']}
첫 호출 전 동결: artifacts/design/criteria.json, forced-graph.json, freeze.json.
관계 조회·원문 회수·부모 전달·최종 인용을 각각 검사한다. 의미 판단과 처리시간은 별도 평가한다.
40물리호출/1800초/사례, RSS6GiB, 전체2사례 순차, adaptive replay 없음.
실패 분류와 담당·예산은 criteria.retry_contract. 불확실성을 이유로 새 차단 규칙을 추가하지 않았다.

## 4. 실험 설계
linked 단일 신규 arm, 두 질문 각1회. 부모는 완료 ADR0953-experiment-v1/live.
기준 답변은 부모의 보존 결과이며 이번에 다시 호출하지 않았다. 단회·시간차 관측이므로 인과적 개선율이나 통계적 우월성을 주장하지 않는다.
동일4문서·MAIN92 제품 코드·프롬프트·검색설정·Qwen3.8, 새 관계 입력만 추가했다.
동일 그래프4관계/8방향 연결을 두 사례 각각의 격리 DB에 넣고, 읽은 내규 span과 교차한 관계만 resolver가 선택한다.

## 5. 데이터·모델·재현성
사진 내규 부분 전사 + 금융투자업규정 + 시행세칙 + 별표10, term-source-696ba4030ea5f1a19ccf.
내규4개 조항 → 외규7개 원문 범위, 8개 방향 연결. 정확한 좌표는 forced-graph.json.
직접 명시 참조와 사용자가 지정한 시험 연결을 provenance로 구분했다. 법적 일치·충돌 결론은 넣지 않았다.
APPROVED는 시험 DB에서 기존 resolver를 작동시키기 위한 활성 상태이며 운영 승인/법률 정본이 아니다.
제품389파일 중 Python·프롬프트 변경0. 새 범위 승인 파일과 엔진 pin만 격리 재결속했다.
모델 Qwen3.8-27b / Parasail FP8 / reasoning none / fallback 없음. offline evaluator0회.

## 6. 결과

| 사례 | 결과 | 비교행 | 물리호출 | 지연 |
|---|---|---:|---:|---:|
{chr(10).join(summary_rows)}

| 사례 | 선택 관계 | 외규 범위 | 모두 읽음 | 부모에 모두 전달 | 직접 인용 범위 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(trace_rows)}

각 단계의 원문 span 기준 정확 집계: artifacts/run-001/graph-trace.json.

## 7. 사례별 오류 분석
{findings}
최초 기술 사전 검사는 원문 오류 코드가 service 공개 응답에도 그대로 있을 것으로 가정하여 assertion 실패했다.
실제 API는409/BASIS_SOURCE_HASH로 거부했고 service는 공개 표시 오류로 변환했다. 원래 frozen 검사와 실패 기록을 보존했다.
추가 기술 검사는 동일 제품 바이트의 raw API·공개 응답을 함께 확인했다. 제품 의미·예산·모델 입력 변경 없음.

## 8. 비용·지연·회수 규모
물리 {totals['model_calls']}호출, 입력 {totals['input_tokens']:,}, 출력 {totals['output_tokens']:,}, 공급자 보고 USD {totals['cost_usd']:.8f}.
원문 저장 {totals['stored_original_checks']}검사 / 불일치 {totals['source_mismatches']}.
현재 항목 직접인용 {len(checks)}검사 / 불일치 {sum(not q['literal_match'] for q in checks)}.
물리 전송·결과 불명·반복은 transport-audit.json, 자원은 resource-*.json.
원문 일치와 법률 의미 정답은 별도. 승인 answer gold가 없어 정확도·gold recall은 미측정.

### 단계별 회수·탈락 원장
retrieval-ledger.json에 사례별 acquired→returned→cited의 전체 before/added/discarded/after 및 탈락 사유를 보존했다.
canonical article-root 단위이며 seed 외규의 세부 항/호 span 흐름은 graph-trace.json이 추가 검증한다.
조문 좌표는 이번 요청에 따라 제품 그래프에 의도적으로 노출됐다. gold_visible_to_product=false는 승인 answer gold가 없음을 뜻한다.

## 9. 해석
{review['interpretation']}
후보 정본 자동 승인·내규 전체 조사·업권 적용 사실 확정은 이번 검증 범위가 아니다.

## 10. 한계와 일반화 가능 범위
알려진 두 사례, 수동 그래프, 부분 내규, 기준일 미지정. 회사의 법적 지위·최신 법령은 확정하지 않았다.
격리 앱을 주입한 실제 service.py ASGI 진입이며, 실행 중인 로컬 MAIN 또는 GENOS 현장 검증이 아니다.
기존 ADR 전역 graph9오류는 별도이며 이번 ADR 기록과 구분한다.

## 11. 운영 결정·롤백 조건
MAIN92 선택 포인터·운영 DB·GENOS·Git 미변경. 시험 DB와 원시 실패·성공 기록 보존.
{review['next_step']}
전체 문서 대사 분기나 자동 참조 구축은 후속 범위다.

## 12. 재현 명령
당시 실행 명령: artifacts/sequence.jsonl와 resource-*.json. 완료 run을 같은 예산으로 재실행하지 않는다.
후처리: `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0954/graph_audit.py`
검증: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path {A.relative_to(R)} --final`
원시 system/user/schema/response/usage는 raw, wire, canonical, calls.json에 있으며 artifacts/manifest.json의 hash로 결속한다.
"""
(A / "README.md").write_text(doc)
text = f"""내규–외규 직접 연결 그래프 대사 — ADR0954 / 2026-10-20

{review['conclusion']}

시험 방식
사진 내규4개 조항과 외규7개 원문 범위를8개 방향 연결로 구성했다.
기존 BASIS_LINKS_PROPOSE/REVIEW API로 격리 DB에 저장하고 기존 내규검색→DB관계조회→외규 read_node→대사를 실행했다.
두 질문에 같은 그래프를 넣었다. 질문 정답 문장은 넣지 않았다.
알려진 조문을 직접 연결한 시험이므로 자동 관계 발견의 정확도를 입증한 것은 아니다.

관측
{chr(10).join(summary_rows)}
{chr(10).join(trace_rows)}
위 단계 수치는 선택 관계 / 외규 범위 / 모두 읽음 / 부모에 모두 전달 / 직접 인용 범위 순서다.

판단
{findings}

{review['interpretation']}

검증
원문{totals['stored_original_checks']}검사 불일치{totals['source_mismatches']}.
직접인용{len(checks)}검사 불일치{sum(not q['literal_match'] for q in checks)}.
모델{totals['model_calls']}호출, 공급자 보고 USD {totals['cost_usd']:.8f}.
사전 API 검사에서 중복 등록·오래된 revision·원문 불일치 처리를 확인했다.
초기 검사 코드의 공개 오류 형식 기대 오류는 원본을 보존하고 raw API와 함께 재확인했다.

남은 범위
{review['next_step']}
부분 내규·기준일 미확인·두 인샘플 사례. 원문 일치가 법률 판단 인증은 아니다.
MAIN·운영 Oracle·GENOS 변경 없음. 전체 문서 대사는 실행하지 않았다.

상세 기록
{A.relative_to(R)}/README.md
{O.relative_to(R)}/graph-trace.json
{O.relative_to(R)}/manual-review.json
"""
(A / "RESULT.txt").write_text(text)
delivery = R / "09_ARTIFACTS/DELIVERIES/risk-rules-forced-graph-20261020"
delivery.mkdir(exist_ok=True)
(delivery / "직접연결_대사_점검결과.txt").write_text(text)
shutil.copyfile(D / "forced-graph.json", delivery / "시험용_내규외규_그래프.json")
m = load(A / "실험/manifest.json")
for case in cases:
    name = case["id"]
    v = result["cases"]["linked"][name]
    q = next(q for q in m["questions"] if q["case_id"] == name)
    path = A / "실험" / q["file"]
    stages = next(c["stages"] for c in ledger["runs"][0]["arms"][0]["cases"] if c["case_id"] == name)
    stage_text = "\n".join(f"| {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} |" for s in stages)
    path.write_text(f"""# {name} — forced graph

## 1. 실행 메타
ADR0954/run-001/linked, exact, 실제 시각 sequence.jsonl. Qwen3.8/Parasail FP8. 오프라인 모델0회.

## 2. 사용자 질문 원문
{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개
승인 answer gold 없음. 사용자 지정 source 좌표는 이번 시험의 제품 graph 입력으로 의도적으로 제공했다.
자동 관계 발견·독립 holdout 평가는 아니다. 역사적 기준은 ADR0953/live.

## 4. 제품 입력을 구성한 원값
forced-graph.json과 graph-seed-receipt.json, 실제 request/binding/health, journal.sqlite의 원문/span.
4문서와 같은 제품 코드. 원문 전체 목록은 audit.json, graph-trace.json, retrieval-ledger.json.

### 회수·탈락 단계 원장 — run·arm별
| 단계 | before | added | discarded | after |
|---|---:|---:|---:|---:|
{stage_text}

골드 없음, graph 입력은 제품에 공개. 탈락 원문과 사유는 ledger 전 목록으로 보존한다.

## 5. 제품 모델 호출 — run·arm별 실제 원문
../artifacts/run-001/linked/{name}/raw/call-*/request.json과 response.json.
system/user/schema/tool과 provider output을 생략 없이 원본 파일에 보존했다.
wire/*.json.gz, canonical/*.json.gz는 실제 payload 및 product view다. hash는 artifacts/manifest.json.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair
동일 디렉터리 calls.json/generations.json/result.json의 전체 phase/usage/지연.
물리 {v['model_calls']}호출, 입력{v['input_tokens']}, 출력{v['output_tokens']}.

## 7. 채점 호출과 반복 판정
채점 모델 호출0·반복0. 수동 원문 검토 및 결정적 문자/해시/DB추적만 수행했다.
manual-review.json은 제품 답변을 변경하지 않는다.

## 8. 사례 최종 판정
{v['status']}, 비교{v['comparison_rows']}행, source mismatch {v['source_mismatches']}.
{review['case_notes'][name]}
법률 정답률 미인증, MAIN·GENOS 미반영.
실제 답변: ../artifacts/run-001/linked/{name}/answer.txt
""")
    shutil.copyfile(O / "linked" / name / "answer.txt", delivery / ("실제답변_" + name + ".txt"))
    q["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
(A / "실험/README.md").write_text("# 직접 연결 그래프 두 질문\n\n" + "\n".join(f"- [{q['case_id']}]({q['file']})" for q in m["questions"]) + "\n")
m["results"]["error_taxonomy"] = review["error_taxonomy"]
put(A / "실험/manifest.json", m)
artifact = load(A / "artifacts/manifest.json")
artifact["files"] = []
files = [A / "RESULT.txt", *sorted((A / "artifacts").rglob("*")), *sorted(Path(__file__).parent.glob("*.py"))]
for p in files:
    if not p.is_file() or p == A / "artifacts/manifest.json" or p.name.startswith(("validation", "graph-final")):
        continue
    with p.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    artifact["files"].append({"path": str(p.relative_to(R)), "sha256": digest, "bytes": p.stat().st_size,
                              "description": "Frozen forced-graph input, exact live capture, or post-run read-only analysis.",
                              "contains_raw_prompts_and_outputs": any(s in p.parts for s in ("raw", "wire", "canonical"))})
put(A / "artifacts/manifest.json", artifact)
print(json.dumps({"artifact_files": len(artifact["files"]), "delivery": str(delivery)}, ensure_ascii=False))
