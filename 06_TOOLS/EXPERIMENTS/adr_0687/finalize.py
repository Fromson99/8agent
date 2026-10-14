"""Save a source-based review, separate from product outputs and approved gold."""
from pathlib import Path
import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0687-risk-cm-recorded-answer-source-review'
PARENT = ROOT / '04_EXPERIMENTS/ADR/ADR-0686-risk-cm-public-scope-local-probe'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


frozen = read(ADR / 'artifacts/design/frozen.json')
for path, expected in frozen['inputs'].items():
    assert sha(ROOT / path) == expected, path
source_index = read(ADR / 'artifacts/evidence/primary-source-index.json')
originals = read(ADR / 'artifacts/evidence/selected-generation-originals.json')['originals']
blocks = {e['id']: {int(b['block_id']): b['text'] for b in e['blocks']} for e in originals}
assert '다음 각 목의 어느 하나' in blocks['rp'][2714]
assert '종합금융투자사업자는' in blocks['special-provision'][820]
assert '적립대상' in blocks['pf-body'][551]
assert source_index['web'][0]['extracts'][2]['found']
prior = read(PARENT / 'artifacts/summary.json')['cases']
assert len(prior) == 3
finance_url = 'https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000285020&chrClsCd=010201'
pf_url = 'https://law.kofia.or.kr/service/law/lawFullScreenContent.do?historySeq=1682&seq=155'
filing_url = 'https://kind.krx.co.kr/external/2026/05/15/002321/20260515005203/11013.htm'
verdicts = [
    {'verdict': 'partial', 'label': '부분정답', 'all_asserted_claims_supported_in_cited_scope': True,
     'reason': '부족액을 대손준비금으로 적립한다는 설명과 인용된 특례 비율은 맞다. 그러나 금융투자회사 일반 질문에 종합금융투자사업자 특례만 답했고, 충당금과 준비금의 회계상 차이를 설명하지 않았다.',
     'findings': [
         {'type': 'scope_incomplete', 'material': True, 'coordinates': ['financial:제3-8조제1항', 'financial:제3-24조의4제3항'],
          'evidence_ids': ['general-provision', 'special-provision'],
          'detail': '제3-24조의4는 종합금융투자사업자의 특례이며 제3-8조 일반 기준과 요적립률이 다르다. 모델은 주체를 명시했으므로 특례 수치 자체를 허위라고 판정하지 않는다. 실제 회사가 특례 대상인지도 이번 입력에서 주어지지 않았다.'},
         {'type': 'essential_explanation_missing', 'material': True,
          'evidence_ids': ['general-provision', 'finance-company-filing'],
          'detail': '대손충당금은 회계기준에 따라 손실을 반영하는 충당금이다. 대손준비금은 감독상 요구액과 회계상 충당금의 부족 차이를 이익잉여금에 적립하는 항목이라는 차이가 빠졌다. 유화증권 2026년 1분기 공시는 준비금 설정이 순자산·손익을 바꾸지 않고 배당을 제한한다고 설명한다.'},
         {'type': 'rates_supported', 'material': False, 'evidence_ids': ['special-provision'],
          'detail': 'PF 정상 1년 이상3%·기타2%·요주의10%·고정30%·회수의문75%·추정손실100%, 비PF .85/7/20/50/100은 해당 특례 범위에서 원문과 일치한다. 일반 비PF .5/2/20/75/100과 혼용하면 안 된다.'}],
     'corrected_answer_candidate': '대손충당금은 한국채택국제회계기준에 따라 손실을 반영하여 설정하는 회계상 충당금이다. 대손준비금은 감독상 기준에 따른 요구액보다 회계상 대손충당금이 적을 때 그 부족 차이를 이익잉여금에 적립하는 항목이다. 일반 기준은 금융투자업규정 제3-8조, 종합금융투자사업자는 제3-24조의4제3항 특례를 구분해 적용한다. 분기 가결산 시 준비금 적립이 확정되지 않았으면 적립예정금액을 산정한다.',
     'primary_urls': [finance_url, filing_url],
     'version_status': '인용 특례와 일반조의 핵심 문언·비율을 선택 원문 및 2026-09-15 시행 공식 본문에서 확인했다. 회사별 특례 해당 여부는 미제공.'},
    {'verdict': 'partial', 'label': '부분정답 — 본문 원칙은 맞음', 'all_asserted_claims_supported_in_cited_scope': True,
     'reason': '사업성 평가→건전성 분류→적립대상 자산의 적정 충당금이라는 원칙은 맞다. 그러나 별표17-1의 등급별 연결과 예외를 확보하지 못해 개별 사업장 적용까지 끝낸 답변은 아니다.',
     'findings': [
         {'type': 'body_claims_supported', 'material': False, 'evidence_ids': ['pf-body'],
          'coordinates': ['risk:제6-15조제1항', 'risk:제6-15조제2항', 'risk:제6-15조제3항'],
          'detail': '본문의 세 명제는 선택 원문 및 협회 2025 연혁과 일치한다. 적립대상 자산이라는 조건과 부실우려 AND 3개월 이상 연체라는 조건을 보존했다. 경공매도 별표에 따르도록 답했으므로 예외를 폐지한 절대 명령으로 단정하지 않는다.'},
         {'type': 'attachment_application_incomplete', 'material': True,
          'coordinates': ['risk:별표17-1', 'risk:별표17-2'],
          'detail': '모델이 직접 미확인 gap을 남겼다. RAW에는 별표17-1·17-2 HWP와 변환 md가 있지만 선택된 리스크관리 문서의 source_unit에서 두 별표를 독립 annex 원문으로 확인하지 못했다. 전체 corpus에 없다는 판정이나 미수집 원인 확정은 하지 않는다.'},
         {'type': 'effective_version_limit', 'material': True,
          'detail': 'RAW의 2026-07-09 개정판과 공식 협회 연혁1800에는 2027-01-01 시행 부칙이 있다. 본문6-15는 2025 연혁과 일치하나 새로운 자기자본비율 예시를 현재 기준으로 쓰면 안 된다. 2025 별표의 공식 링크는 확인했지만 바이너리 본문을 이번에 재확보하지 못했으므로 현행 별표 전체 검증은 미완료다.'}],
     'corrected_answer_candidate': '사업성 등급 하락 자체만으로 모든 PF 익스포저에 같은 충당금이 자동 적용되는 것은 아니다. 분기별 사업성 평가 결과를 자산건전성 분류에 반영하고, 대손충당금 적립대상 자산에는 그 분류와 회계·감독 기준에 맞는 충당금을 적립해야 한다. 개별 등급의 분류·적립은 적용 시점의 별표17-1과 해당 자산·회사 유형의 금융투자업규정을 함께 확인해야 한다. 별표 전체의 현행 버전을 확인하기 전에는 구체적 등급별 비율을 확정하지 않는다.',
     'primary_urls': [pf_url],
     'version_status': '본문 원칙은 공식 이전 연혁과 선택 원문이 일치함을 확인. 현재 효력 별표 전체 재검증은 미완료; 2027 시행 개정판의 새 기준은 소급 사용하지 않음.'},
    {'verdict': 'incorrect', 'label': '오답 — 중요 조건 오류', 'all_asserted_claims_supported_in_cited_scope': False,
     'reason': '첫 문단은 대체 요건을 맞게 열거했으나, 뒤에서는 BBB 이상을 모든 일반 고객 RP에 필수라고 설명해 제5-18조제2항제2호의 선택 구조와 모순된다. 대상 증권 종류의 전체 열거도 빠졌다.',
     'findings': [
         {'type': 'alternative_condition_made_universal', 'material': True,
          'model_excerpt': '일반 경우: 신용평가업자로부터 투자적격(회사채 BBB이상) 판정을 받은 증권이어야 한다.',
          'evidence_ids': ['rp'], 'coordinates': ['financial:제5-18조제2항제1호', 'financial:제5-18조제2항제2호가목부터마목'],
          'detail': '공통조건은 시장성 및 일별 시가평가 가능성이다. 그에 더하여 가~마목 중 하나를 충족하면 된다. BBB 이상은 가목의 요건이므로 나목 적격금융기관 발행·보증 또는 다목 정부·지자체 보증 등 다른 경로에 일괄 덧붙일 수 없다. 모델 첫 문단과 둘째 문단도 서로 모순된다.'},
         {'type': 'requested_security_categories_missing', 'material': True,
          'evidence_ids': ['rp', 'rp-decree'],
          'coordinates': ['decree:제181조제1항제1호', 'financial:제5-18조제1항'],
          'detail': '시행령181조의 국채·지방채·특수채와 규정5-18①의 보증사채·모집/매출 무보증사채·공공기관/지방공사 채권·유동화 신탁 수익증권·주택저당/학자금대출증권 등의 종류를 제시하지 않았다. ②의 신용·발행·보증 조건만으로 대상 종류를 다 답했다고 볼 수 없다.'},
         {'type': 'proviso_scope_requires_preservation', 'material': True,
          'evidence_ids': ['rp'], 'coordinates': ['financial:제5-18조제2항제2호가목단서'],
          'detail': '자동투자 상위3개 등급과 복수 평가 중 낮은 등급은 원문에 존재한다. 다만 이를 가목의 단서 위치에서 떼어 다른 모든 대체 경로의 전역 조건으로 바꾸는 설명은 피해야 한다. 확정 오답의 주된 근거는 BBB 보편 요건 문장이다.'}],
     'corrected_answer_candidate': 'RP 대상은 시행령 제181조제1항제1호와 금융투자업규정 제5-18조제1항에 정한 증권 종류여야 한다. 대고객 RP는 시장성과 일별 시가평가 가능성이라는 공통조건에 더하여 제5-18조제2항제2호 가~마목 중 하나를 충족해야 한다. BBB 이상은 가목에 따른 투자적격 경로의 요건이며, 적격금융기관 발행·보증이나 정부·지자체 보증 등 다른 경로까지 모두 BBB 이상을 요구한다는 뜻은 아니다. 가목 단서의 자동투자에는 상위3개 등급 및 복수 평가 시 낮은 등급 기준을 그 문언 범위에서 확인한다.',
     'primary_urls': [finance_url],
     'version_status': '선택 원문 및 2026-09-15 시행 공식 본문에서 동일한 어느 하나 구조와 가목 단서를 확인했다. 이 오류는 별표의 시점 불확실성과 무관하게 성립.'},
]
rows = []
for case, previous, verdict in zip(frozen['cases'], prior, verdicts):
    assert case['case_id'] == previous['case_id']
    result_path = PARENT / 'artifacts' / previous['run_id'] / 'result.json'
    rows.append({**case, **verdict,
        'recorded_output': {'path': str(result_path.relative_to(ROOT)), 'sha256': sha(result_path),
                            'json_path': 'output.answer.text'},
        'prior_runtime_coverage': previous['answer_coverage'],
        'reviewer': 'Codex offline source review', 'new_model_calls': 0, 'gold_approved': False})
review = {'schema_version': 'recorded-answer-source-audit-result-v1',
    'reviewed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'run_id': 'run-001', 'arm_id': 'baseline', 'cases': rows,
    'summary': {'total': 3, 'correct': 0, 'partial': 2, 'incorrect': 1, 'unverified': 0,
                'fully_supported_asserted_claims_cases': 2, 'material_contradiction_cases': 1,
                'definition': 'Completeness-inclusive verdicts under the frozen source-review rubric. Partial does not mean false; this is not an approved-gold accuracy estimate.'},
    'limits': frozen['limits'], 'new_model_calls': 0,
    'immutable_inputs_verified': True, 'original_risk_cm_transmitted': False,
    'question_bank_gold_approved': False, 'main_unchanged': True,
    'evidence': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in sorted((ADR / 'artifacts/evidence').glob('*')) if p.is_file()]}
put(ADR / 'artifacts/run-001/review.json', review)
m = read(ADR / '실험/manifest.json')
m['runs'][0].update(status='complete', sha256=sha(ADR / 'artifacts/run-001/review.json'))
m['dataset'].update(legal_version_checked=True, reference_version_checked=True,
    version_check_limits='Official-current financial body checked. KOFIA future-effective published revision separated from 2025 matching body; current full-annex verification is not claimed.')
m['results'].update(status='complete', by_arm={'baseline': {'total_count': 3, 'correct_count': 0,
    'partial_count': 2, 'incorrect_count': 1, 'all_asserted_claims_supported_count': 2,
    'approved_gold_accuracy': None, 'method': 'One Codex source reviewer; frozen completeness-inclusive rubric, no external judge call.'}},
    comparisons=[], judge_disagreements=None,
    usage={'new_model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost_usd': 0},
    latency={'not_applicable': 'No new product inference or judge invocation'},
    error_taxonomy=[{'case_id': r['case_id'], 'type': f['type'], 'reason': f['detail']} for r in rows for f in r['findings'] if f['material']])

table = '| 주제 | 판정 | 이유 |\n|---|---|---|\n' + '\n'.join(f"| {r['topic_reference']} | {r['label']} | {r['reason']} |" for r in rows)
for number, row in enumerate(rows, 1):
    q = ADR / '실험' / f"질문-{number:03d}-{row['case_id']}.md"
    output = row['recorded_output']
    references = '\n'.join('- [' + u.split('?')[0].split('/')[-1] + '](' + u + ')' for u in row['primary_urls'])
    q.write_text('\n\n'.join([
        '# ' + row['case_id'], '## 1. 실행 메타', 'run-001 / baseline / ADR0686 완료 기록 오프라인 대조 / 모델 신규 호출0',
        '## 2. 사용자 질문 원문', row['question'], '공개 합성 입력의 주제 대응: ' + row['topic_reference'] + '. 원본 내부 질문으로 실행한 결과가 아니다.',
        '## 3. 기준답변 — 채점 전용, 제품 입력 비공개', row['corrected_answer_candidate'], '이 답변은 오프라인 검토 후보이며 golden 정답 승인이나 제품 입력 변경이 아니다.',
        '## 4. 제품 입력을 구성한 원값', '새 제품 입력 없음. 부모 frozen input/output SHA를 artifacts/design/frozen.json에 고정했다.',
        '### 회수·탈락 단계 원장 — run·arm별', '새 retrieval 없음. 부모 retrieval-ledger.json.gz와 exact provider request를 hash로 상속했다.',
        '## 5. 제품 모델 호출 — run·arm별 실제 원문', f"기존 제품은 Qwen3.8, 이번 추가 호출0. 답변 전체 정본: `{output['path']}` / `sha256:{output['sha256']}` / JSON `{output['json_path']}`. 본문·호출 payload는 중복 복사하지 않는다.",
        '## 6. 중간 LLM 호출 — router/compiler/verifier/repair', '새 중간 호출0. 기존 호출 및 provider 원문은 ADR0686에 불변 보존.',
        '## 7. 채점 호출과 반복 판정', '외부 judge0. Codex가 동일 사전 기준으로 원문·공식 출처를1회 대조. 독립 평가자 교정이나 통계 일반화 없음. ' + row['version_status'],
        '## 8. 사례 최종 판정', '**' + row['label'] + '** — ' + row['reason'],
        '\n\n'.join('### ' + f['type'] + '\n\n' + f['detail'] for f in row['findings']), references,
        '정확한 좌표·선택 원문·공식 출처와 판정은 artifacts/run-001/review.json 및 artifacts/evidence에 보존했다.']) + '\n')
    m['questions'][number-1]['sha256'] = sha(q)
put(ADR / '실험/manifest.json', m)
front = (ADR / 'README.md').read_text().split('---', 2)[1]
sections = [
    ('1. 결정 요약', '원문 검토 완료: 부분정답2, 중요 조건 오류가 있는 오답1. 세 답변의 완전 정답 승인은 보류한다. 판정과 수정 답변 후보를 제품·gold와 분리했으며 MAIN은 변경하지 않았다.'),
    ('2. 문제와 변경 전 구조', 'ADR0686은 답변 생성3/3을 관찰했고 법률 정답률은 채점하지 않았다. 사용자는 그 답변이 맞는지 확인을 요청했다. 현재 선택된 MAIN45의 기존 출력과 원문 세대를 다시 읽되 새 모델 호출은 하지 않았다.'),
    ('3. 가설과 사전 판정 기준', frozen['hypothesis'] + '\n\n' + frozen['success_criteria'] + '\n\n' + frozen['failure_criteria'] + '\n\ncorrect: 적용·명제·필수 내용 모두 충족. partial: 지원되는 내용은 있으나 필수 설명·범위·세부 확인 미완료. incorrect: 중요 조건·예외의 상실 또는 원문 모순. unverified: 판단할 원문·시점 자체 미확인. 기준은 결과 작성 전에 frozen.json으로 고정했다.'),
    ('4. 실험 설계', '단일 baseline은 완료 부모 ADR-0686-experiment-v1/baseline의 기록3건 전부다. 새 제품 후보·A/B·재추론·채점모델은 없다. 답변의 명제 사실성과 질문 완결성을 별도로 기록한다. 부모 ledger를 상속하며 평가 근거나 수정 답변을 제품 context에 넣지 않는다.'),
    ('5. 데이터·모델·재현성', '입력12파일 SHA를 호출 전 frozen.json에 고정하고 완료 직전 재검증했다. 선택 generation의 source_unit와 source_block5개 조문을 좌표·원천해시로 보존했다. 공식 2026-09-15 시행 금융투자업규정3-8·3-24조의4·5-18과 공개 발행사 공시를 대조했다. 협회6-15는 2025 공식 연혁과 본문 일치를 확인했다. 2026-07-09 공표 개정판은 2027-01-01 시행이라 현재 적용과 구분했다.'),
    ('6. 결과', table + '\n\n완전 정답0/3은 이번 완결성 기준의 관측값이고 승인 gold 정확도가 아니다. 기재 명제가 인용 범위 안에서 지원되는 사례는2/3, 중요 모순이 확인된 사례는1/3이다. 통계적 정답률이나 전체105문항 품질로 확대하지 않는다.'),
    ('7. 사례별 오류 분석', '\n\n'.join(r['topic_reference'] + ': ' + r['reason'] for r in rows) + '\n\nRP의 오류는 선택 원문 자체에 있는 대체 조건을 답변이 전역 BBB 요건으로 바꾼 것이다. 이에 반해 특례 수치와 PF 본문 원칙은 원문 지원 내용으로 보존한다.'),
    ('8. 비용·지연·회수 규모', '신규 제품·중간·judge 호출0, 신규 모델 토큰0·비용0. 새 retrieval 없음; 원문 재열람과 공식 출처 검토만 했다. 부모 전체 article-root26597과 provider exact 기록·retrieval ledger는 공유한다. 원시 공식 금융본문/공시는 무손실 gzip·SHA로 보존하며 세대 전체와 답변 본문은 반복 복사하지 않았다.'),
    ('9. 해석', 'COVERED였던 RP 답변에서 중요 오류가 확인됐다. 따라서 runtime의 COVERED 및 인용 존재만으로 완전 정답이 성립한다는 가설은 지지되지 않는다. 특례 선택 편중과 별표 미확보는 각각 적용 범위 및 근거 확보의 개선 대상으로 기록한다. 이번에는 실패 원인의 코드 변경을 실험하지 않았다.'),
    ('10. 한계와 일반화 가능 범위', '알려진 공개 합성3건·in_sample·단일 source reviewer다. 원본 risk_cm105문항의 정답 승인·외부 반출·holdout 성능을 뜻하지 않는다. RAW 별표가 존재하지만 2025 현행판 바이너리 재다운로드를 확보하지 못했으므로 현행 별표 전체의 세부 비율까지 검증했다고 주장하지 않는다. 본문에 인용된 원칙의 검증과 이 한계를 구분한다. 저장소 전체 graph는 기존8개 오류가 있어 통과하지 않는 상태이며 최종 receipt에 새 오류 여부를 남긴다.'),
    ('11. 운영 결정·롤백 조건', 'MAIN45·선택 데이터·제품 코드·질문은행 question_only·반출 설정·GENOS 상태는 불변이다. 원문·과거 모델 출력·과거 실험 판정은 덮어쓰지 않았다. 수정 답변은 이 ADR의 오프라인 후보일 뿐 golden이나 제품 wiki가 아니다. 후속 답변 개선·재실행은 새 ADR에서 기준을 동결한다.'),
    ('12. 재현 명령', 'WSL에서 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0687/finalize.py로 고정 기존 출력과 저장 evidence를 재대조한다. 완료 record를 덮어쓰기보다는 분리 복사에서 재현한다. 신규 source 수집은 최초 성공 exact payload와 실패 이력을 보존했다. stable runner의 adr_structure.py hash, validate --final, graph 결과를 artifacts에 남긴다.'),
]
(ADR / 'README.md').write_text('---' + front + '---\n\n# ADR-0687: risk_cm 기존 답변 원문 검증\n\n' + '\n\n'.join('## ' + title + '\n\n' + body for title, body in sections) + '\n')
(ADR / '실험/README.md').write_text('# 기록 답변 원문 검증\n\n' + table + '\n\n' + '\n'.join(f"- [{r['case_id']}](질문-{i:03d}-{r['case_id']}.md)" for i, r in enumerate(rows, 1)) + '\n\n새 모델 호출0. 수정 답변 후보는 평가 전용이며 승인 gold와 제품 입력에는 넣지 않았다.\n')
index = ROOT / '04_EXPERIMENTS/ADR/README.md'
link = '[ADR-0687 risk_cm 기존 답변 원문 검증](' + ADR.name + '/README.md)'
if link not in index.read_text():
    index.write_text(index.read_text() + '\n- ' + link + ' — 부분정답2·중요 조건 오류1, 신규 모델0회, MAIN 불변.\n')
files = [p for p in (ADR / 'artifacts').rglob('*') if p.is_file() and p != ADR / 'artifacts/manifest.json']
files += list((ROOT / '06_TOOLS/EXPERIMENTS/adr_0687').glob('*.py'))
put(ADR / 'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-0687',
    'files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in sorted(files)]})
print(json.dumps(review['summary'], ensure_ascii=False))
