"""Document the finished run; consumes existing records and makes no model calls."""
from pathlib import Path
import gzip, hashlib, json

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0717-main50-cm51-sequential-profile'
O = A / 'artifacts/run-001'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
m = read(A / '실험/manifest.json')
s = read(O / 'summary.json')
assert s['completed'] == 51
rows = read(O / 'result.json')['cases']
questions = {c['case_id']: c['question'] for c in read(A / 'artifacts/design/dataset.json')['cases']}
started = {parts[1]: parts[2] for line in (A / 'artifacts/worker.log').read_text().splitlines()
           if line.startswith('CASE_START ') for parts in [line.split()]}
index = '| 질문 | 최종 답변 제외 호출 | 최종 답변 제외 LLM 시간 | 전달 원문 | 응답 |\n|---|---:|---:|---:|---|\n'
trace_report = '# CM51 실제 이동과 물리 호출\n\n최종 답변·판단(memory-assess 및 복구)은 주 지표에서 분리한다. 아래 호출 표에는 이를 포함한 모든 호출을 남긴다. 화살표는 적용된 행동 순서이며 참조 선택 보조 기록은 별도다. 인용 검증과 과거 근거 전달률은 정답률이 아니다.\n'

for record, q in zip(rows, m['questions'], strict=True):
    cid = record['case_id']
    assert cid == q['case_id']
    prefix = '../artifacts/run-001/' + cid
    observer = read(A / 'artifacts/observations' / (cid + '.json'))
    if record['http_status'] != 200:
        public = read(O / cid / 'result.json')['output']
        (O / cid / 'answer.txt').write_text(public.get('message', '답변을 완료하지 못했습니다.')
            + '\n조회 번호: ' + str(public.get('request_id', cid)) + '\n')
    table = '| 호출 | 실제 단계 | 시간 | 입력/출력 토큰 | 상태 |\n|---:|---|---:|---:|---|\n'
    for c in observer['calls']:
        table += f"| {c['call']} | {c['phase']} | {c['seconds']:.3f}초 | {c['input_tokens']} / {c['output_tokens']} | {c['status']} |\n"
    steps = sorted(record['trace'], key=lambda x: x.get('number') or 0)
    chain = ' → '.join(x['action'] for x in steps if x['action'] != 'REFERENCE_CHOICES') or '적용 행동 없음'
    detail = '\n'.join(f"- {x['number']}. **{x['action']}** ({x['status']}): {x['reason']}" for x in steps)
    outcome = (f"마지막 답변 작성·수정만 제외(중간 재조사 판단은 포함) **{record['final_answer_excluded_calls']}회·{record['final_answer_excluded_seconds']:.3f}초**. "
               f"순수 탐색 **{record['investigation_calls']}회·{record['investigation_seconds']:.3f}초**, "
               f"답변·판단 {record['assessment_calls']}회·{record['assessment_seconds']:.3f}초, HTTP{record['http_status']}. "
               f"확보 {len(record['acquired_ids'])}·모델 전달 {len(record['presented_ids'])}·채택 {len(record['adopted_ids'])}개. "
               f"과거 전체 근거 {record['gold_presented']}/{record['gold_total']}, MAIN 역할 근거 {record['main_gold_presented']}/{record['main_gold_total']} 전달. "
               '정답 여부는 독립 채점하지 않았다.')
    with gzip.open(O / cid / 'ledger-case.json.gz', 'rt') as f:
        ledger = json.load(f)
    ledger_table = '| 단계 | 이전/추가/탈락/이후 | gold 이전/추가/탈락/이후 | recall |\n|---|---|---|---:|\n'
    for st in ledger['stages']:
        ledger_table += (f"| {st['stage_id']} | {st['before_count']}/{st['added_count']}/{st['discarded_count']}/{st['after_count']} | "
                         f"{st['gold_before']}/{st['gold_added']}/{st['gold_discarded']}/{st['gold_after']} | {st['golden_recall']} |\n")
    sections = [
        ('실행 메타', f'ADR0717/run-001/measured-main50, {cid}, 질문당 1회, 단일 순차 worker. 질문 작업 시작 {started[cid]}. Qwen3.8 / Parasail FP8. 원본 상태: 실제 provider bytes와 runtime 보존, 복원 hash 검증. 호출 단계·시간은 아래 표에 보존한다.'),
        ('사용자 질문 원문', questions[cid]),
        ('기준답변 — 채점 전용, 제품 입력 비공개', '[오프라인 참조](../artifacts/design/gold.json)에 고정했다. 제품 runner는 이 파일을 읽지 않는다. 과거 기준답변의 현행 법률 정확성은 미인증이다.'),
        ('제품 입력을 구성한 원값', '### 회수·탈락 단계 원장 — run·arm별\n\n' + ledger_table + f'\n[정확한 좌표·모든 탈락 이유]({prefix}/ledger-case.json.gz). 카탈로그는 메타데이터 후보 수이며 전체 본문을 읽었다는 뜻이 아니다. 원문·프롬프트·필터는 압축 원시 기록에서 정확히 복원할 수 있다.'),
        ('제품 모델 호출 — run·arm별 실제 원문', table + f'\n[원시 request/response/schema/runtime]({prefix}/raw.tar.gz), [각 파일 SHA-256·크기·복원법]({prefix}/raw-archive.json). exact provider bytes; 재구성 아님. 저장공간 최소화 지시에 따라 원문을 문서마다 반복 복사하지 않는다.'),
        ('중간 LLM 호출 — router/compiler/verifier/repair', chain + '\n\n' + detail + f"\n\n탐색/판단 복구 합계 {record['repair_calls']}회. [거절·검색·모델의 실제 선택](../artifacts/observations/{cid}.json)."),
        ('채점 호출과 반복 판정', '평가 모델 호출 0회. 반복 측정·독립 의미 채점 없음. 물리 호출 회계·권한·인용 원문 일치·실행 binding·승인 판단 해시는 모델 없는 검사로 확인했다.'),
        ('사례 최종 판정', outcome + f'\n\n[실제 답변]({prefix}/answer.txt) · [진단]({prefix}/diagnostic.json). 실패도 집계에 포함하고 재실행하지 않았다.'),
    ]
    path = A / '실험' / q['file']
    path.write_text(f'# {cid} · MAIN50 탐색 진단\n\n' + '\n\n'.join(f'## {i}. {title}\n\n{body}' for i, (title, body) in enumerate(sections, 1)) + '\n')
    q['sha256'] = sha(path)
    index += f"| [{cid}]({q['file']}) | {record['final_answer_excluded_calls']} | {record['final_answer_excluded_seconds']:.1f}초 | {len(record['presented_ids'])} | {record['http_status']} |\n"
    trace_report += f"\n## {cid}\n\n{questions[cid]}\n\n{outcome}\n\n{chain}\n\n{table}\n{detail}\n"

(A / '실험/manifest.json').write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n')
(A / '실험/README.md').write_text('# CM51 순차 실행\n\n최종 답변·판단 및 코드/캐시 시간을 제외한 실제 모델 호출 시간.\n\n' + index)
(O / 'traces.md').write_text(trace_report)
print('Documented all51 cases and physical-call traces; no model calls or product changes.')
