"""Render run.py output as terms.csv (one row per headword) and REPORT.md.

usage: report.py DIR
"""
import collections, csv, json, re, sys
from pathlib import Path

NAMES = {'econedu': '경제교육', 'nts': '국세청', 'krx': '한국거래소'}
LISTS = ('법령용어목록', '지식용어목록', '일상용어목록')


def short_latin(text):
    """Latin/number abbreviations of at most 3 characters (AP, CU, LP) are ambiguous."""
    return bool(re.fullmatch(r'[A-Za-z0-9&.]{1,3}', text.replace(' ', '')))


def main():
    out = Path(sys.argv[1])
    rows = [json.loads(line) for line in open(out / 'rows.jsonl', encoding='utf-8')]
    summary = json.loads((out / 'summary.json').read_text())
    for r in rows:
        r['abbr_hit'] = bool(r['matched_surfaces']) and all(short_latin(m['text']) for m in r['matched_surfaces'])
        r['abbr_moleg'] = bool(r['moleg']) and all(short_latin(m['surface']) for m in r['moleg'])

    with open(out / 'terms.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['소스', '표제어', '분류', '출현 조문 수', '출현 문서 수', '본문 일치 표기', '약어 주의(본문)',
                    '예시 문서', '예시 위치', '예시 문맥', '법제처 법령용어목록', '법제처 지식용어목록', '법제처 일상용어목록',
                    '법제처 일치 표기', '약어 주의(법제처)', '옛 분류(글자 매칭)', 'ID'])
        for r in rows:
            e = r['examples'][0] if r['examples'] else {}
            w.writerow([NAMES[r['source']], r['label'], r['class'], r['articles'], r['documents'],
                        ' / '.join(m['text'] for m in r['matched_surfaces']), 'Y' if r['abbr_hit'] else '',
                        e.get('document', ''), e.get('heading', ''), e.get('snippet', ''),
                        *['Y' if name in r['moleg_lists'] else '' for name in LISTS],
                        ' / '.join(sorted({m['surface'] for m in r['moleg']})), 'Y' if r['abbr_moleg'] else '',
                        r['old_class'], r['id']])

    lines = ['# 공개 용어사전 3종 × 본문 159문서 × 법제처 목록 대조 (2026-09-18)', '',
             f"본문: navigation-source-20260918-morph-v1 세대, 조문 {summary['inputs']['articles']:,}개 / 문서 {summary['inputs']['documents']}개.",
             '판정 규칙: 표기가 조문 안에서 Kiwi 명사 형태소 경계에 맞게 나와야 본문용어(현행 MAIN 매칭 규칙과 같음).',
             '글자로만 포함된 경우(형태소 경계 불일치)는 참고용어. 법제처 대조는 공백 무시 동일 표기만 본다.',
             '로컬 법제처 원장(437,778건)에는 한자·뜻이 비어 있어 의미 동일성은 판정하지 않았다. LLM 호출 0회.', '',
             '## 요약', '',
             '| 소스 | 표제어 | 본문용어 | 참고용어 | 약어만으로 본문 연결(주의) | 법제처 동일 표기 있음 | 법령용어목록 | 지식용어목록 | 일상용어목록 | 법제처 없음 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for source, name in NAMES.items():
        s = summary['by_source'][source]
        rs = [r for r in rows if r['source'] == source]
        lines.append(f"| {name} | {s['terms']:,} | {s['본문용어']:,} | {s['참고용어']:,} | {sum(r['abbr_hit'] for r in rs)} | "
                     f"{s['moleg_any']:,} | {s['moleg_by_list']['법령용어목록']:,} | {s['moleg_by_list']['지식용어목록']:,} | "
                     f"{s['moleg_by_list']['일상용어목록']:,} | {s['moleg_none']:,} |")
    lines += ['', '## 분류 × 법제처', '', '| 소스 | 본문용어·법제처 있음 | 본문용어·법제처 없음 | 참고용어·법제처 있음 | 참고용어·법제처 없음 |', '|---|---:|---:|---:|---:|']
    for source, name in NAMES.items():
        c = summary['by_source'][source]['class_x_moleg']
        lines.append(f"| {name} | {c.get('본문용어/법제처有', 0):,} | {c.get('본문용어/법제처無', 0):,} | "
                     f"{c.get('참고용어/법제처有', 0):,} | {c.get('참고용어/법제처無', 0):,} |")
    lines += ['', '## 옛 분류(boundary-20260914-v3, 글자 매칭)와 비교', '', '| 소스 | 변화 | 건수 |', '|---|---|---:|']
    for source, name in NAMES.items():
        for k, v in sorted(summary['by_source'][source]['old_vs_new'].items()):
            lines.append(f'| {name} | {k} | {v:,} |')

    def examples(title, pick, n=8):
        lines.extend(['', '## ' + title, '', '| 소스 | 표제어 | 조문 수 | 문서 | 문맥 | 법제처 |', '|---|---|---:|---|---|---|'])
        for r in pick[:n]:
            e = r['examples'][0] if r['examples'] else {}
            snip = (e.get('snippet', '') or ' / '.join(r['literal_only_surfaces'])).replace('|', '¦')[:80]
            lines.append(f"| {NAMES[r['source']]} | {r['label']} | {r['articles']} | {e.get('document', '')[:24]} | {snip} | {', '.join(r['moleg_lists']) or '-'} |")

    by = lambda f: sorted((r for r in rows if f(r)), key=lambda r: -r['articles'])
    examples('본문용어인데 법제처에 같은 표기가 없는 것 (많이 나오는 순)', by(lambda r: r['class'] == '본문용어' and not r['moleg_lists'] and not r['abbr_hit']), 15)
    examples('약어만으로 본문에 연결된 것 (동음이의 확인 필요)', by(lambda r: r['abbr_hit']), 15)
    examples('글자로는 있지만 형태소 경계가 안 맞아 참고용어가 된 것',
             [r for r in rows if r['class'] == '참고용어' and r['literal_only_surfaces']], 12)
    (out / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
