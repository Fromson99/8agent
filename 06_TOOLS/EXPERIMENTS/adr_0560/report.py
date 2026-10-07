from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0559'))
import report as parent_report
parent_report.ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0560-node-action-experience-wire-repair'
parent_report.RUN = parent_report.ADR/'artifacts/run-001'
parent_report.main()

# The parent report helper is immutable; child metadata describes its own wire
# repair and contract suite without changing the completed parent's record.
import json
import statistics
manifest_path = parent_report.ADR/'실험/manifest.json'
manifest = parent_report.read(manifest_path)
run_result = parent_report.read(parent_report.RUN/'result.json')
for arm in ['baseline', 'experience']:
    calls = [u for u in run_result['usage'] if '-'+arm+'-' in u['phase']]
    values = [r['seconds'] for r in run_result['results'] if r['arm']==arm and r.get('mode')=='live-gemma']
    manifest['results']['usage'].setdefault('by_arm', {})[arm] = {
        'physical_calls': len(calls), 'input_tokens': sum(u.get('input_tokens') or 0 for u in calls),
        'output_tokens': sum(u.get('output_tokens') or 0 for u in calls),
        'cost_usd': sum(u.get('cost_usd') or 0 for u in calls), 'live_questions': 6}
    manifest['results']['latency'].setdefault('by_arm', {})[arm] = {
        'case_seconds_mean': statistics.mean(values) if values else None,
        'case_seconds_p50': statistics.median(values) if values else None,
        'case_seconds_p95': sorted(values)[round((len(values)-1)*.95)] if values else None,
        'live_question_denominator': len(values)}
parent_report.write(manifest_path, manifest)
readme = parent_report.ADR/'README.md'
text = readme.read_text().replace('계약 검사15개 통과', '계약 검사16개 통과')
text = text.replace('06_TOOLS/EXPERIMENTS/adr_0559/test_contracts.py',
    '06_TOOLS/EXPERIMENTS/adr_0560/test_contracts.py')
text = text.replace('adr_candidate.py validate --candidate 02_BACKEND/lawrag/research/candidates/adr_0559/experience',
    'adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0560/experience')
text = text.replace('## 4. 실험 설계\n', '''## 4. 실험 설계

완료 부모 ADR-0559/experience의 byte 동일 기억 코드를 재사용했다. 부모는 양쪽 arm의
JSON whitespace/length 실패로 조기 종료했으며 그 결과를 덮어쓰지 않았다. 이번 분기는
두 arm 모두 schema-in-prompt=true, answer 필드 마지막, max_output_tokens=1024,
repair=0을 적용했다. 기억 안내만 paired arm 차이다. 제품 호출의 실제 system/user와
native journal request의 일치도 별도 계약 검사로 검증했다.
''')
text = text.replace('## 8. 비용·지연·회수 규모\n', '## 8. 비용·지연·회수 규모\n\n'
    + parent_report.block({'usage_by_arm': manifest['results']['usage']['by_arm'],
        'latency_by_arm': manifest['results']['latency']['by_arm']})
    + '\n안내 개념이 입력 문맥을 추가하므로 읽은 원문 감소가 토큰·비용·지연 감소를 의미하지 않는다. '
      '6개 모의 질문 1회씩의 지연이며 안정된 속도 개선으로 해석하지 않는다.\n')
readme.write_text(text)
artifact = parent_report.ADR/'artifacts/manifest.json'
value = json.loads(artifact.read_text())
for path in [Path(__file__), Path(__file__).with_name('test_contracts.py')]:
    value['files'].append({'path': str(path.relative_to(ROOT)), 'sha256': parent_report.sha(path),
        'bytes': path.stat().st_size, 'description': 'Child offline reporting / repaired wire contract suite',
        'contains_raw_prompts_and_outputs': False})
parent_report.write(artifact, value)
