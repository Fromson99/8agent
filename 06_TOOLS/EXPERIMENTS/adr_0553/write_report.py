"""Record the completed frozen calls; never invokes a model or modifies results."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0553-qwen38-27b-reference-twelve'
PARENT = ROOT / '04_EXPERIMENTS/ADR/ADR-0483-qwen-ambiguous-reference-probe'
OUT = ADR / 'artifacts/run-001'
ARMS = ('qwen38-original', 'qwen38-normalized')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def block(value):
    return '```json\n' + json.dumps(value, ensure_ascii=False, indent=2) + '\n```\n'


def relative(path):
    return str(Path(path).relative_to(ROOT))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def paired(a, b, a_id, b_id):
    return {'baseline': a_id, 'candidate': b_id, 'total': 12,
            'candidate_only_correct': sum(b[k] and not a[k] for k in a),
            'baseline_only_correct': sum(a[k] and not b[k] for k in a),
            'both_correct': sum(a[k] and b[k] for k in a),
            'both_wrong': sum(not a[k] and not b[k] for k in a)}


def main():
    result = read(OUT / 'result.json')
    fixture = read(ADR / 'fixture.json')
    manifest = read(ADR / '실험/manifest.json')
    design = read(ADR / 'artifacts/frozen-design.json')
    old = read(PARENT / 'artifacts/run-001/result.json')
    values = result['by_arm']
    historical = {s['case_id']: s['qwen_exact'] for s in old['scores']}
    scores = {a: {s['case_id']: s for s in values[a]['scores']} for a in ARMS}
    correctness = {a: {k: v['exact'] for k, v in scores[a].items()} for a in ARMS}
    comparisons = [paired(historical, correctness[a], 'baseline', a) for a in ARMS]
    comparisons.append(paired(correctness[ARMS[0]], correctness[ARMS[1]], *ARMS))
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    manifest['runs'][0].update(status='complete', sha256=sha(OUT / 'result.json'), completed_at=now)
    by_arm = {'baseline': {'correct': old['qwen_exact'], 'total': 12, 'accuracy': old['qwen_exact']/12,
                           'new_model_calls': 0, 'historical_model': old['model']}}
    for arm, value in values.items():
        by_arm[arm] = {'correct': value['exact'], 'total': 12, 'accuracy': value['accuracy'],
                      'target_set_exact': value['target_set_exact'],
                      'unknown_false_resolutions': value['unknown_false_resolutions'],
                      'outside_candidate_ids': value['outside_candidate_ids'],
                      'success_criteria_pass': value['success'], 'model_calls': value['physical_calls']}
    all_usage = [u for a in ARMS for u in values[a]['usage']]
    manifest['results'] = {'status': 'complete', 'by_arm': by_arm, 'comparisons': comparisons,
        'judge_disagreements': None, 'judge_disagreement_note': 'No LLM judge; exact set and state comparison against immutable synthetic gold.',
        'usage': {'new_model_calls': len(all_usage), 'input_tokens': sum(u['input_tokens'] for u in all_usage),
                  'output_tokens': sum(u['output_tokens'] for u in all_usage),
                  'thinking_tokens': sum(u['thinking_tokens'] for u in all_usage),
                  'provider_reported_cost_usd': sum(u['cost_usd'] for u in all_usage),
                  'provider': 'openrouter', 'upstream_provider': 'Parasail', 'model': 'qwen/qwen3.8-27b'},
        'latency': {'by_arm_single_batch_seconds': {a: values[a]['seconds'] for a in ARMS},
                    'p50_p95': 'not meaningful with one batch per arm'},
        'error_taxonomy': [{'arm': ARMS[0], 'type': 'other', 'subtype': 'cardinality_label', 'count': 4},
                           {'arm': ARMS[1], 'type': 'unsupported_inference', 'case_id': 'structure-001', 'count': 1}]}
    decision = 'Proposed' if values[ARMS[1]]['success'] else 'Rejected'
    original_meta = (ADR / 'README.md').read_text().split('---', 2)[1]
    meta = original_meta.replace('status: Proposed', 'status: ' + decision)
    table = '| 방식 | 엄격 정답 | 대상 ID 집합 | 필수기권 오연결 | 입력/출력 토큰 | 비용 USD | 단일 배치 초 |\n|---|---:|---:|---:|---:|---:|---:|\n'
    old_cost = sum(u['cost_usd'] for u in old['usage'])
    table += f"| 과거 Qwen3.5 (역사적 기준) | {old['qwen_exact']}/12 | 12/12 | 0/4 | {old['usage'][0]['input_tokens']}/{old['usage'][0]['output_tokens']} | {old_cost:.8f} | {old['seconds']} |\n"
    for arm in ARMS:
        v = values[arm]; u = v['usage'][0]
        table += f"| {arm} | {v['exact']}/12 ({v['accuracy']:.1%}) | {v['target_set_exact']}/12 | {v['unknown_false_resolutions']}/4 | {u['input_tokens']}/{u['output_tokens']} | {v['cost_usd']:.8f} | {v['seconds']} |\n"
    text = f'''---{meta}---

# ADR-0553: Qwen3.8-27B FP8 모호 참조 12건

## 1. 결정 요약

{decision}. 사용자 지정 OpenRouter Qwen3.8-27B, Parasail FP8, thinking off로 두 방식 각1회 실행했다.
기존 출력은 8/12, 현재 서버 상태 계산 방식은 11/12다. 후자는 존재하지 않는 제9항을 상위 제4조로 연결한 1건 때문에 사전 오연결0 관문을 통과하지 못했다. MAIN 불변.

선점 이력은 [claim](claim.json)과 [manifest](실험/manifest.json)의 append-only reservation에 있다.

## 2. 문제와 변경 전 구조

ADR-0483의 Qwen3.5는 대상 집합12/12였지만 범위4건에 MULTI_TARGET 대신 RESOLVED를 출력하여 엄격8/12였다.
ADR-0484의 서버 상태 계산은 별도6건에서6/6이었다. 이번에는 원래12건 전체와 사용자 지정 작은 모델로 비교했다.

## 3. 가설과 사전 판정 기준

[사전 계획](PLAN.md), [동결 설계](artifacts/frozen-design.json)에 10/12 이상 exact decision+ID set,
필수 UNKNOWN4건 오연결0, 후보/evidence 밖ID0, 출력12건 완료, arm당1호출·USD0.10 이하·120초 이하를 고정했다.
모델·provider fallback, repair, 재시도와 사후 prompt 변경은 없다. 하나라도 실패하면 해당arm은 채택하지 않는다.

## 4. 실험 설계

| arm | 변경 | 고정 조건 |
|---|---|---|
| baseline | ADR-0483 완료 응답을 역사적 기준으로 상속, 신규호출0 | 원래12건·gold |
| qwen38-original | 기존 실제 system/user/schema와 상태 출력 유지, 모델/provider 변경 | 같은12건·temperature0·thinking off |
| qwen38-normalized | ADR-0484 system + 현행 frozen protocol/schema, 모델은 ID만 선택, 서버가 상태 계산 | 같은12건·모델·provider·후보/evidence |

실행 순서는 사전고정 original→normalized이다. 모델효과와 prompt/schema/서버 계약효과를 구분하며 순서·시간 편향을 통제하지 못한 단회probe다.
직접 부모는 ADR-0483-experiment-v1/qwen-review 완료arm, ADR-0484는 informed_by다. 두 결과를 운영 통합한 merge가 아니다.

## 5. 데이터·모델·재현성

원래 fixture 바이트 동일: `{sha(ADR/'fixture.json')}`. 합성 범위4·약칭/문맥4·필수기권4이며 실제 법령·내부 자료는 없다.
모델 `qwen/qwen3.8-27b`, 실제upstream Parasail, catalog quantization FP8, reasoning tokens0이다.
실제 request/response/usage와 후보revision 해시를 보존했다. gold는 모든 호출에서 제거했다.
현재 protocol/schema와 transport는 frozen snapshot에서만 import했다. 사용자 승인 모델 예외는 이 합성benchmark에만 결속하며 기본Gemma정책은 유지한다.
LLM judge 없음, 고정gold와 결정론 집합·상태 대조로 채점했다. 단회라 반복/다수결 없음.

## 6. 결과

{table}

paired 집계:

{block(comparisons)}

## 7. 사례별 오류 분석

기존 방식은 range-001~004에서 대상 ID를 모두 정확하게 골랐지만 상태를 RESOLVED로 표시했다. 과거Qwen3.5와 같은 실패형이다.
현재 방식은 범위4·약칭/문맥4·필수기권3을 맞췄다. structure-001은 제4조제9항이 없음을 스스로 설명하면서 가장 가까운 상위 제4조 전체를 선택했다.
이는 구조부족의 의도적 UNKNOWN을 근접대상으로 대체한 unsupported_inference다. 후보밖ID 생성은 양쪽0, evidence밖ID도0이다.
원문·응답과 정오를 [12건 인덱스](실험/README.md)에 보존했다. 판단상태11/12가 오연결허용의 근거는 아니다.

## 8. 비용·지연·회수 규모

새 모델 호출2회, 입력4604·출력2935·thinking0 토큰, 총비용USD{sum(u['cost_usd'] for u in all_usage):.8f}.
각arm 12건을 한 배치로 처리했으므로 위 지연은 질문당지연이 아니다. 단회p50/p95 일반화불가다.
corpus 검색·후보생성·golden recall·selectivity는 해당없다. 동결 합성 후보를 그대로 전달했고 회수·탈락 원장 mode는 not_applicable다.

## 9. 해석

관측: 모델을 바꿔도 기존 상태출력의 범위오류는 남았다. 서버 상태계산은 그4건을 해결했으나 기권1건을 잃어 엄격정답이 순증3건이었다.
원인 추론: 현재하네스 prompt에는 기존한국어prompt의 구조없는항은UNKNOWN이라는 구체 제약이 없고, 공급자출력에서도 상위조대체가 명시됐다.
이것이 유일원인인지는 검증하지 않았다. 사후prompt 변경이나 새 실행은 하지 않았다.

## 10. 한계와 일반화 가능 범위

기존에노출된 합성12건·각1batch·in_sample이며 실제법령검색·후보생성recall·최종법률답변·현장성능을 인증하지 않는다.
이 시험은12건 모두를 LLM에 직접 제시한 프로토콜probe다. 운영 prepare의 DATA_GAP 선분류, 운영자검토, generation apply까지는 실행하지 않았다.
현재 구축 prepare는 구조가없는사례를 DATA_GAP으로 모델대상에서 제외하므로 이번오연결이 자동운영적용된 것은 아니다.
현재방식은 prompt/schema도 바뀌었으므로11/12를 모델변경만의 효과로 해석하지 않는다. 과거baseline은다른시점·upstream AtlasCloud다.

## 11. 운영 결정·롤백 조건

{decision}, main_wiring=unchanged, decision_eligible=false. 원문DB·포인터·기본Gemma정책·GENOS 배포는 변경하지 않았다.
실험모델승인을 기록하는 검사기만 합성·인샘플·benchmark·해시고정·FP8·MAIN불변 조건에서 scoped override를 검증하도록 추가했다. 승인경계6/6 검사통과.
재실험은 새ADR에서기권제약/데이터부족분류를 사전동결하여 진행한다. 이결과를 승인연결로적용하지 않으며 기존릴리스rollback 작업은 없다.

## 12. 재현 명령

```bash
.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0553/study.py
.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0553-qwen38-27b-reference-twelve --final
```

완료run-001은재호출을거부한다. [동결 원시결과](artifacts/run-001/result.json) · [산출물manifest](artifacts/manifest.json).
'''
    (ADR / 'README.md').write_text(text.strip() + '\n')
    index = ['# 12개 합성 참조 결과\n', '| 사례 | 과거Qwen3.5 | Qwen3.8 기존 | Qwen3.8 현재하네스 |', '|---|---:|---:|---:|']
    paths = set()
    for arm in ('baseline', *ARMS):
        calls = PARENT/'artifacts/run-001/calls' if arm == 'baseline' else OUT/arm/'calls'
        call = next(calls.glob('call-*'))
        paths.update(call.glob('*.json'))
    for row in manifest['questions']:
        case = next(c for c in fixture['cases'] if c['case_id'] == row['case_id'])
        cid = case['case_id']
        clean = {k: v for k, v in case.items() if k != 'gold'}
        q = f"# 질문 {row['number']:03d} — {cid}\n\n## 1. 실행 메타\n\nADR-0553 / run-001 / exact; 신규모델 qwen/qwen3.8-27b Parasail FP8, thinking off; 시간 {now}. baseline은원래완료응답.\n\n## 2. 사용자 질문 원문\n\n{case['source']}\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n{block(case['gold'])}\n## 4. 제품 입력을 구성한 원값\n\n{block(clean)}\n회수·탈락 단계 원장: corpus 회수없음, fixture후보/evidence 동일, gold는선택후채점에만결합.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n"
        for arm in ('baseline', *ARMS):
            calls = PARENT/'artifacts/run-001/calls' if arm == 'baseline' else OUT/arm/'calls'
            call = next(calls.glob('call-*'))
            req = read(call/'request.json')
            response = read(call/'response.json')
            value = old if arm == 'baseline' else values[arm]
            q += f"### run-001 / {arm}\n\n전체배치의실제요청을그대로보존한다. 이사례는 user.cases 내 {cid}다.\n\n{block({'request_path':relative(call/'request.json'),'request':req,'response_path':relative(call/'response.json'),'response':response,'usage':value['usage'],'batch_seconds':value['seconds']})}\n"
        q += '## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n없음. 서버상태계산은결정론검증이며추가호출없음.\n\n## 7. 채점 호출과 반복 판정\n\nLLM judge없음. 사전gold와exact decision+ID set 결정론대조, 반복/다수결없음.\n\n## 8. 사례 최종 판정\n\n'
        for arm in ARMS:
            q += f"### {arm}\n\n{block(scores[arm][cid])}\n"
        q += f"과거 baseline exact={historical[cid]}. 독립사람judge없음. 실패형: " + ('unsupported_inference (없는하위항을상위조로대체).' if cid=='structure-001' else 'other / cardinality_label.' if cid.startswith('range-') else '없음.') + '\n'
        qp = ADR/'실험'/row['file'];qp.write_text(q);row['sha256']=sha(qp)
        index.append(f"| [{cid}]({row['file']}) | {int(historical[cid])} | {int(scores[ARMS[0]][cid]['exact'])} | {int(scores[ARMS[1]][cid]['exact'])} |")
    (ADR/'실험/README.md').write_text('\n'.join(index)+'\n')
    write_json(ADR/'실험/manifest.json',manifest)
    paths.update(p for p in (ADR/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json')
    paths.update([ADR/'fixture.json',ADR/'PLAN.md',Path(__file__),ROOT/'06_TOOLS/EXPERIMENTS/adr_0553/study.py'])
    for c in design['candidates']:
        paths.add(ROOT/c['manifest_path'])
        paths.update(p for p in (ROOT/c['snapshot_path']).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths.update(ROOT/p for p in design['file_hashes'])
    write_json(ADR/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0553',
        'files':[{'path':relative(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(paths)]})
    workspace_index = ROOT/'04_EXPERIMENTS/ADR/README.md'
    addition='- [ADR-0553 Qwen3.8-27B FP8 모호참조12건](ADR-0553-qwen38-27b-reference-twelve/README.md) — 기존8/12·현재서버하네스11/12, 구조부족1건오연결로Rejected. 실제2호출·USD0.00756196, MAIN불변.\n\n'
    index_text = workspace_index.read_text()
    if 'ADR-0553 Qwen3.8' not in index_text:
        workspace_index.write_text(index_text.replace('# ADR workspace\n\n','# ADR workspace\n\n'+addition,1))
    print('Recorded both calls, all twelve cases, paired results and immutable artifact hashes.')


if __name__ == '__main__':
    main()
