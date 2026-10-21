"""Write the completed inspection record from immutable live captures."""
from pathlib import Path
import hashlib
import json
import shutil

R = Path(__file__).resolve().parents[3]
A = R / "04_EXPERIMENTS/ADR/ADR-0953-risk-photo-authorized-live"
O = A / "artifacts/run-001"
load = lambda p: json.loads(p.read_text())
put = lambda p, v: p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
results = load(O / "result.json")
cases = load(A / "artifacts/design/cases.json")
discovery = load(O / "discovery-audit.json")
ledger = load(O / "retrieval-ledger.json")
aggregate = results["by_arm"]["live"]
details = results["cases"]["live"]
review = {
    "kind": "offline_record_review", "model_calls": 0, "legal_accuracy_certified": False,
    "liquidity": {
        "target_discovery": "내규 제6-4조 제1·2항 및 외규 시행세칙 별표10 확보·인용. 사용자 확인 대상 금융투자업규정 제3-24조의4 제2항은 데이터에 존재하지만 회수·인용 0.",
        "scope_issue": "제3-64조의 합병투자매매업자·투자중개업자 기준을 주요 의무 비교에 사용. 실제 회사의 해당 여부를 확정하지 않았음.",
        "semantic_issue": "condition을 MATCH로 표기하면서 별표10과 종금자산부채현황표를 서로 같은 조건처럼 설명. 원문 인용 일치가 이 해석의 정당성을 보장하지 않음.",
    },
    "leverage": {
        "target_discovery": "내규 제2-1조 제1항 제3호·제1-4조 제1항 제3호, 외규 제3-6조 레버리지 정의·제3-24조의4·제3-26조 제7항 모두 읽고 인용.",
        "semantic_issue": "내규 1,000% 관리기준과 외규 900% 초과 보고조건을 DIFFERENT로 설명. 관리상한과 보고의무의 차이가 곧 모순이라는 결론은 아님. 산정기간은 양측 미확인인데 DIFFERENT로 표시해 상태와 설명의 정합성 보완 필요.",
        "scope_issue": "내규가 부분 전사이므로 예외·계산 세부사항을 못 찾았다는 관측은 내규 전체에 없다는 증명이 아님.",
    },
    "mapping": {
        "initial_approved_targets": 0,
        "new_proposals": 4, "statuses": ["PROPOSED"], "kinds": ["RELATED"],
        "persisted_in": "두 사례의 격리 runtime/basis-links/authority.sqlite",
        "direct_explicit_relationship_verified": False,
        "discovery_gap": "두 외규 첫 조사 입력 모두 basis_snapshot.items=[] 및 basis_targets=[]. 내규에서 읽은 명시 인용이 외규 task의 구체적 참조 대상으로 전달되지 않음. 레버리지의 목표 조문 회수 성공과 내규 출발 연결 성공은 별도.",
        "production_oracle_written": False,
    },
    "workflow": {
        "question_workflow": "실제 두 요청 모두 HTTP200 / partial, 비교행 2·1개",
        "document_comparison": "문서 대사: 전용 비교 분기는 미연결. ADR0951의 use_llm=false 진입 관찰에서 일반 RAG로 분기. 실모델 문서 전체 대사는 이번 범위에 포함하지 않음.",
        "whole_document_basis_discovery": "기존 근거관계 탐색 경로와 문서 전체 모순 비교는 구분해야 함.",
    },
    "next_changes_not_implemented": [
        "내규에서 실제 읽은 명시 참조의 원문 위치·해시·대상 문서와 조문을 DB 관계로 연결하고 외규 조사 입력에 전달.",
        "명시 참조·내용상 후보·적용성 판단·사람 검토 상태를 별도 보존. 새 RELATED 후보를 승인 정본으로 자동 승격하지 않음.",
        "문서 대사:를 별도 분기로 연결하고 전체 구조 목록의 항목별 대응·미대응·미확보 및 양방향 누락을 추적.",
        "동일 용어의 다른 업권 조문 혼입과 상태/설명 불일치를 후속 동결 실험에서 검증.",
    ],
}
put(O / "manual-review.json", review)

summary = f"""사진 내규를 사용한 실제 대사 점검 — 2026-10-20 / ADR0953

결과
사진 기반 위험관리기준시행세칙 부분 전사 문서로 유동성·레버리지 질문을 실제 실행했다.
유동성: partial, 비교 2행, 20호출, {details['liquidity']['elapsed_seconds']:.2f}초.
내규 제6-4조와 시행세칙 별표10은 찾았지만, 확인 대상인 금융투자업규정 제3-24조의4 제2항은 놓쳤다.
주요 의무 비교에 합병투자매매업자·투자중개업자 대상 제3-64조를 사용했다. 적용 대상 판단을 보완해야 한다.
레버리지: partial, 비교 1행, 13호출, {details['leverage']['elapsed_seconds']:.2f}초.
내규 제2-1조 제1항 제3호와 외규 제3-6조·제3-24조의4·제3-26조 제7항을 모두 찾아 인용했다.
다만 관리상한과 보고조건을 구분해 설명해야 하며, 양측 미확인을 DIFFERENT로 표시하는 판단 정합성 문제가 남았다.

내규에서 외규로 실제 연결되는가
두 외규 조사 입력 모두 승인 관계 snapshot과 basis_targets가 비어 있었다.
내규에서 읽은 명시 참조가 외규 조사의 구체적 대상으로 전달되지 않았다.
따라서 레버리지 조문을 찾은 결과만으로 '내규 기반 참조 탐색 성공'으로 판정할 수 없다.
대사 후 관계 후보 4건은 격리 DB에 저장됐다. 모두 RELATED / PROPOSED이며 승인된 명시 근거관계는 아니다.
기존 DB 후보 저장 기능은 동작한다. 명시 참조 자동 연결과 재사용은 이 문서에서 아직 충족되지 않았다.

문서 전체 대사
'문서 대사:' 전용 분기는 아직 연결되지 않았다.
기존 문서 근거관계 탐색과 문서 전체 충돌 비교는 다르다.
사진이 원본 일부이므로 현 자료만으로 원본 전체의 모순·누락을 판정할 수 없다.
이번에는 일반 대사 2개만 실제 모델로 실행했다.

검증과 비용
실제 Qwen3.8 / Parasail FP8, reasoning none. 33호출, 전송 실패·결과 불명 0.
입력 {aggregate['input_tokens']:,}토큰 / 출력 {aggregate['output_tokens']:,}토큰 / 공급자 보고 ${aggregate['cost_usd']:.8f}.
저장 근거 123건의 원문·해시 검사 불일치 0, 항목 직접인용 61건의 문자 불일치 0.
두 사례 모두 저장 결과·중복 요청 응답 동일, 소비자 확인 추가 모델 호출 0.
원문/인용 일치는 법률 판단 정확도 인증과 다르다.

실행 범위와 상태
MAIN92와 같은 제품 코드·프롬프트·검색 정책을 격리 앱에 주입했다. 새 문서 승인 구성 및 그 해시만 재결속했다.
실제 로컬 service.py의 ASGI 진입 경로를 사용했지만, 실행 중인 로컬 MAIN 서비스나 GENOS 현장 검증은 아니다.
문서 4개 범위: 사진 내규 부분 전사 + 금융투자업규정 전문 + 시행세칙 전문 + 별표10.
기준일 미지정·내규 개정일 미확인. 전체 MAIN corpus 검색이나 법령 최신성 검증이 아니다.
MAIN 선택 포인터·운영 Oracle·GENOS·Git 배포는 변경하지 않았다.
ADR0952의 승인 파일 해시 불일치 실패는 모델 0회 기록으로 보존하고, ADR0953에서 사전 검사 후 실행했다.

후속 구현 우선순위
1. 내규 명시 참조를 원문 span·버전·권한과 함께 DB에 연결하고 외규 조사 대상으로 전달.
2. 의미상 후보 관계와 적용성·검토 상태를 분리해 저장하고 재사용.
3. '문서 대사:' 분기에서 양쪽 문서 구조 전체의 대응·누락·미확보를 추적.

상세 기록
{A.relative_to(R)}/README.md
{O.relative_to(R)}/discovery-audit.json
{O.relative_to(R)}/manual-review.json
{O.relative_to(R)}/live/liquidity/answer.txt
{O.relative_to(R)}/live/leverage/answer.txt
"""
(A / "RESULT.txt").write_text(summary)
delivery = R / "09_ARTIFACTS/DELIVERIES/risk-rules-photo-20261020-r2"
(delivery / "실제_대사_점검결과.txt").write_text(summary)
for case in cases:
    name = case["id"]
    shutil.copyfile(O / "live" / name / "answer.txt", delivery / ("실제답변_" + name + ".txt"))
    actual = details[name]
    rows = next(c["stages"] for c in ledger["runs"][0]["arms"][0]["cases"] if c["case_id"] == name)
    table = "\n".join(f"| {s['stage_id']} | {s['before_count']} | {s['added_count']} | {s['discarded_count']} | {s['after_count']} |" for s in rows)
    record = f"""# 질문 — {name}

## 1. 실행 메타
ADR0953 / run-001 / live / exact. 실제 실행시각은 artifacts/sequence.jsonl.
Qwen3.8-27b / Parasail FP8 / reasoning none. 오프라인 평가 모델 호출 없음.
격리된 실제 service.py ASGI 앱, 활성 MAIN·GENOS 미변경.

## 2. 사용자 질문 원문
{case['question']}

## 3. 기준답변 — 채점 전용, 제품 입력 비공개
승인된 법률 정답 없음. 사용자 제시 조문은 reference-hints-evaluation-only.json으로 별도 동결.
질문 입력에 조문 정답을 추가하지 않았다. 정확도·gold recall은 미측정.

## 4. 제품 입력을 구성한 원값
정확한 request·binding·health: ../artifacts/run-001/live/{name}/.
원문 회수·전달·최종 인용의 전 목록과 탈락 사유: ../artifacts/run-001/retrieval-ledger.json.
원문·span·해시: 해당 사례 audit.json 및 runtime의 journal.sqlite.
문서 4개 고정, 내부 원본 부분 전사. 전체 MAIN corpus가 아님.

### 회수·탈락 단계 원장 — run·arm별

| 단계 | before | added | discarded | after |
|---|---:|---:|---:|---:|
{table}

계수 단위는 case_id + canonical article-root coordinate. 횟수 중복과 조문 고유값을 구분한다.
gold_total=0은 승인 gold가 없다는 뜻이며 정답이 0개라는 뜻이 아니다.

## 5. 제품 모델 호출 — run·arm별 실제 원문
../artifacts/run-001/live/{name}/raw/call-*/request.json: 실제 system/user/schema.
같은 디렉터리 response.json: 공급자 원응답. wire/*.json.gz, canonical/*.json.gz: 전송/제품 view와 구조 출력.
calls.json, generations.json, result.json: 호출별 실제 usage·지연·성공 상태.
전체 원문은 중복 복사하지 않고 원본 경로와 artifacts/manifest.json 해시로 보존한다.

## 6. 중간 LLM 호출 — router/compiler/verifier/repair
동일 calls.json의 phase별 전 호출 포함. intake·navigation·items·compare 및 재검토를 누락하지 않았다.
물리 호출 {actual['model_calls']}회, 입력 {actual['input_tokens']}, 출력 {actual['output_tokens']}.

## 7. 채점 호출과 반복 판정
오프라인 모델 0회, 반복/다수결 없음. 저장된 원문·인용·입력·DB 기록을 후처리로 검사했다.
post-run manual-review.json은 제품 context나 답변을 변경하지 않는다.

## 8. 사례 최종 판정
HTTP200 / {actual['status']}. 비교 {actual['comparison_rows']}행. 법률 정답 인증 없음.
{review[name]['target_discovery']}
{review[name]['semantic_issue']}
{review[name]['scope_issue']}
전송 오류 0, 원문 불일치 {actual['source_mismatches']}건. MAIN 승격 대상 아님.
최종 원문 답변: ../artifacts/run-001/live/{name}/answer.txt
"""
    q = next(q for q in load(A / "실험/manifest.json")["questions"] if q["case_id"] == name)
    (A / "실험" / q["file"]).write_text(record)

front = (A / "README.md").read_text().split("---", 2)[1]
rows = "\n".join(f"| {n} | {v['status']} | {v['comparison_rows']} | {v['model_calls']} | {v['input_tokens']:,} | {v['elapsed_seconds']:.2f}초 |"
                 for n, v in details.items())
doc = f"""---{front}---

# 사진 내규 실제 대사 점검

## 1. 결정 요약
실제 두 질문의 실행·회수·인용·DB 저장 관측을 완료했다. 두 답변은 partial.
레버리지의 지정 조문은 회수했지만, 유동성의 제3-24조의4 제2항은 놓쳤다.
내규 명시 참조의 외규 task 전달은 두 사례 모두 비어 있었으며, 관계 후보 4건만 PROPOSED로 저장됐다.
Proposed / decision_eligible=false / MAIN unchanged. 결과를 성공한 법률 정답으로 승인하지 않는다.

## 2. 문제와 변경 전 구조
사진 기반 새 내규로 기존 일반 대사 및 내규 출발 외규 탐색을 점검한다.
ADR0952는 새 승인 파일의 엔진 pin이 어긋나 모델 0회로 차단됐다.
이번 후보는 승인 파일과 엔진/파이프라인 해시를 재결속했고 StageRunner 사전 검사를 통과했다.

## 3. 가설과 사전 판정 기준
실행 전 동결: artifacts/design/criteria.json, freeze.json.
MAIN92가 내규 정의·명시 참조에서 외규를 찾아 설명 가능한 결과를 내는지 관측한다.
원문/권한/해시/상태/예산 보존과 실제 소스 추적을 필수로 삼고, 라우트 성공을 품질 성공으로 취급하지 않는다.
40물리호출/1800초/사례, RSS6GiB, 순차 실행. 후속 자동 재실행 없음.

## 4. 실험 설계
live 단일 arm, liquidity → leverage 각1회. 사전 승인한 원래 질문에 목표 조문을 주입하지 않았다.
완료 부모 ADR0952-experiment-v1/live, 데이터 준비 ADR0951.
제품 Python·프롬프트·검색 코드는 선택 MAIN92 그대로; 승인 및 pin 메타데이터만 격리 변경.
준비 실패 원본과 후속 성공 관측을 같은 run으로 합치지 않았다.

## 5. 데이터·모델·재현성
4문서/25,448 unit/29,993 nonempty block, term-source-696ba4030ea5f1a19ccf.
사진 내규는 실자료 부분 전사, 합성 완전 문서가 아니다. 개정/시행일 미확인.
Qwen3.8-27b / OpenRouter Parasail FP8 / reasoning none, fallback 없음.
고정 source 및389파일 code binding은 artifacts/design/*.json. 소비자 확인도 동일 앱·pin.

## 6. 결과

| 사례 | 결과 | 비교행 | 물리호출 | 입력토큰 | 지연 |
|---|---|---:|---:|---:|---:|
{rows}

33응답 수신, 429·전송 실패·결과 불명0. 법률 정확도·A/B 효과는 측정하지 않았다.

## 7. 사례별 오류 분석
유동성: 제3-24조의4 제2항 retrieval_miss, 합병 업권의 제3-64조 적용성 미확정, 다른 산정조건을 MATCH로 설명.
레버리지: 목표 세 조문 회수·인용. 양측 기간 미확인을 DIFFERENT로 표시하는 정합성 문제, 예외 미확보 유지.
두 사례: 승인 연결 0건, 명시 참조 대상의 외규 task 전달 없음. 후보 저장은 RELATED/PROPOSED 4건.
상세: artifacts/run-001/manual-review.json 및 discovery-audit.json.

## 8. 비용·지연·회수 규모
입력 {aggregate['input_tokens']:,}, 출력 {aggregate['output_tokens']:,}, USD {aggregate['cost_usd']:.8f}.
최대 프로세스 그룹 RSS 약0.94GiB, 중단 조건 미발생.
저장 원문123검사 불일치0(중복 저장 건 포함), 항목 직접인용61검사 불일치0.
회수·전달·최종 인용 고유 좌표: 유동성10→10→6, 레버리지8→8→6.
전체 corpus와 selectivity 등은 manifest. gold 미승인으로 recall 미측정.

### 단계별 회수·탈락 원장
artifacts/run-001/retrieval-ledger.json에 각 사례 acquired/returned/cited의 before/added/discarded/after 전체.
탈락은 최종 인용 집합에 없다는 관측이며 법적 무관성의 증명이 아니다.

## 9. 해석
일반 대사의 자료 회수·비교·저장 경로는 동작한다. 내규 출발 DB 관계 재사용은 이 새 문서에서 검증되지 않았다.
실제 외규 task에는 basis_snapshot.items=[], basis_targets=[]만 전달됐다.
부모는 이미 읽은 내규 명시 인용을 외규의 구체적 참조 대상으로 넘기지 않았다.
이는 task 영수증 및 semantic_runtime/basis_links/integration.py:parent_task와 일치한다.
DB 후보 생성은 finish_workflow에서 관측됐으며, 명시 인용을 모두 확정 관계로 전환한 것은 아니다.

## 10. 한계와 일반화 가능 범위
두 인샘플 사례, 작은 문서 범위, 부분 내규, 기준일 미지정. 전체 MAIN 검색과 최신 법령 검증 아님.
앱 주입 실제 service.py ASGI 검증이며 상주 로컬 서비스/GENOS 내부 모델 검증 아님.
문서 대사: 전용 분기 미연결은 ADR0951의 읽기 전용 진입 점검 결과. 이번 실제 모델 제3사례 없음.
전역 ADR graph에는 기존9오류가 있어 전체 저장소 graph 통과로 보고하지 않는다.

## 11. 운영 결정·롤백 조건
MAIN92 포인터·운영 권한 파일·운영 Oracle·GENOS·Git 미변경. 신규 후보를 정본으로 승인하지 않았다.
후속은 명시 참조 DB→외규 task 전달, 문서 전체 대사 분기, 업권 적용성 및 상태/설명 정합성 검증.
미검증 결과를 운영 자동 승인에 사용하지 않는다.

## 12. 재현 명령
실행 당시 명령: artifacts/resource-*.json 및 sequence.jsonl. 이미 완료한 live.py를 같은 run에 다시 실행하지 않는다.
후처리: `.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0953/discovery_audit.py`
검증: `.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path {A.relative_to(R)} --final`
정확한 prompt/output는 raw·wire·canonical 원본과 artifacts/manifest.json hash로 보존했다.
"""
(A / "README.md").write_text(doc)
(A / "실험/README.md").write_text("# 실제 두 질문 대사\n\n" + "\n".join(f"- [{c['id']}](질문-{i:03d}-{c['id']}.md)" for i, c in enumerate(cases, 1)) + "\n")
m = load(A / "실험/manifest.json")
m["results"]["error_taxonomy"] = ["retrieval_miss", "scope_actor_mismatch", "condition_exception", "other"]
put(A / "실험/manifest.json", m)
artifact = load(A / "artifacts/manifest.json")
artifact["files"] = []
files = [A / "RESULT.txt", *sorted((A / "artifacts").rglob("*")), *sorted(Path(__file__).parent.glob("*.py"))]
for p in files:
    if not p.is_file() or p == A / "artifacts/manifest.json" or p.name.startswith("validation") or p.name.startswith("graph"):
        continue
    with p.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    artifact["files"].append({"path": str(p.relative_to(R)), "sha256": digest, "bytes": p.stat().st_size,
                              "description": "Frozen inputs or exact live captures; post-run diagnostic files are read-only analyses.",
                              "contains_raw_prompts_and_outputs": any(s in p.parts for s in ("raw", "wire", "canonical"))})
put(A / "artifacts/manifest.json", artifact)
print(json.dumps({"files": len(artifact["files"]), "model_calls": aggregate["model_calls"], "delivery": str(delivery)}, ensure_ascii=False))
