"""Render completed root-bundle results; no retrieval or model calls."""
from pathlib import Path
import csv
import html
import json
import statistics

R = Path(__file__).resolve().parents[3]
A = R / '04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations'
D = R / '07_DOCS/REFERENCE/REPORTS/LEGAL_SEARCH_ROOT_BUNDLES_20260922'


def read(path):
    return json.loads(path.read_text())


def esc(value):
    return html.escape(str(value), quote=True)


CSS = '''body{font:16px/1.65 system-ui,sans-serif;max-width:1240px;margin:40px auto;padding:0 24px;color:#182331;background:#f8fafc}h1,h2{line-height:1.3}table{width:100%;border-collapse:collapse;background:white}td,th{text-align:left;padding:10px;border-bottom:1px solid #dce3eb;vertical-align:top}th{background:#e9eff6}a{color:#175bbb}small{color:#52657a}details{background:white;padding:14px;margin:12px 0;border:1px solid #dce3eb;border-radius:8px}summary{cursor:pointer;font-weight:600}.notice{background:#fff3d8;padding:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}input{font:inherit;padding:10px;width:95%;margin:10px 0}.tag{padding:2px 7px;background:#e4eefc;border-radius:5px}blockquote{border-left:3px solid #879eb9;margin-left:0;padding-left:12px}'''


def page(title, body):
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + esc(title) + '</title><style>' + CSS + '</style><body>' + body + '</body></html>'


def main():
    summary = read(A / 'artifacts/summary.json')
    rows = summary['by_case']
    totals = summary['totals']
    questions = {x['case_id']: x['question'] for x in read(A / 'product-cases.json')['cases']}
    D.mkdir(parents=True, exist_ok=True)
    (D / 'cases').mkdir(exist_ok=True)
    index_rows = []
    for row in rows:
        cid = row['case_id']
        out = read(A / 'artifacts/run-001' / cid / 'result.json')
        sources = out.get('source_appendix', {}).get('selected_sources', [])
        lookup = {x['source_id']: x for x in sources}
        roots = out.get('selected_root_ids', [])
        labels = {sid: 'R' + str(i + 1) for i, sid in enumerate(roots)}
        def name(sid):
            s = lookup.get(sid, {})
            return s.get('document_name', '') + ' ' + s.get('heading', sid)
        body = '<p><a href="../index.html">← 전체 문항</a></p><h1>' + esc(cid) + '</h1><p>' + esc(questions[cid]) + '</p>'
        body += '<p class="notice">답변 작성 전 준비한 출처입니다. 실제 답변 생성·인용 검증은 실행하지 않았습니다. 연결 관계 문구는 원문과 대조했으며, 질문에 대한 법적 적용 여부는 별도 판단이 필요합니다.</p>'
        body += f'<p>시작점 후보 {row["root_candidate_count"]}개 → 선택 <b>{len(roots)}개</b> · 연결 원문 <b>{row["protected_linked_count"]}개</b> · 전체 <b>{len(out["final_ids"])}개</b> · 원래 풀에서 제외 {row["orphan_branch_removed_count"]}개</p>'
        if out.get('error'):
            body += '<p class="notice">DEGRADED_PRESERVED: 선별 실패로 기존 원문 풀을 보존했습니다. 정상적인 시작점 선택 결과가 아닙니다.</p>'
        body += '<h2>선택한 시작점</h2><table><tr><th>시작점</th><th>조문</th><th>선택 사유</th><th>연결 묶음 규모</th></tr>'
        owners = out.get('selected_root_owners', {})
        for sid in roots:
            size = sum(sid in values for values in owners.values())
            body += '<tr><td>' + labels[sid] + '</td><td>' + esc(name(sid)) + '</td><td>' + esc(lookup[sid]['reason']) + '</td><td>' + str(size) + '개 (공유 조항 포함)</td></tr>'
        body += '</table><h2>보존한 연결 조항</h2><p>각 조항의 시작점 열에 하나라도 채택된 시작점이 남으면 보존합니다. 다른 시작점의 연결 조항으로 살아남은 미선택 시작점도 포함합니다.</p><table><tr><th>조문</th><th>연결된 채택 시작점</th><th>구분</th></tr>'
        for sid in out['final_ids']:
            if sid in roots:
                continue
            values = owners.get(sid, [])
            label = ', '.join(labels[v] for v in values)
            status = '공유' if len(values) > 1 else '연결'
            if sid in out.get('root_rejected_but_protected_ids', []):
                status += ' · 시작점으로는 미선택'
            if out.get('error'):
                status = '오류 시 원문 보존'
            body += '<tr><td>' + esc(name(sid)) + '</td><td>' + esc(label) + '</td><td>' + status + '</td></tr>'
        body += '</table><h2>관계와 원문 근거</h2><p>아래 화살표는 원문의 참조 방향입니다. 검색 과정의 역참조 회수 방향과 다를 수 있습니다.</p>'
        predicates = {'CITES': '인용', 'APPLIES_MUTATIS_MUTANDIS': '준용', 'SPECIFIES_DELEGATED_CASES_OF': '위임 사항 구체화'}
        for rel in out.get('source_appendix', {}).get('relations', []):
            body += '<details><summary>' + esc(name(rel['from_source_id'])) + ' → ' + esc(predicates.get(rel['predicate'], rel['predicate'])) + ' → ' + esc(name(rel['to_source_id'])) + '</summary><blockquote>' + esc(rel['witness']) + '</blockquote><small>원문 문구 일치 확인 · 적용 여부 미판단 · ' + esc(rel['reference_id']) + '</small></details>'
        body += '<h2>미회수 연결</h2><p>선택 시작점에서 도달하지만 이번 원문 풀에 없는 연결 대상 ' + str(row['unacquired_reachable_count']) + '개는 원문 확보 완료로 계산하지 않았습니다.</p>'
        body += '<details><summary>전체 원문 — 준비한 패킷</summary>'
        for packet in out.get('final_packets', []):
            for evidence in packet['evidence']:
                sid = evidence['source_id']
                original = '\n'.join(span['text'] for span in evidence['spans'])
                body += '<details><summary>' + esc(name(sid)) + '</summary><pre>' + esc(original) + '</pre></details>'
        body += '</details>'
        (D / 'cases' / (cid + '.html')).write_text(page(cid + ' 출처 묶음', body))
        index_rows.append(f'<tr><td><a href="cases/{cid}.html">{cid}</a></td><td>{esc(questions[cid])}</td><td>{len(roots)}</td><td>{row["protected_linked_count"]}</td><td>{row["final_count"]}</td><td>{row["gold_final"]}/{row["gold_total"]}</td><td>{"오류·원문 보존" if row["error"] else "완료"}</td></tr>')
    body = '<h1>시작점 선택과 연결 조항 보존</h1><p>시작점 선택 → 해당 연결 묶음 보존. 시작점 제외 → 그 시작점에만 연결된 가지 제외. 공유 조항은 남은 시작점이 있으면 유지합니다. 개수 제한은 없습니다.</p>'
    body += f'<p>공개 61문항 · 필수 원문 {totals["gold_final"]}/90 · 평균 시작점 {totals["selected_roots_mean"]:.2f}개 + 연결 {totals["protected_linked_mean"]:.2f}개 · 연결 보호 손실 {totals["protected_loss"]}개 · 오류 {totals["error_cases"]}건</p>'
    body += '<p class="notice">실험 후보 결과입니다. MAIN·GENOS 미반영, 실제 최종답변 미생성. 원래 회수된 풀과 기록 경로 안에서의 연결 보존이며, 전체 코퍼스의 연결 전수회수 결과가 아닙니다.</p><img src="article-distribution.svg" alt="시작점과 연결 조항 수 분포" style="width:100%"><h2>문항별 출처와 관계</h2><table><tr><th>문항</th><th>질문</th><th>시작점</th><th>연결</th><th>전체</th><th>필수 원문</th><th>상태</th></tr>' + ''.join(index_rows) + '</table>'
    (D / 'index.html').write_text(page('시작점과 연결 조항 보존 실험', body))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname='/mnt/c/Windows/Fonts/malgun.ttf')
    plt.rcParams['axes.unicode_minus'] = False
    fig, axes = plt.subplots(2, 1, figsize=(16, 9), gridspec_kw={'height_ratios': [1, 2]})
    x = list(range(len(rows)))
    selected = [r['root_selected_count'] for r in rows]
    linked = [r['protected_linked_count'] for r in rows]
    axes[0].bar(x, selected, color='#2269b5')
    axes[0].set_title('Gemma가 선택한 시작점 수 — 개수 제한 없음', fontproperties=font)
    axes[1].bar(x, selected, color='#2269b5', label='선택 시작점')
    axes[1].bar(x, linked, bottom=selected, color='#91aecb', label='따라온 연결 원문')
    axes[1].plot(x, [r['acquired_count'] for r in rows], color='#d68d37', linewidth=1.2, label='원래 회수한 전체 풀')
    axes[1].set_title('최종 보존 묶음 — 공유·순환 연결 중복 제거', fontproperties=font)
    axes[1].legend(prop=font)
    for ax in axes:
        ax.set_ylabel('조항 수', fontproperties=font)
        ax.set_xticks(x)
        ax.set_xticklabels([r['case_id'] for r in rows], rotation=90, fontsize=7)
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle(f'공개 61문항 · 필수 원문 {totals["gold_final"]}/90 · 연결 보호 손실 {totals["protected_loss"]}개', fontproperties=font, fontsize=16)
    fig.tight_layout()
    fig.savefig(D / 'article-distribution.png', dpi=160)
    fig.savefig(D / 'article-distribution.svg')
    plt.close(fig)
    columns = ['case_id', 'acquired_count', 'root_candidate_count', 'root_selected_count', 'protected_linked_count', 'final_count', 'gold_final', 'gold_total', 'protected_loss', 'unacquired_reachable_count', 'composed_seconds']
    with (D / 'comparison.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    text = f'''# 시작점 선택과 연결 원문 보존

시작점만 모델이 선택하고, 채택 시작점에서 도달하는 회수 완료 원문은 모두 보존한다. 제외된 시작점의 배타적 연결 가지는 제외하고, 다른 채택 시작점과 공유하는 조항은 유지한다. 개수 목표는 없다.

|지표|결과|
|---|---:|
|공개 문항|61|
|원래 회수 풀의 필수 원문|90/90|
|이전 개별 선별의 필수 원문|72/90|
|이번 묶음 선별의 필수 원문|{totals['gold_final']}/90|
|평균 선택 시작점|{totals['selected_roots_mean']:.2f}개|
|평균 연결 조항|{totals['protected_linked_mean']:.2f}개|
|평균 최종 묶음|{totals['final_count_mean']:.2f}개|
|선택 시작점의 연결 원문 손실|{totals['protected_loss']}개|
|오류|{totals['error_cases']}문항|
|과거 회수 시간 + 이번 처리 p95|{totals['composed_p95']:.2f}초|

[문항별 시작점·연결 조항·관계 원문](index.html) · [분포 그래프](article-distribution.png) · [CSV](comparison.csv)

연결 수는 기록된 역참조와 재귀 경로까지 따라간 결과다. 시작점 수가 작아도 묶음 전체는 크게 남을 수 있다. 원래 풀 밖에서 도달하는 조항은 미회수로 별도 기록했으며, 이번에 신규 코퍼스 전수 회수를 실행한 것은 아니다.

출처 목록은 답변 작성 전에 준비한 근거다. 실제 답변 생성·인용 검증은 실행하지 않았다. 관계 문구의 원문 일치와 법적 적용 판단을 구분한다. 과거 회수 시간과 이번 처리 시간의 합은 실제 신규 종단 측정값이 아니다.

노출된 공개 61문항 실험으로 in_sample=true, decision_eligible=false. MAIN·GENOS 미반영.
'''
    (D / 'README.md').write_text(text)
    print(json.dumps({'directory': str(D), 'cases': len(rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
