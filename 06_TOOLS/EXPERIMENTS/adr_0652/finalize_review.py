"""Post-run accounting against the already frozen criteria; no product changes."""
import hashlib, importlib.util, json
from pathlib import Path

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0652-shortcut-main-separated-validation'
D = A / 'artifacts/design'
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v): p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + '\n')

assert read(A/'실험/manifest.json')['reservation']['status'] == 'in_progress'
spec = importlib.util.spec_from_file_location('accounting', R/'06_TOOLS/EXPERIMENTS/adr_0649/finalize.py')
accounting = importlib.util.module_from_spec(spec); spec.loader.exec_module(accounting)
accounting.main(str(A.relative_to(R)))
p = A/'artifacts/run-001/result.json'; result = read(p); b = read(D/'bindings.json')
frozen = all(sha(R/f) == h for seal in ['freeze.json', 'release-freeze.json'] for f, h in read(D/seal)['files'].items())
result['checks'].update(
    candidate_nine_turns=result['summary']['integrated']['total'] == 9,
    contracts_102_passed='102 passed' in (A/'artifacts/contracts.txt').read_text(),
    cli_wiring=all((A/'artifacts'/n).read_text().startswith('usage:') for n in ['cli-action-memory.txt', 'cli-unified-memory.txt']),
    frozen_code_data_release=frozen and sha(R/b['generation']/'manifest.json') == b['generation_manifest_hash'] and sha(R/b['generation']/'store.sqlite') == b['source_sha256'],
    active_unchanged=sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == b['active_pointer_hash'],
    request_p95_within_240_seconds=result['summary']['integrated']['p95_seconds'] <= 240,
    calls_within_100=result['summary']['integrated']['calls'] <= 100,
)
result['strict_success'] = all(result['checks'].values())
result['interpretation'] = 'Fresh separated public/synthetic scenarios: explicit validated v6 parent versus the same frozen integrated implementation selected by default configuration. No claim of superiority over historical active release. Latencies include concurrent independent case workers; p95 is nearest-rank maximum for n=9.'
put(p, result)
m = read(A/'실험/manifest.json'); m['runs'][0]['sha256'] = sha(p)
m['results']['comparisons'] = [{'paired': result['paired'], 'checks': result['checks']}]
put(A/'실험/manifest.json', m)
# Preserve failed holdout without changing its predeclared criteria.
text = (A/'README.md').read_text().replace('status: Proposed', 'status: Rejected').replace('decision_eligible: false', 'decision_eligible: true')
text = text.replace('빈 첫 선택과 누락 검토의 의미가 섞인 지침을 구분하고, 빈 선택에는 원문 구간과 이탈 사유를 제공한다. 현재 사실과 사건 연결은 실제 모델로 검증한다.', '첫 근거 선택의 모호한 지침과 빈 선택 회복은 ADR-0649에서 수정했다. 실제 멀티턴에서 current_facts를 법률 출처 ID로 만든 실패는 ADR-0651에서 실제 근거 ID enum과 검증 오류 구체화로 수정했다. 이 평가에서는 제품을 더 수정하지 않고, 새 상법·정보공개·금융판매 사례에 대해 명시적 v6와 기본 설정 v6를 비교했다.')
text = text.replace('MAIN 불변. 후속 분리 평가 통과 전 승격하지 않는다.', '최종 9개 중 8개만 통과해 Rejected다. 금융판매 정정에서 사용자가 제한한 판단 범위를 넘어 영업 허용을 단정했다. MAIN을 변경하지 않는다. 사실 정정의 저장 성공만으로 답변 정확성을 보증할 수 없었다. 새 ADR에서 현재 요청 범위의 전달을 수정한 뒤 다시 검증한다.')
text = text.replace('06_TOOLS/EXPERIMENTS/adr_0649/run.py', '06_TOOLS/EXPERIMENTS/adr_0652/run.py')
text += '\n## 추가 사전 기준의 최종 확인\n\n' + accounting.block(result['checks']) + '\n' + result['interpretation'] + '\n\nADR-0650의 완료된 artifact manifest 미완성 메타데이터는 역사적 오류로 보존했다. 여기서는 동일 승격 코드를 포함한 후보에서 102개 계약 검사를 새로 통과했고, ADR-0652 자체의 전체 아티팩트 목록과 최종 검증을 승격 근거로 사용한다.\n'
(A/'README.md').write_text(text)
files = []
for p in sorted((A/'artifacts').rglob('*')):
    if not p.is_file() or p == A/'artifacts/manifest.json' or p.name.endswith(('-wal', '-shm')) or '__pycache__' in p.parts:
        continue
    files.append({'path': str(p.relative_to(R)), 'sha256': sha(p), 'bytes': p.stat().st_size, 'description': 'Frozen inputs and release stage; actual model requests, responses, journals, measurements and source-only grading', 'contains_raw_prompts_and_outputs': p.name in ['request.json', 'response.json']})
put(A/'artifacts/manifest.json', {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-0652', 'files': files})
print(json.dumps({'checks': result['checks'], 'summary': result['summary'], 'artifacts': len(files)}, ensure_ascii=False, indent=2))
