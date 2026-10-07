"""Read-only descriptive plot of completed ADR-0517; no selection replay."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
SOURCE = ROOT / '04_EXPERIMENTS/ADR/ADR-0517-bounded-provenance-protocol/artifacts/summary.json'
raw = SOURCE.read_bytes()
data = json.loads(raw)
cases = data['by_case']
ok = [r for r in cases if not r['error']]
errors = [r for r in cases if r['error']]
complete = Counter(r['final_count'] for r in ok if r['gold_final'] == r['gold_total'])
missing = Counter(r['final_count'] for r in ok if r['gold_final'] != r['gold_total'])
counts = [r['final_count'] for r in ok]
summary = {
    'source': str(SOURCE.relative_to(ROOT)),
    'source_sha256': hashlib.sha256(raw).hexdigest(),
    'analysis': 'descriptive_only_no_new_model_call_or_top5_replay',
    'attempted_cases': len(cases), 'completed_selection_cases': len(ok),
    'error_cases': [r['case_id'] for r in errors],
    'success_mean': statistics.mean(counts), 'success_median': statistics.median(counts),
    'success_min': min(counts), 'success_max': max(counts),
    'success_at_most_5': sum(n <= 5 for n in counts),
    'success_between_4_and_6': sum(4 <= n <= 6 for n in counts),
    'all_gold_retained_success_cases': sum(complete.values()),
    'missing_gold_success_cases': sum(missing.values()),
    'annotated_gold_count_distribution': dict(sorted(Counter(r['gold_total'] for r in cases).items())),
    'original_metrics_all_61': data['totals'],
    'top5_replacement_effectiveness_measured': False,
    'in_sample': data['in_sample'], 'decision_eligible': data['decision_eligible'],
    'main_changed': False,
}
(OUT / 'statistics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
with (OUT / 'distribution.csv').open('w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['selected_articles', 'all_annotated_gold_retained', 'annotated_gold_missing', 'total_cases'])
    for n in range(1, max(counts)+1):
        w.writerow([n, complete[n], missing[n], complete[n]+missing[n]])
with (OUT / 'cases.csv').open('w', newline='') as f:
    w = csv.writer(f)
    fields = ['case_id', 'baseline_count', 'first_count', 'recovered_count', 'final_count', 'gold_total', 'gold_final', 'error']
    w.writerow(fields)
    w.writerows([[r[k] for k in fields] for r in cases])

font = Path('/mnt/c/Windows/Fonts/malgun.ttf')
if font.exists():
    font_manager.fontManager.addfont(str(font))
    plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font)).get_name()
plt.rcParams.update({'axes.unicode_minus': False, 'font.size': 11, 'svg.fonttype': 'path'})
fig, ax = plt.subplots(figsize=(12, 6.6), facecolor='#ffffff')
fig.subplots_adjust(left=.08, right=.97, bottom=.23, top=.77)
fig.text(.08, .94, '질문별 최종 선택 조항 수', fontsize=22, weight='bold', color='#182b3a')
fig.text(.08, .883, 'Gemma · ADR-0517 기존 결과  |  정상 처리 60문항 · API 오류 1문항 별도', fontsize=12, color='#465763')
fig.text(.08, .832, f'5개 이하 30/60문항 (50%)   ·   평균 {statistics.mean(counts):.2f}개   ·   중앙값 5.5개   ·   최대 18개', fontsize=12)
x = list(range(1, max(counts)+1))
ax.axvspan(4.5, 5.5, color='#ecf1f5', zorder=0)
ax.bar(x, [complete[n] for n in x], color='#357a9c', width=.72, label='평가에 지정된 필수 원문 모두 유지 (51문항)', zorder=3)
ax.bar(x, [missing[n] for n in x], bottom=[complete[n] for n in x], color='#de9367', width=.72, label='필수 원문 누락 (9문항)', zorder=3)
for n in x:
    total = complete[n]+missing[n]
    if total:
        ax.text(n, total+.25, str(total), ha='center', va='bottom', fontsize=11)
ax.set_xticks(x)
ax.set_yticks(range(0, 17, 2))
ax.set_ylim(0, 16)
ax.set_xlim(.3, 18.7)
ax.set_xlabel('최종 선택된 조항 수 (개)  ·  회색 영역: 새 목표 5개', labelpad=12)
ax.set_ylabel('문항 수', labelpad=12)
ax.grid(axis='y', color='#e3e9ed', zorder=0)
for side in ['top', 'right', 'left']:
    ax.spines[side].set_visible(False)
ax.spines['bottom'].set_color('#becbd4')
ax.tick_params(axis='both', length=0, pad=8)
fig.legend(*ax.get_legend_handles_labels(), loc='lower left', bbox_to_anchor=(.073, .093), frameon=False, ncol=2, fontsize=10)
fig.text(.08, .066, 'API 429 오류 1건은 0개 선택 성공으로 집계하지 않았습니다. 색상은 답변 정답률을 뜻하지 않습니다.', fontsize=10, color='#536471')
fig.text(.08, .028, '기존 결과의 분포이며, 5개 제한·교체 방식의 성능은 아직 측정하지 않았습니다. 공개 고정 61문항 · in-sample.', fontsize=10, color='#536471')
fig.savefig(OUT / 'article-count-distribution.png', dpi=180, facecolor='white')
fig.savefig(OUT / 'article-count-distribution.svg', facecolor='white')
plt.close(fig)
assert sum(complete.values()) + sum(missing.values()) + len(errors) == len(cases)
assert sum(counts) == 373
assert SOURCE.read_bytes() == raw
print(json.dumps(summary, ensure_ascii=False, indent=2))
