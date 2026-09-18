"""Read saved provider requests/responses into one complete human-readable Markdown."""
from pathlib import Path
from collections import Counter
import base64
import copy
import hashlib
import json
import statistics

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0434-basic-first-gemini-audit'
ART = ADR / 'artifacts'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def block(value, lang='json'):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return '\n```' + lang + '\n' + text + '\n```\n'


def link(path, label=None):
    return f'[{label or path.name}](<{path.resolve()}>)'


def flat_parents(tree):
    out = {}
    def visit(nodes, parent=None):
        for n in nodes:
            out[str(n['block'])] = parent
            visit(n['children'], n['block'])
    visit(tree['tree'])
    return out


def main():
    report = read(ART / 'results.json')
    cases = read(ART / 'dataset/cases.json')
    stats = []; sections = {}; all_images = {}; rows = []
    for case, result in zip(cases, report['cases']):
        cid = case['case_id']; directory = ART / 'runs' / cid
        calls = []
        for d in sorted((directory / 'provider').glob('call-*')):
            req = read(d / 'request.json'); raw = read(d / 'response.json') if (d / 'response.json').exists() else {}
            text = req['contents'][0]['parts'][0]['text']; data = json.loads(text)
            u = raw.get('usageMetadata', {})
            modalities = {x['modality']: x['tokenCount'] for x in u.get('promptTokensDetails', [])}
            images = []
            for part in req['contents'][0]['parts']:
                if 'inlineData' not in part:
                    continue
                binary = base64.b64decode(part['inlineData']['data']); h = hashlib.sha256(binary).hexdigest()
                image_dir = ART / 'report-images'; image_dir.mkdir(exist_ok=True)
                p = image_dir / (h + '.png')
                if not p.exists():
                    p.write_bytes(binary)
                images.append(h); all_images[h] = p
            phase = d.name.split('-', 2)[2]
            usage = next((x for x in result['usage'] if x['phase'] == phase), {})
            row = dict(case=cid, call=int(d.name.split('-')[1]), phase=phase,
                       task=data.get('task'), pages=data.get('page_window'), input_chars=len(text),
                       source_snippet_chars=sum(len(x['text']) for x in data.get('source_blocks', [])),
                       field_chars={k: len(json.dumps(v, ensure_ascii=False)) for k, v in data.items()},
                       input_tokens=u.get('promptTokenCount'), output_tokens=u.get('candidatesTokenCount'),
                       thinking_tokens=u.get('thoughtsTokenCount', 0), cached_input_tokens=u.get('cachedContentTokenCount', 0),
                       text_tokens=modalities.get('TEXT'), image_tokens=modalities.get('IMAGE'),
                       finish=next(iter(raw.get('candidates', [])), {}).get('finishReason'),
                       seconds=usage.get('seconds'), image_hashes=images,
                       body_tail_in_text='모의자료끝' in text,
                       path=str(d.relative_to(ROOT)))
            calls.append((row, req, raw, data, d)); rows.append(row)
        def total(key):
            return sum(x[0].get(key) or 0 for x in calls)
        revisions = []
        for p in sorted(directory.glob('structure-recipe-runs/*/window-tree-*.json'), key=lambda p: int(p.stem.split('-')[-1])):
            parents = flat_parents(read(p))
            revisions.append({'revision': p.stem, 'parents': parents, 'matches_gold': parents == result['expected_parents'], 'path': str(p.relative_to(ROOT))})
        summary = dict(case=cid, calls=len(calls), input_tokens=total('input_tokens'), output_tokens=total('output_tokens'),
                       image_tokens=total('image_tokens'), text_tokens=total('text_tokens'), cached_input_tokens=total('cached_input_tokens'),
                       input_chars_max=max((x[0]['input_chars'] for x in calls), default=0),
                       image_occurrences=sum(len(x[0]['image_hashes']) for x in calls),
                       unique_images=len({h for x in calls for h in x[0]['image_hashes']}),
                       repair_calls=sum('-repair-' in x[0]['phase'] for x in calls),
                       full_source_chars=case['source_chars'], output_cutoffs=sum(x[0]['finish'] == 'MAX_TOKENS' for x in calls),
                       status=result['status'], passed=result['pass'], revisions=revisions)
        stats.append(summary)
        section = f'\n## {cid}\n\n'
        section += f"모의 PDF {case['pages']}쪽 / 원문 {case['source_chars']:,}자. {link(ROOT / case['pdf'], '원본 PDF')}\n\n"
        section += '### 실행 결과와 코드 오류\n' + block({k: v for k, v in result.items() if k not in {'usage', 'cached_meta'}})
        section += '### 수정 전후 실제 트리의 부모 관계\n\n블록 번호 → 직접 부모 블록 번호. null은 최상위입니다. 정답은 모델 호출 종료 후에만 대조했습니다.\n' + block(revisions)
        section += '### 입력 블록 전체와 초기 힌트\n\n아래 원문 전체는 코드 입력입니다. 실제 모델에 전달된 텍스트는 각 호출의 user 필드를 확인하세요.\n'
        section += block({'hints': case['hints'], 'blocks': read(ROOT / case['blocks'])})
        section += '### 호출별 입력·출력 전체\n\n'
        for row, req, raw, data, d in calls:
            section += f"#### 호출 {row['call']}: {row['phase']}\n\n"
            section += block(row)
            section += f"\n{link(d / 'request.json', '실제 전송 요청 JSON')} · {link(d / 'response.json', 'provider 원응답 JSON')}\n"
            section += '\n**System — 실제 전송 문자열 전체**\n' + block(req['systemInstruction']['parts'][0]['text'], 'text')
            section += '\n**User — 실제 전송 문자열 전체**\n' + block(req['contents'][0]['parts'][0]['text'], 'text')
            section += '\n**실제 전송 설정·스키마**\n' + block(req['generationConfig'])
            section += '\n**로컬 검증 스키마**\n' + block(read(d / 'validation-schema.json'))
            section += '\n**이미지 입력 — 전송 순서**\n\n'
            for n, h in enumerate(row['image_hashes'], 1):
                section += f"{n}. {link(all_images[h], '이미지 ' + h[:12])}\n"
            section += '\n**Provider 원응답 전체 — 출력 텍스트·종료 사유·사용량 포함**\n' + block(raw)
            if (d / 'output.json').exists():
                section += '\n**해석된 출력 JSON**\n' + block(read(d / 'output.json'))
            feedback = list(directory.glob('structure-recipe-runs/*/' + row['phase'] + '-feedback-input.json'))
            if feedback:
                feedback_data = read(feedback[0])
                section += '\n**코드가 반환한 오류와 직전 답변**\n' + block({k: feedback_data.get(k) for k in ('previous_answer', 'correction')})
        sections[cid] = section
    total = {k: sum(s[k] for s in stats) for k in ('calls', 'input_tokens', 'output_tokens', 'image_tokens', 'text_tokens', 'cached_input_tokens', 'image_occurrences', 'repair_calls', 'output_cutoffs')}
    total['unique_images'] = len(all_images)
    seconds = [r['seconds'] for r in rows if r['seconds'] is not None]
    total['call_seconds_p50'] = statistics.median(seconds) if seconds else None
    total['call_seconds_p95_observed'] = sorted(seconds)[max(0, int(len(seconds) * .95 + .999) - 1)] if seconds else None
    total['input_chars_max'] = max(r['input_chars'] for r in rows)
    total['output_tokens_max'] = max(r['output_tokens'] or 0 for r in rows)
    total['approval_retry_input_tokens'] = sum(r['input_tokens'] or 0 for r in rows if 'action-repair-' in r['phase'])
    total['last_saved_tree_correct'] = sum(bool(s['revisions'] and s['revisions'][-1]['matches_gold']) for s in stats)
    audit = {'totals': total, 'cases': stats, 'calls': rows}
    (ART / 'token-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    title = '# v31 basic-first — 실제 Gemini 입력·출력·토큰 감사\n\n'
    title += '2026-09-16 · ADR-0434 · gemini-3.1-flash-lite · run-001 · 합성 PDF 3건 · 운영 코드 변경 없음\n\n'
    title += f"**문제없지 않습니다.** 최종 성공 {sum(bool(s['passed']) for s in stats)}/3. 실제 {total['calls']}회 호출에서 입력 {total['input_tokens']:,}, 출력 {total['output_tokens']:,} 토큰을 사용했습니다. 출력 잘림은 {total['output_cutoffs']}회입니다.\n\n"
    title += f"**틀을 적용하는 코드 자체는 작동했습니다.** 마지막 저장 트리는 {total['last_saved_tree_correct']}/3에서 동결 정답과 일치합니다. wrong-parent는 두 번 수정한 뒤 `가. → 1. → 1)` 직접 부모 관계가 맞았습니다. 그러나 모두 최종 승인 처리에서 중단됐습니다. ‘트리 정답’과 ‘전체 흐름 완료’를 구분해야 합니다.\n\n"
    title += '앞서 확인한 224개 검사는 모의 응답 계약 검사였습니다. 이번 실제 Gemini 응답에서 드러난 긍정 의견 문제를 검증하지 못했으므로, 그 통과 수를 실모델 성공 근거로 사용할 수 없습니다.\n\n'
    title += '이 보고서는 v31 코드와 프롬프트를 동결한 뒤 실제 Gemini에 보낸 요청 및 받은 응답입니다. GENOS 내부 모델·실제 내규·PDF 파서는 시험하지 않았습니다. 이미지와 동일한 텍스트 블록을 함께 만든 모의 문서를 사용했습니다.\n\n'
    title += '## 한눈에 보는 결과\n\n| 사례 | 쪽 | 호출 | 입력 토큰 | 출력 토큰 | 이미지 입력 토큰 | 재시도 호출 | 최종 성공 |\n|---|---:|---:|---:|---:|---:|---:|---|\n'
    for case, s in zip(cases, stats):
        title += f"| {s['case']} | {case['pages']} | {s['calls']} | {s['input_tokens']:,} | {s['output_tokens']:,} | {s['image_tokens']:,} | {s['repair_calls']} | {'통과' if s['passed'] else '실패/보류'} |\n"
    title += '\n## 확인된 문제와 토큰 중복\n\n'
    title += '1. **정상 의견을 오류로 처리합니다.** clean-hierarchy 첫 응답은 “정확하게 인식됐다”는 긍정 의견 3개였습니다. 의견 판정은 모두 accept였고, 코드가 accept를 전부 미해결 issue로 만들었습니다. 뒤의 approve 응답 3개를 거부하여 정상 문서가 중단됐습니다. 이는 JSON 스키마 실패가 아니라 의미 계약의 결함입니다.\n'
    title += f"   이 결함으로 발생한 승인 재시도 6회에 입력 {total['approval_retry_input_tokens']:,}토큰을 추가로 사용했습니다. 최초 승인 요청은 포함하지 않은 값입니다.\n"
    title += '2. **동일 이미지·구조가 단계마다 반복됩니다.** VLM 의견 생성뿐 아니라 의견별 판정, 조치 선택, 범위 선택, 부모 선택도 vision=True입니다. 특히 여러 의견에 대해 같은 페이지를 별도로 전송합니다. 검수에 필요한 재전송과 불필요한 재시도를 구분해야 합니다.\n'
    title += f"3. 전체 입력 중 이미지 {total['image_tokens']:,}토큰, 텍스트 {total['text_tokens']:,}토큰입니다. 이미지 전달 {total['image_occurrences']}장 중 고유 바이트는 {total['unique_images']}장입니다. **중복 전송량 전체가 낭비라는 뜻은 아닙니다.** 원본/수정 bbox 재검수는 필요하지만 현재 의견별 분리는 중복을 키웁니다.\n"
    title += f"4. provider가 보고한 캐시 입력은 {total['cached_input_tokens']:,}토큰입니다. 이는 promptTokenCount에 포함된 부분이며 별도로 더하지 않았습니다. 입력 토큰 수를 실제 청구 금액으로 표현하지 않습니다.\n"
    title += f"5. 호출별 입력 JSON 최대 {total['input_chars_max']:,}자, 출력 최대 {total['output_tokens_max']:,}토큰입니다. 이번 실패를 16,384 출력 한도 초과로 설명할 근거는 없습니다.\n\n"
    title += '6. **판정 라벨과 이유가 모순됩니다.** wrong-parent 호출 4·10은 누락/잘못된 계층을 이유에서 인정하면서 decision=reject를 반환했습니다. 호출 2·9는 실제 트리에 없는 구조를 있다고 주장했습니다. 현재 검사는 허용 enum·근거 블록 존재를 확인할 뿐 이 의미 모순을 잡지 못합니다. 최종 조치가 일부를 다시 찾아 수정했으나, 판정 단계를 독립 검증으로 신뢰할 수 없습니다.\n\n'
    title += '7. 긴 본문 사례의 원문은 9,072자였고, 실제 source_blocks 접두부는 호출당 684자였습니다. 본문 끝 식별어는 텍스트 요청에 없었습니다. **본문 축약은 확인됐지만 이미지·구조 정보·지원 목록 반복은 남았습니다.** 6쪽 중 첫 1~3쪽 검수에서 중단됐으므로 전체 6쪽의 완료 비용은 측정하지 못했습니다.\n\n'
    title += '긴 본문 축약 여부, 실제 부모 관계 수정·재검수 결과, 세부 실패는 아래 사례별 기록을 확인하세요. 실패한 문서를 성공으로 저장하거나 MAIN에 반영하지 않았습니다.\n\n'
    title += '## 다음 수정에서 검증할 항목\n\n'
    title += '- 결함/불확실성/정상 관찰을 응답 계약에서 구분하고, 정상 관찰의 accept가 수정을 요구하지 않게 해야 합니다. “문제없으면 opinions=[]” 지시만으로 해결됐다고 판단하면 안 됩니다.\n'
    title += '- 의견별 판정에 같은 이미지 전체를 반복하지 않도록 묶음 판정이나 필요한 근거만 전달하는 방식을 별도 비교해야 합니다. 이미지 제거로 잘못된 승인이 늘지 않는지도 확인해야 합니다.\n'
    title += '- 번호 체계 수정 후 블록별 직접 부모가 정답과 맞는지, 정상 문서를 불필요하게 수정하지 않는지 실모델 회귀 검사를 포함해야 합니다.\n'
    title += '- 창 겹침과 전체 재검수 비용, 구조·지원 목록·visual_evidence 사이 중복을 단계별로 줄일 여지가 있습니다. 현재 보고서에서는 운영 코드나 동결한 프롬프트를 수정하지 않았습니다.\n\n'
    title += '## 이전 Gemini 결과와 구분\n\n'
    title += 'ADR-0385는 다른 코드와 공개 PDF 2건으로 7회 호출, 입력 235,901토큰·출력 927토큰, 최종 기준 0/2였습니다. VLM 승인 1/2와 최종 구조 정답을 혼동하면 안 됩니다. 이번 모의 문서는 다르므로 전후 절감률이나 품질 개선율을 계산하지 않습니다.\n\n'
    title += '## 읽는 방법과 재현 범위\n\n'
    title += '각 호출의 system, user, API 스키마, 로컬 검증 스키마, 원응답, 해석 결과를 생략 없이 담았습니다. 바이너리 이미지의 base64만 본문에서 제외하고 원본 JSON과 이미지 파일을 연결했습니다. 따라서 텍스트는 실제 값이며, 표시용으로 이미지를 뺀 본문 자체를 완전한 원시 HTTP 요청이라고 부르지 않습니다. 요청 JSON에는 실제 inlineData가 보존되어 있습니다. 인증 헤더·키는 기록하지 않았습니다.\n\n'
    title += 'Gemini의 JSON 전송·minimal thinking 설정은 공통 연구 클라이언트를 사용했습니다. GENOS 전송을 직접 호출한 것이 아닙니다. 구조 코드의 일부 저장 메타에 backend=genos가 남지만 실제 provider는 별도 binding과 원응답의 Gemini 모델로 확인합니다.\n\n'
    title += '### 전체 계측\n' + block(total)
    title += '\n### 호출별 토큰표\n\n| 사례/호출 | 작업 | 입력 | 출력 | 이미지 | 캐시 입력(입력에 포함) | 초 | 종료 |\n|---|---|---:|---:|---:|---:|---:|---|\n'
    for r in rows:
        title += f"| {r['case']}/{r['call']} | {r['task']} | {r['input_tokens']} | {r['output_tokens']} | {r['image_tokens']} | {r['cached_input_tokens']} | {r['seconds']} | {r['finish']} |\n"
    content = title + ''.join(sections.values())
    content += '\n## 이미지 근거 모음 — 동일 바이트는 한 번 표시\n\n'
    for h, p in all_images.items():
        content += f'### {h[:12]}\n\n![실제 모델 입력 이미지 {h[:12]}]({p})\n\n'
    output = ADR / 'GEMINI_INPUT_OUTPUT_AUDIT.md'
    output.write_text(content)
    for q, case in zip(read(ADR / '실험/manifest.json')['questions'], cases):
        cid = case['case_id']; result = next(r for r in report['cases'] if r['case_id'] == cid)
        text = f"# 질문 {q['number']:03d} — {cid}\n\n## 1. 실행 메타\n\nrun-001 / baseline, gemini / gemini-3.1-flash-lite / exact text; images linked. 실제 시작 Unix timestamp: {result['started_at']}.\n"
        text += '\n## 2. 사용자 질문 원문\n\n실제 돌리면 토큰낭비나 이상한거 없나? Gemini로 돌렸을 때 문제 없나? 입력 출력을 하나의 MD로 확인한다.\n'
        text += '\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n' + block(result['expected_parents'])
        text += '\n## 4. 제품 입력을 구성한 원값\n\n### 회수·탈락 단계 원장 — run·arm별\n\n해당 없음. 문서 구조화이며 검색은 없다.\n' + block(case)
        text += '\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n' + sections[cid]
        text += '\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n위 호출 순서 전체에 VLM·의견 판정·조치·수정·repair를 포함했다. baseline 모델 호출은 0회다.\n'
        text += '\n## 7. 채점 호출과 반복 판정\n\n별도 모델 채점 없음. 제품 호출 종료 후 동결된 블록별 직접 부모와 코드로 exact 비교, 반복·다수결 없음.\n'
        text += '\n## 8. 사례 최종 판정\n' + block({k: result[k] for k in ['baseline_correct', 'final_correct', 'pass', 'false_visual_approval', 'status']})
        text += '\n실패 유형: other: review contract / hierarchy correction. 구체적 원인은 위 코드 오류·원응답에 보존했다.\n'
        (ADR / '실험' / q['file']).write_text(text)
    print(json.dumps({'report': str(output), 'bytes': output.stat().st_size, 'totals': total}, ensure_ascii=False))


if __name__ == '__main__':
    main()
