"""One Markdown for actual v32 provider IO and the inherited v31 comparison."""
from pathlib import Path
from collections import Counter
import base64
import hashlib
import json
import statistics

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0435-image-pattern-gemini-audit'
ART = ADR / 'artifacts'
OLD = ROOT / '04_EXPERIMENTS/ADR/ADR-0434-basic-first-gemini-audit/artifacts'


def read(p):
    return json.loads(p.read_text())


def block(value, language='json'):
    value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return '\n```' + language + '\n' + value + '\n```\n'


def link(p, label=None):
    return f'[{label or p.name}](<{p.resolve()}>)'


def totals(rows):
    result = {key: sum(r.get(key) or 0 for r in rows) for key in
              ('input_tokens', 'output_tokens', 'text_tokens', 'image_tokens', 'cached_input_tokens', 'thinking_tokens')}
    result.update(calls=len(rows), image_occurrences=sum(len(r['images']) for r in rows),
                  unique_images=len({h for r in rows for h in r['images']}),
                  input_chars_max=max((r['input_chars'] for r in rows), default=0),
                  output_tokens_max=max((r['output_tokens'] or 0 for r in rows), default=0),
                  repair_calls=sum('-repair-' in r['phase'] for r in rows),
                  cutoffs=sum(r['finish'] == 'MAX_TOKENS' for r in rows))
    times = [r['seconds'] for r in rows if r['seconds'] is not None]
    result.update(call_p50=statistics.median(times) if times else None,
                  call_p95_observed=sorted(times)[max(0, int(len(times)*.95+.999)-1)] if times else None)
    return result


def main():
    result = read(ART / 'results.json'); old = read(OLD / 'results.json')
    previous = read(OLD / 'token-audit.json')['totals']
    cases = read(ART / 'dataset/cases.json'); sections = {}; rows = []; per_case = []
    images = {}; forbidden = {'source_blocks', 'recipe', 'actual_structure', 'observed_markers', 'visual_evidence'}
    for case, outcome in zip(cases, result['cases']):
        cid = case['case_id']; directory = ART / 'runs' / cid; call_rows = []
        text = f'\n## {cid}\n\n' + link(ROOT / case['pdf'], '이번에 보낸 모의 원본 PDF') + '\n'
        text += '\n### 실행 결과와 독립 정답 대조\n' + block({k: v for k, v in outcome.items() if k not in {'usage', 'cached_meta'}})
        text += '\n### 코드 입력 원문·초기 힌트\n\n이 텍스트 전체는 코드 입력이며 모델에 보내지 않았습니다.\n'
        text += block({'hints': case['hints'], 'blocks': read(ROOT / case['blocks'])})
        for d in sorted((directory / 'provider').glob('call-*')):
            req = read(d / 'request.json'); raw = read(d / 'response.json') if (d / 'response.json').exists() else {}
            user = req['contents'][0]['parts'][0]['text']; data = json.loads(user)
            phase = d.name.split('-', 2)[2]
            usage = next((u for u in outcome['usage'] if u['phase'] == phase), {})
            u = raw.get('usageMetadata', {}); mods = {x['modality']: x['tokenCount'] for x in u.get('promptTokensDetails', [])}
            image_ids = []
            for p in req['contents'][0]['parts']:
                if 'inlineData' not in p: continue
                binary = base64.b64decode(p['inlineData']['data']); h = hashlib.sha256(binary).hexdigest()
                path = ART / 'report-images' / (h + '.png'); path.parent.mkdir(exist_ok=True)
                if not path.exists(): path.write_bytes(binary)
                images[h] = path; image_ids.append(h)
            row = {'case': cid, 'call': int(d.name.split('-')[1]), 'phase': phase, 'input_chars': len(user),
                   'input_tokens': u.get('promptTokenCount'), 'output_tokens': u.get('candidatesTokenCount'),
                   'text_tokens': mods.get('TEXT', 0), 'image_tokens': mods.get('IMAGE', 0),
                   'cached_input_tokens': u.get('cachedContentTokenCount', 0), 'thinking_tokens': u.get('thoughtsTokenCount', 0),
                   'seconds': usage.get('seconds'), 'images': image_ids,
                   'finish': next(iter(raw.get('candidates', [])), {}).get('finishReason'),
                   'forbidden_input_keys': sorted(set(data) & forbidden),
                   'body_tail_in_text': '모의자료끝' in user,
                   'input_keys': list(data), 'path': str(d.relative_to(ROOT))}
            rows.append(row); call_rows.append(row)
            text += f"\n### 호출 {row['call']} — {phase}\n\n" + block(row)
            text += '\n' + link(d / 'request.json', '실제 전송 JSON (이미지 base64 포함)') + ' · ' + link(d / 'response.json', '원응답') + '\n'
            text += '\n**System 실제 문자열 전체**\n' + block(req['systemInstruction']['parts'][0]['text'], 'text')
            text += '\n**User 실제 문자열 전체**\n' + block(user, 'text')
            text += '\n**API 설정·스키마**\n' + block(req['generationConfig'])
            text += '\n**로컬 검증 스키마**\n' + block(read(d / 'validation-schema.json'))
            text += '\n**이미지 입력 — 전송 순서**\n\n'
            text += '\n'.join(f'{i}. {link(images[h], h[:12])}' for i, h in enumerate(image_ids, 1)) if image_ids else '없음: 텍스트 전용 호출.'
            text += '\n\n**Provider 원응답 전체**\n' + block(raw)
            if (d / 'output.json').exists(): text += '\n**해석된 출력**\n' + block(read(d / 'output.json'))
            for f in directory.glob('structure-recipe-runs/*/' + phase + '-feedback-input.json'):
                feedback = read(f)
                text += '\n**코드가 거부한 이유**\n' + block({k: feedback.get(k) for k in ('previous_answer', 'correction')})
        summary = totals(call_rows); summary.update(case=cid, passed=outcome['pass'], seconds=outcome['seconds'],
                                                   status=outcome['status'], final_correct=outcome['final_correct'])
        per_case.append(summary); sections[cid] = text
    measured = totals(rows)
    measured.update(passed=sum(bool(c['pass']) for c in result['cases']), documents=len(cases), seconds=result['seconds'],
                    source_unchanged=all(c['source_unchanged'] for c in result['cases']),
                    cache_calls=sum(c.get('cache_calls', 0) for c in result['cases']),
                    cache_checked_documents=sum('cache_calls' in c for c in result['cases']),
                    replay_identical_on_checked=all(c['replay_identical'] for c in result['cases'] if 'cache_calls' in c),
                    false_approvals=sum(c['false_visual_approval'] for c in result['cases']),
                    input_contract_ok=all(not r['forbidden_input_keys'] and not r['body_tail_in_text'] and
                      (bool(r['images']) == ('-vlm-review' in r['phase'])) for r in rows))
    comparison = {'input_reduction_pct': 100*(1-measured['input_tokens']/previous['input_tokens']),
                  'output_reduction_pct': 100*(1-measured['output_tokens']/previous['output_tokens']),
                  'call_reduction_pct': 100*(1-measured['calls']/previous['calls']),
                  'wall_time_reduction_pct_observed': 100*(1-result['seconds']/old['seconds']),
                  'baseline_inherited': True, 'baseline': previous, 'baseline_seconds': old['seconds']}
    audit = {'totals': measured, 'comparison': comparison, 'cases': per_case, 'calls': rows}
    (ART / 'token-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n')
    header = '# v32 실제 Gemini 성능·토큰·입출력\n\n'
    header += '2026-09-16 · ADR-0435 · gemini-3.1-flash-lite · 동일 모의 PDF 3건 · 각 1회 · MAIN/GENOS 배포 변경 없음\n\n'
    header += f"**최종 성공 {measured['passed']}/3, 입력 {measured['input_tokens']:,}토큰, 출력 {measured['output_tokens']:,}토큰, {measured['calls']}회 호출.** 같은 모의 문서를 사용한 v31 대비 입력 {comparison['input_reduction_pct']:.1f}% 감소입니다.\n\n"
    header += '| 항목 | v31 기존 실측 | v32 이번 실측 |\n|---|---:|---:|\n'
    for label, before, after in [('최종 성공', '0/3', f"{measured['passed']}/3"), ('모델 호출', previous['calls'], measured['calls']),
                                 ('입력 토큰', previous['input_tokens'], measured['input_tokens']), ('출력 토큰', previous['output_tokens'], measured['output_tokens']),
                                 ('텍스트 입력 토큰', previous['text_tokens'], measured['text_tokens']), ('이미지 입력 토큰', previous['image_tokens'], measured['image_tokens']),
                                 ('추가 재시도 호출', previous['repair_calls'], measured['repair_calls']),
                                 ('전체 실행 초', old['seconds'], result['seconds'])]:
        header += f'| {label} | {before} | {after} |\n'
    header += '\n## 문서별 결과\n\n| 문서 | 쪽 | 최종 성공 | 호출 | 입력 토큰 | 출력 토큰 | 실행 초 |\n|---|---:|---|---:|---:|---:|---:|\n'
    for case, s in zip(cases, per_case):
        header += f"| {s['case']} | {case['pages']} | {'통과' if s['passed'] else '실패/보류'} | {s['calls']} | {s['input_tokens']} | {s['output_tokens']} | {s['seconds']} |\n"
    header += '\n## 무엇을 확인했나\n\n'
    header += '정상 문서 보존, 뒤집힌 `가. → 1. → 1)` 계층 복구, 긴 본문 문서의 전체 페이지 검수를 확인하는 고정 사례입니다. 정답은 모델에 전달하지 않고 모든 제품 호출 종료 후 블록별 직접 부모로 비교했습니다. 완료한 문서는 저장된 틀로 재실행해 동일 트리·추가 호출 0회를 검사했습니다.\n\n'
    header += block({k: measured[k] for k in ['source_unchanged', 'cache_checked_documents', 'cache_calls', 'replay_identical_on_checked', 'false_approvals', 'input_contract_ok', 'cutoffs', 'input_chars_max', 'output_tokens_max']})
    header += '\n완료한 2건만 캐시 재실행을 검사했고 둘 다 동일 트리·추가 호출 0회였다. 실패한 긴 문서는 캐시 재실행에 도달하지 못했다.\n'
    header += '\n## 긴 문서가 실패한 이유\n\n'
    header += '출력 한도 때문이 아니다. 초기 트리는 제1~6조 모두 정답이고 각 조 span에 본문이 이미 포함됐다. 그런데 세 번째 VLM 호출이 3~5쪽 본문 b7/b8 등을 부모 없는 항목으로 판단해 수정을 요구했다. 그림은 본문에 `n=none`을 표시하며 실제 소속 노드를 숨긴다. 이 표시가 오판을 유발했다는 것은 코드·응답에 근거한 추론이다. VLM은 실제 n2인 b6을 `n=6`이라고 지칭하는 등 블록/노드 ID도 혼동했다.\n\n'
    header += '부모 선택 입력에는 제3~5조(F1)와 본문 끝에서 인식된 20./21./30.(F2)가 전달됐다. 모델은 F2→F1을 선택했지만 본문 소속 문제를 해결하는 계약과 번호 체계 부모 선택 계약이 맞지 않는다. 이후 6~15 블록 범위를 수정하면서 기본 구간이 분할됐고, 저장된 두 번째 트리에서는 제6조(b15)가 사라졌다. 해당 단일 조문 구간 로그는 활성 후보 없음이다. 정확한 엔진 원인까지 이번 측정에서 수정·재시험하지 않았다.\n\n'
    header += 'VLM이 같은 수정을 다시 요구한 뒤 코드가 반복 구조/변화 없는 수정을 거부했고 2회 repair 후 보류됐다. 정상 최종 결과로 저장되지는 않았다. 따라서 입력 50% 절감 조건은 충족했지만 3/3 완료라는 사전 성공 기준은 미달이다. 소속 표시·ID 구분과 분할 후 기존 조문 보존을 먼저 고쳐야 한다.\n'
    header += '\n## 해석과 한계\n\n'
    header += f"VLM에 원본/bbox 이미지와 번호 체계만 보내고, 수정 LLM에는 이미지 없이 의견·범위·부모 선택만 보냈습니다. 이미지 전달은 {previous['image_occurrences']}장→{measured['image_occurrences']}장(중복 포함)입니다. 정상 의견에 대한 별도 판정·추가 승인 반복을 제거한 계약을 그대로 시험했습니다.\n\n"
    header += f"provider의 캐시 입력 {measured['cached_input_tokens']:,}토큰은 입력 총량 안에 포함됩니다. 다시 더하지 않았습니다. 달러 비용·과금액은 실측하지 않았습니다.\n\n"
    header += '이 결과는 합성 문서 3건의 인샘플 1회 실행입니다. 실제 내규·복잡한 표·다단·OCR 및 GENOS 내부 모델의 정확도는 확인하지 않았습니다. PDF 파서는 실행하지 않았으며 이미지와 동일하게 작성된 고정 블록을 사용했습니다. v31은 이전 실행 결과를 재사용했으므로 동시 무작위 A/B가 아닙니다. 지연은 관측치이며 운영 속도 보장이 아닙니다. v31 긴 문서는 첫 3쪽에서 중단됐으므로 전체 6쪽 완료 비용의 동일 구간 비교는 아닙니다.\n\n'
    header += '제품 코드는 이번 실험에서 바꾸지 않았습니다. 발송된 v32 구조 모듈의 해시와 일치하는 격리 snapshot을 사용하고 전송만 공통 Gemini 실험 클라이언트로 대체했습니다. 일부 기존 감사 메타의 backend=genos는 실제 공급자가 아니며 provider binding과 원응답 모델이 정본입니다.\n\n'
    header += '## 전체 사용량\n' + block(measured)
    header += '\n## 원시 기록 읽기\n\n아래 system/user/스키마/응답 텍스트는 생략 없는 실제 값입니다. 이미지 base64만 MD에서 제외하고 정확한 요청 JSON과 이미지 파일을 연결했습니다. 인증 헤더/키는 기록하지 않았습니다.\n'
    content = header + ''.join(sections.values())
    content += '\n## 이미지 근거 — 동일 바이트는 한 번 표시\n\n'
    for h, path in images.items(): content += f'### {h[:12]}\n\n![실제 입력 {h[:12]}]({path})\n\n'
    output = ADR / 'GEMINI_INPUT_OUTPUT_AUDIT.md'; output.write_text(content)
    m = read(ADR / '실험/manifest.json')
    for q, outcome in zip(m['questions'], result['cases']):
        cid = q['case_id']
        text = f"# 질문 {q['number']:03d} — {cid}\n\n## 1. 실행 메타\n\nrun-001 / v32 / 실제 Gemini / 텍스트 exact, 이미지 링크 / 시작 timestamp {outcome['started_at']}\n"
        text += '\n## 2. 사용자 질문 원문\n\n성능은 어떤가 토큰은\n'
        text += '\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n' + block(outcome['expected_parents'])
        text += '\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\n해당 없음. 구조화 검토이며 검색은 없다. 원문은 아래 코드 입력 절, 실제 모델 입력은 호출별 user 참조.\n'
        text += '\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n' + sections[cid]
        text += '\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n위 모든 호출에 실제 VLM 검수·텍스트 범위·부모 선택·repair를 포함했다. v31 baseline은 ADR0434/gemini 결과를 변경 없이 상속했으며 재호출하지 않았다.\n'
        text += '\n## 7. 채점 호출과 반복 판정\n\n별도 모델 judge 없음. 독립 정답으로 직접 부모 exact 비교. 제품 호출 완료 후 검사. 반복1회·다수결 없음.\n'
        text += '\n## 8. 사례 최종 판정\n' + block({k: outcome.get(k) for k in ['status', 'final_correct', 'pass', 'false_visual_approval', 'source_unchanged', 'cache_calls', 'replay_identical', 'error']})
        (ADR / '실험' / q['file']).write_text(text)
    print(json.dumps({'report': str(output), 'totals': measured, 'comparison': {k: v for k, v in comparison.items() if k != 'baseline'}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
