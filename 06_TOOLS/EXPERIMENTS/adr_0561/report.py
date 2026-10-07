from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0559'))
import report as parent_report
parent_report.ADR = ROOT/'04_EXPERIMENTS/ADR/ADR-0561-node-action-experience-citation-contract'
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
text = readme.read_text().replace('계약 검사15개 통과', '계약 검사18개 통과')
text = text.replace('06_TOOLS/EXPERIMENTS/adr_0559/test_contracts.py',
    '06_TOOLS/EXPERIMENTS/adr_0561/test_contracts.py')
text = text.replace('adr_candidate.py validate --candidate 02_BACKEND/lawrag/research/candidates/adr_0559/experience',
    'adr_candidate.py validate 02_BACKEND/lawrag/research/candidates/adr_0561/experience')
text = text.replace('## 4. 실험 설계\n', '''## 4. 실험 설계

완료 부모 ADR-0560/experience의 byte 동일 기억 코드를 재사용했다. 이전 출력 계약은
예외 사례에서 E 근거 핸들과 article 원문 식별자를 혼동해 검증부가 거부했다.
이번 분기는 두 arm 모두 citable_source_ids를 실제 읽은 원문에서 생성해 prompt와
source_ids의 enum으로 제공한다. 나머지 호출 형식·원문·질문·기억 코드는 그대로다.
schema-in-prompt=true, answer 필드 마지막, max_output_tokens=1024, repair=0이다.
기억 안내만 paired arm 차이며 부모 실패와 사전 gold를 덮어쓰지 않았다.
실제 system/user와 native journal request의 일치, 잘못된 E 핸들 거부를 계약 검사했다.
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
