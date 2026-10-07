"""Render the sealed single-run result and exact payloads; never changes product code."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0476-source-first-qwen-autonomy'
OUT = ADR / 'artifacts/run-001'


def read(p):
    return json.loads(p.read_text())


def main():
    m = read(ADR / 'artifacts/metrics.json')
    result = read(OUT / 'result.json')
    old = (ADR / 'README.md').read_text()
    header = old.split('---', 2)[1]
    header = header.replace('status: Proposed', 'status: Rejected')
    table = '| 단계 | 원문 수 | 결정 조문 수 |\n|---|---:|---:|\n'
    for name, row in m['stages'].items():
        table += f'| {name} | {row["sources"]} | {row["decisive"]}/2 |\n'
    texts = [
        ('결정 요약', 'CM003 실제 Qwen 자동 답변 검증 **실패**. 필요한 원문 두 개는 최초 입력에 전달됐으나 같은 READ 요청을 두 번 반복하고 근거를 선택하지 않았다. 새 근거/선택 진전 없음 조건으로 종료돼 최종 주장 0개다. Rejected는 이번 성공 기준 미달을 뜻하며 전체 아키텍처의 불가능성을 뜻하지 않는다. MAIN unchanged.'),
        ('문제와 변경 전 구조', '부모 ADR0475는 scripted 계약 23개와 단위 계약 9개를 통과했으나 실제 모델 행동은 미검증이었다. 그 동결 탐색·선택·작성 코드를 그대로 실행하고 전송 대역만 실제 Qwen으로 교체했다. 기존 장부 형식 실패를 이번 실패와 혼동하지 않는다.'),
        ('가설과 사전 판정 기준', '[PLAN.md](PLAN.md)와 [frozen-design](artifacts/frozen-design.json)을 첫 모델 호출 전에 고정했다. 모델이 스스로 근거를 선택하고 인용된 최종 주장을 생성해야 한다. 원문 발견, 실제 제시, 선택, 최종 보존을 분리한다. judge 호출은 0이며 의미정답 인증은 범위 밖이다. 최종 주장 0으로 성공 기준 미달이다.'),
        ('실험 설계', 'baseline은 부모 scripted 구조 기록만 참조하고 동시 모델 비교를 실행하지 않았다. candidate는 CM003 한 문항 단회. 동일 145 공개 문서 범위·원질문·14콜 예산·300초 controller·max_no_progress=2. 정답과 decisive ID는 제품 runner에서 읽지 않는다. 후보 원문·선택을 사람이 지정하지 않았다. API/publication E2E 재검사가 아니라 동일 controller의 investigate→select→assemble→answer_and_review 구성요소 실행이다.'),
        ('데이터·모델·재현성', '사용자가 외부 원문 전송과 Qwen을 명시 승인했다. 요청별 승인에 source store hash·문서 범위·endpoint·model을 결속했다. 원문 세대 export 플래그는 보존하고 외부 transport를 external로 표시했다. 모델은 qwen/qwen3.5-122b-a10b, 실제 upstream은 SiliconFlow, FP8/no reasoning 정책. GENOS 직접 실행이 아니다. 후보와 공통 single-send 어댑터를 rev-001로 고정했고 숨은 repair는 없다.'),
        ('결과', table + f'\n모델 실제 호출 {m["physical_calls"]}회, journal {m["journal_attempts"]}회로 일치. 형식 오류·네트워크 오류 없음. 최종 주장은 {m["claim_count"]}개, gate={m["gate"]}. 제어기가 FINAL로 끝난 사실은 답변 성공이 아니다. 기본 선읽기 8개에 결정 조문 2개가 이미 포함됐다. 추가 검색 0회, READ 요청 2회, 신규 READ 근거 0개, 선택 0개. 독립 의미정답은 채점하지 않았다.'),
        ('사례별 오류 분석', '두 응답은 동일하게 시행세칙 제23조 카드(P3)를 읽으라고 요청했다. 이 조문은 최초 view의 E7에 이미 원문으로 있었다. 두 번째 view는 첫 번째와 base_state_revision·remaining·view_id만 다르고 cards/evidence는 같았다. 모델 입력에는 직전 도구 결과 요약과 P→E 읽음 상태 연결이 명시되지 않았다. 따라서 읽음 상태/행동 결과 전달 부족이 반복에 기여했을 가능성이 있다. 이는 관찰에 근거한 가설이며 단회로 원인을 확정하지 않는다. 직접 중단 원인은 max_no_progress=2이고 직접 답변 부재 원인은 selected=0이다. 기존 finding 장부 형식 오류나 결정 조문 검색 누락이 아니다.'),
        ('비용·지연·회수 규모', f'실제 호출 2회. 입력 {m["input_tokens"]:,}토큰, 출력 {m["output_tokens"]:,}토큰. provider 보고 비용 ${m["provider_reported_cost_usd"]:.8f}. 전체 로컬 실행 {m["seconds"]}초(초기화 포함), 단회이므로 의미 있는 p50/p95 추정 없음. corpus 26,597 canonical 조문. 회수 단계는 실행 전 동결했고 gold 좌표는 종료 후 scorer에서만 결합했다. baseline은 미실행이므로 원장상 빈 집합/0을 기준군 성능으로 해석하지 않는다.'),
        ('해석', '검색·선읽기는 필요한 원문을 전달했다. 실패 지점은 READ 이후 선택·작성 전환이다. 무모델 계약 통과가 실제 모델의 자율 과업 성공을 보장하지 않음을 확인했다. 모델이 READ를 요청한 사실만으로 탐색이 복원됐다고 주장할 수 없다. 이번에는 이미 읽은 원문을 반복 요청했을 뿐이다.'),
        ('한계와 일반화 가능 범위', 'CM003 인샘플 단회. 동시 기준군 없음, 독립 법률 채점 없음, GENOS 없음. 초기 원문량이 약 2만 입력 토큰이었으며 실제 병목의 원인 분리 실험은 하지 않았다. 원문 최신성 미확인. 모델 능력 전체나 전체 설계의 실패로 일반화하지 않는다. 성공할 때까지 프롬프트·코드를 수정하거나 반복 실행하지 않았다.'),
        ('운영 결정·롤백 조건', 'MAIN·기본 모델 정책·원문 세대·기존 완료 ADR은 변경하지 않았다. 후보는 미승격. 후속으로 읽은 카드와 근거 별칭의 연결, 직전 행동 결과, 반복 요청 피드백을 명시하는 인터페이스 수정을 검토할 수 있다. 수정/추가 유료 실험은 별도 요청과 새 ADR 범위다. 저장소 전체 graph에는 기존 다른 ADR 오류가 남아 있어 저장소 전체 마감 검증 통과를 주장하지 않는다.'),
        ('재현 명령', 'WSL 저장소 루트에서 실행한다. `run_autonomy.py`는 무호출 사전 검증이며 `--execute`는 유료 실행이다. 기존 run-001이 있으면 재실행/덮어쓰기를 거부한다. 새 반복은 새 ADR에서 한다.\n\n```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0476/run_autonomy.py\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0476-source-first-qwen-autonomy --final\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR\n```\n\n[질문별 전체 입출력](실험/질문-001-cm-003.md) · [산출물 해시](artifacts/manifest.json) · [지표](artifacts/metrics.json)')]
    (ADR / 'README.md').write_text('---' + header + '---\n\n# 원문 중심 더블하네스 CM003 Qwen 자율 실행 검증\n\n' + '\n\n'.join(f'## {i}. {title}\n\n{body}' for i, (title, body) in enumerate(texts, 1)) + '\n')
    (ADR / '실험/README.md').write_text('# 실험 질문 인덱스\n\n| case | run | arm | 판정 | 기록 |\n|---|---|---|---|---|\n| cm-003 | run-001 | qwen-autonomous | 자동 답변 실패: 선택/주장 0 | [전체](질문-001-cm-003.md) |\n\nbaseline은 부모 구조 참고이며 별도 모델 실행 없음. 제품 2콜, judge 0콜. 단계 원장과 호출 원문은 아래 질문 파일에 전량 보존. MAIN unchanged.\n')
    fixture = read(ADR / 'fixture.json')
    question = '# 질문 001 — cm-003\n\n## 1. 실행 메타\n\n2026-09-20 / run-001 / qwen-autonomous / exact. Qwen 실제 호출 2회. baseline 미실행.\n\n## 2. 사용자 질문 원문\n\n' + fixture['question'] + '\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n기준답변/의미정답 채점 없음. decisive 좌표는 제품 종료 후 원장 scorer에만 결합했다.\n\n## 4. 제품 입력을 구성한 원값\n'
    payloads = [('### 전체 원문·카드·선택 trace', OUT / 'trace.json'),
                ('### 회수·탈락 단계 원장 — run·arm별', ADR / 'artifacts/retrieval-stage-ledger.json'),
                ('## 5. 제품 모델 호출 — run·arm별 실제 원문', OUT / 'journal-tables.json')]
    for directory in sorted((OUT / 'calls').glob('call-*')):
        for file in sorted(directory.glob('*.json')):
            payloads.append(('### ' + directory.name + ' / ' + file.name, file))
    payloads += [('### 전체 실행 결과', OUT / 'result.json')]
    for title, path in payloads:
        if path.exists():
            question += '\n' + title + '\n\n```json\n' + path.read_text().rstrip() + '\n```\n'
    question += '\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n위 investigate 2회뿐이며 compose/review에 도달하지 않았다. 숨은 호출/repair 없음.\n\n## 7. 채점 호출과 반복 판정\n\njudge 0회, 독립 법률 정확도 미평가.\n\n## 8. 사례 최종 판정\n\n자동 답변 성공 기준 미달. 원문 두 개 전달 후 동일 READ 반복, 선택 0·주장 0. retrieval_miss가 아니라 other: no-progress before evidence selection. 단회 결과를 일반화하지 않는다.\n'
    (ADR / '실험/질문-001-cm-003.md').write_text(question)
    paths = [p for p in (ADR / 'artifacts').rglob('*') if p.is_file() and p != ADR / 'artifacts/manifest.json']
    paths += list((ROOT / '06_TOOLS/EXPERIMENTS/adr_0476').glob('*.py')) + [ADR / 'PLAN.md', ADR / 'fixture.json']
    rows = [{'path': str(p.relative_to(ROOT)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
             'bytes': p.stat().st_size, 'description': 'Sealed autonomous probe input/output or audit',
             'contains_raw_prompts_and_outputs': p.name in ('request.json', 'response.json', 'journal-tables.json', 'journal.sqlite')}
            for p in sorted(paths)]
    manifest = read(ADR / 'artifacts/manifest.json')
    manifest['files'] = rows
    (ADR / 'artifacts/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report_written': True, 'artifacts': len(rows), 'autonomous_answer_success': False}))


if __name__ == '__main__':
    main()
