"""Render exact existing no-network receipts and hash artifacts; does not run models."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0475-source-first-double-harness-wiring'


def main():
    fixture = json.loads((ADR / 'fixture.json').read_text())
    sections = [
        '# 질문 001 — cm-003\n',
        '## 1. 실행 메타\n\nADR-0475 / run-001. 2026-09-20. exact 보존. baseline은 구조 assertion만 실행했다. candidate rev-001은 scripted-no-network 대역이며 실제 모델은 호출하지 않았다.\n',
        '## 2. 사용자 질문 원문\n\n```text\n' + fixture['question'] + '\n```\n',
        '## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n기준답변·gold 채점 사용 없음. 실제 법률 답변을 생성하거나 검증한 실행이 아니다.\n',
        '## 4. 제품 입력을 구성한 원값\n\n아래 trace와 wire는 전량 보존한다. 제품 선택의 입력에는 기준답변/decisive ID가 없다.\n']
    for title, rel in [
        ('### 회수 좌표·원문·제시 view — 전체', 'check-002/manual-trace.json'),
        ('### 회수·탈락 단계 원장 — run·arm별', 'retrieval-stage-ledger.json'),
        ('## 5. 제품 모델 호출 — run·arm별 실제 원문', 'check-002/manual-wire.json'),
        ('### 기존 Pipeline을 통한 별도 scripted 요청 전체', 'check-002/pipeline-wire.json'),
        ('### Pipeline 최종 결과 전체', 'check-002/pipeline-result.json')]:
        sections.append(title + '\n\n모의 호출/구조 감사이며 실제 모델 판단이 아니다. 단계 원장은 사후 재구성이며 사전 동결 품질 비교가 아니다.\n\n```json\n' + (ADR / 'artifacts' / rel).read_text().rstrip() + '\n```\n')
    sections.extend([
        '## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n실제 LLM 호출 없음. 모의 응답과 모든 요청·journal은 artifacts에 보존했다. 별도 합성 단위 검사에서 형식 복구 2회와 물리 예산 2회를 확인했다.\n',
        '## 7. 채점 호출과 반복 판정\n\n채점 호출·정답률·다수결 모두 해당 없음.\n',
        '## 8. 사례 최종 판정\n\n후보 연결 검사 23/23 및 추가 계약 9/9 통과. 실제 CM003 정답 여부 미평가. baseline 대비 paired 정답/회귀 미측정. 첫 실행은 기존 엔진 해시 결속 실패로 끝났고, 격리 runner 결속을 고친 두 번째 실행이 통과했다. 원 후보 rev-001은 유지했다. 기존 회귀 두 assertion 실패와 광역 검사 정체는 별개이며 전체 회귀 통과로 보고하지 않는다.\n'])
    (ADR / '실험/질문-001-cm-003.md').write_text('\n'.join(sections))
    paths = sorted(p for p in (ADR / 'artifacts').rglob('*') if p.is_file() and p.name != 'manifest.json')
    paths += [ADR / 'PLAN.md', ADR / 'fixture.json', ROOT / '05_TESTS/CONTRACTS/test_source_first_candidate.py']
    paths += sorted((ROOT / '06_TOOLS/EXPERIMENTS/adr_0475').glob('*.py'))
    rows = []
    for p in paths:
        rows.append({'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                     'bytes': p.stat().st_size, 'description': 'No-network contract artifact; scripted data is not model quality evidence.',
                     'contains_raw_prompts_and_outputs': 'wire' in p.name or 'journal' in p.name or 'trace' in p.name})
    value = {'schema_version': 'adr-artifacts-v1', 'adr_id': 'ADR-0475',
             'created_at': '2026-09-20T03:31:33.595643Z', 'files': rows}
    (ADR / 'artifacts/manifest.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'archived_files': len(rows), 'question_bytes': (ADR / '실험/질문-001-cm-003.md').stat().st_size}))


if __name__ == '__main__':
    main()
