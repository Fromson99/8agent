"""Write the repository decision record without duplicating raw model text."""
from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0684-venture-option-tax-navigation-local-probe'
def read(p): return json.loads(p.read_text())
def put(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
s = read(ADR / 'artifacts/summary.json')
m = read(ADR / '실험/manifest.json')
f = read(ADR / 'artifacts/design/frozen.json')
lines = ['| 반복 | HTTP | 시간(초) | 모델 호출 | 세법 후보 선두 | 모델의 세법 READ | 답변 확인 범위 | 종료 사유 |',
         '|---|---:|---:|---:|---|---:|---|---|']
for r in s['runs']:
    lines.append(f"| {r['run_id']} | {r['http_status']} | {r['seconds']:.3f} | {r['model_calls']} | {r['first_law_order'][0] if r['first_law_order'] else '-'} | {r['tax_model_read_count']} | {r['answer_coverage']} | {r['stop_reason']} |")
table = '\n'.join(lines)
front = (ADR / 'README.md').read_text().split('---', 2)[1]
sections = {
    '1. 결정 요약': f"알려진 질문을 변경 없는 로컬 MAIN45에서 두 번 실행했다. 세법이 첫 후보인 반복은 {s['tax_candidate_first_count']}/2, 명시적인 모델 세법 READ가 있는 반복은 {s['tax_model_navigation_count']}/2다. HTTP 성공 {s['request_success_count']}/2와 부분 답변 {s['partial_answer_count']}/2를 구분한다. 신규 구현 채택·MAIN 승격은 없으며 Proposed로 기록한다.",
    '2. 문제와 변경 전 구조': '사용자는 GENOS가 주식매수선택권 질문에서 조세특례제한법으로 반복 진입한다고 보고했다. 사진에는 벤처기업법을 핵심 근거로 제안한 LAW_DECISION_REJECTED, source-law-navigation-2-repair와 SOURCE.INVESTIGATION.INCOMPLETE/HTTP422가 보인다. 전체 질문·이전 조사 상태·배포 코드/데이터 hash는 사진만으로 알 수 없다. 로컬은 service.service가 ACTIVE_RELEASE를 검증하고 선택된 frozen runtime을 불러오는 경로다.',
    '3. 가설과 사전 판정 기준': f"{f['hypothesis']}\n\n{f['criteria']}\n\nartifacts/design/frozen.json에 질문·기준·두 반복·코드/데이터/프로필/모델/설정 hash를 첫 호출 전에 동결했다. 후보 노출만으로 채택을 주장하지 않으며 HTTP200만으로 답변 완결을 주장하지 않는다.",
    '4. 실험 설계': 'baseline 단일 arm / run-001, run-002 / 동일 질문 / 매번 새로운 프로세스와 빈 runtime / 공유 원문과 불변 선택 릴리스 / 제품 코드·prompt·검색 정책 수정 0개. audit adapter는 기존 provider_request의 exact wire를 공통 ExperimentClient로 전달하고 입력·출력·usage를 남긴다. 제품 영향 구현 후보가 없으므로 후보 snapshot을 만들지 않는다. 부모는 완료된 ADR-0681-experiment-v1/session의 retests이며 별도 후보 효과 비교나 paired delta는 없다.',
    '5. 데이터·모델·재현성': f"공개 질문: {f['question']}\n\n현재 GENOS 질문 원문은 미확인이며 사진에서 읽은 의미와 기존 ADR0671의 공개 질문으로 재현했다. 공개 승인145문서, {f['release']['data_path']}, source generation term-source-3b667f54bb11d9477888, selected session-runtime-v6-20261007-r1/generation45. Qwen3.8 qwen/qwen3.8-27b / OpenRouter Parasail FP8 / reasoning effort none / fallback 없음. GENOS 내부 모델 실험이 아니다. 모든 호출에 모델/provider 검사를 수행했다. 원문 세대가 고정되어 있으며 최신 법령 효력이나 세부 법률 정답을 새로 인증하지 않았다.",
    '6. 결과': table + '\n\n정확한 최종 출처·답변·누락·입출력 hash·실행 binding은 artifacts/summary.json, 각 run의 diagnostic.json, navigation-trace.json, provider 원본과 질문 파일에 연결한다.',
    '7. 사례별 오류 분석': '첫 노출과 실제 원문 열람을 분리한다. 초기 deterministic recall은 세법 preview를 확보할 수 있지만 UNIT_READ_CHOICE는 모델이 선택한 법령이다. 실제 답변의 answer.claims.source_ids를 SELECT.final_ids와도 별도 기록한다. 부분 답변은 부족한 시행령 원문과 추가 조사 복귀 한도를 검토한다. 이 실험에는 legal gold나 정답 채점이 없으므로 의미 정답률을 제시하지 않는다. 사진의 GENOS 실패와 동일한 원인이라고 단정하지 않는다.',
    '8. 비용·지연·회수 규모': f"제품 호출 {sum(r['model_calls'] for r in s['runs'])}회, input {s['usage']['input_tokens']} / output {s['usage']['output_tokens']} tokens, USD {s['usage']['cost_usd']:.6f}. 요청 p50 {s['latency']['request_p50']:.3f}초 / 표본2개 p95 {s['latency']['request_p95']:.3f}초. evaluator0회. 승인 원문 article-root {m['retrieval_accounting']['corpus_total']}개. exact catalogue→초기recall→원문확보→모델입력 집합은 retrieval-ledger.json.gz에 보존했다. 단계 전체의 집합이므로 이후 확장에 의한 added도 그대로 기록한다. gold가 없어 golden recall은 미측정이다. 원문·캐시는 공유하고 보고서에는 전체 본문을 반복 복제하지 않는다.",
    '9. 해석': '선택 릴리스의 unit_fulltext.py law_groups_page는 개별 단위 FTS rank를 materialize한 뒤 법령별 MIN(match_score)로 정렬한다. 이 순서는 검색어와 잘 맞는 본문 기준이며 행사 요건의 법적 우선순위 판정이 아니다. 세법도 벤처기업·주식매수선택권·행사를 포함하므로 후보 선두에 노출될 수 있다. 후속 모델의 법령 선택과 완결성은 별도 문제다. 실측 후보 순서는 trace에 있고 원인을 다른 model로 바꿔 검증한 실험은 아니다.',
    '10. 한계와 일반화 가능 범위': '알려진 공개 질문 단일 사례의 두 번 반복이다. 현장 배포 hash·내부 모델2605의 정확한 model ID·현장 source generation·기존 세션/shortcut 상태·정확한 사용자 질문은 미확인이다. 로컬과 GENOS 차이를 모델 하나로 귀속하지 않는다. 두 run의 차이를 정확도 또는 일반화 통계로 해석하지 않는다.',
    '11. 운영 결정·롤백 조건': 'MAIN 포인터·작업 제품 코드·선택 릴리스·원문 세대·GENOS 배포를 변경하지 않았다. 새 runtime만 격리 경로에 생성했다. 조회 순서나 부족 근거 복귀 정책을 개선하려면 이 기록을 부모/관련 ADR로 삼고 새 기준을 호출 전에 동결한다. 기존 실패와 원시 기록은 보존한다. 현재 작업의 제품 롤백은 필요하지 않다.',
    '12. 재현 명령': 'WSL /home/jin/8-AGENT에서 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0684/run_probe.py run-001 또는 run-002가 사전 동결된 요청을 실행했다. 기존 run 폴더를 덮어쓰지 않으므로 추가 재실행은 새 ADR에서 수행한다. 본 기록 확인은 summarize.py와 stable runner adr_structure.py validate --final 및 graph를 사용한다.'}
(ADR / 'README.md').write_text('---' + front + '---\n\n# ADR-0684: 벤처기업 주식매수선택권 행사 질문의 로컬 MAIN 법령 선택 재현\n\n' + '\n\n'.join('## ' + k + '\n\n' + v for k, v in sections.items()) + '\n')
(ADR / '실험/README.md').write_text('# 질문·반복 인덱스\n\n[venture-option-exercise](질문-001-venture-option-exercise.md) — 사진에서 읽은 의미의 공개 질문을 현재 MAIN45에서 새 상태로 두 번 실행했다.\n\n' + table + '\n\n정답률·paired delta·judge 불일치 비교는 수행하지 않았다. 모든 exact 입출력은 질문 파일에서 provider 원본 경로·hash로 연결한다.\n')
index = ROOT / '04_EXPERIMENTS/ADR/README.md'
link = '[ADR-0684 로컬 MAIN의 벤처 주식매수선택권 법령 선택](ADR-0684-venture-option-tax-navigation-local-probe/README.md)'
if link not in index.read_text():
    index.write_text(index.read_text() + '\n- ' + link + ' — 변경 없는 MAIN45·공개 질문2회; 검색 후보와 모델 READ/답변완결 분리, MAIN 불변.\n')
files = [p for p in (ADR / 'artifacts').rglob('*') if p.is_file() and p != ADR / 'artifacts/manifest.json']
files += list((ROOT / '06_TOOLS/EXPERIMENTS/adr_0684').glob('*.py'))
put(ADR / 'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-0684',
    'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in sorted(files)]})
print('Wrote source-navigation diagnostic record and artifact inventory.')
