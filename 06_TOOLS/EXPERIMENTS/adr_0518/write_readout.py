"""Present existing measured results. No model calls or source re-selection."""
from pathlib import Path
import json,html,statistics,collections,csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop'
O=R/'07_DOCS/REFERENCE/REPORTS/LEGAL_SEARCH_FINAL_REVIEW_20260922'
def esc(x):return html.escape(str(x),quote=True)
def main():
 O.mkdir(parents=True,exist_ok=True)
 s=json.loads((A/'artifacts/summary.json').read_text());rows=s['by_case'];t=s['totals']
 questions={c['case_id']:c['question'] for c in json.loads((A/'product-cases.json').read_text())['cases']}
 pairs=[r for r in rows if not r['error'] and not r['baseline_error']]
 with (O/'comparison.csv').open('w',newline='') as f:
  cols=['case_id','baseline_count','final_count','gold_baseline','gold_final','gold_total','removed_count','added_count','relation_count','selection_seconds','full_chain_composed_seconds','error']
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
 font_manager.fontManager.addfont('/mnt/c/Windows/Fonts/malgun.ttf');plt.rcParams['font.family']='Malgun Gothic';plt.rcParams['axes.unicode_minus']=False
 fig,ax=plt.subplots(figsize=(11.5,6));fig.subplots_adjust(top=.78,bottom=.21,left=.08,right=.98)
 before=collections.Counter(r['baseline_count'] for r in pairs);after=collections.Counter(r['final_count'] for r in pairs)
 xs=list(range(1,max(max(before),max(after))+1));ax.bar([x-.2 for x in xs],[before[x] for x in xs],width=.39,color='#a6b3be',label='기존 최종 선택');ax.bar([x+.2 for x in xs],[after[x] for x in xs],width=.39,color='#2c829a',label='원문 재검토 후')
 ax.set_xticks(xs);ax.set_xlabel('선택 조항 수 (개)');ax.set_ylabel('문항 수');ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
 ax.spines[['top','right']].set_visible(False);ax.legend(frameon=False)
 fig.text(.08,.94,'최종 선택을 다시 검토한 뒤의 조항 수',fontsize=21)
 fig.text(.08,.875,f'양쪽 정상 처리 {len(pairs)}문항 비교  |  평균 {t["comparable_baseline_mean"]:.2f} → {t["comparable_candidate_mean"]:.2f}개',fontsize=13)
 fig.text(.08,.095,'조항 개수 목표·5개 제한 없음. 오류 문항을 줄어든 조항으로 계산하지 않았습니다.',fontsize=10,color='#485866')
 fig.text(.08,.05,'공개 고정61문항 · Gemma 외부 실험 · 최종 답변 생성/정확도 미측정 · MAIN 미반영',fontsize=10,color='#485866')
 fig.savefig(O/'article-count-comparison.png',dpi=180);fig.savefig(O/'article-count-comparison.svg');plt.close(fig)
 labels={'APPLIES_MUTATIS_MUTANDIS':'준용','SPECIFIES_DELEGATED_CASES_OF':'위임 사항 구체화','CITES':'인용','DELEGATES_TO':'위임'}
 parts=[];examples=[]
 for r in rows:
  cid=r['case_id'];out=json.loads((A/'artifacts/run-002'/cid/'result.json').read_text());app=out.get('source_appendix',{})
  numbers={c['source_id']:i+1 for i,c in enumerate(app.get('selected_sources',[]))}
  cards=[]
  for c in app.get('selected_sources',[]):
   cards.append(f'<li><strong>{esc(c["document_name"])} · {esc(c["heading"])}</strong><p>{esc(c["reason"])}</p></li>')
  grouped={}
  for e in app.get('relations',[]):grouped.setdefault((e['from_source_id'],e['to_source_id'],e['predicate']),[]).append(e)
  relations=[]
  for (src,dst,pred),es in grouped.items():
   # Preserve every distinct original witness and native locator in a collapsible list.
   witnesses=[];seen=set()
   for e in es:
    key=(e['witness_sha256'],e.get('locator'))
    if key in seen:continue
    seen.add(key)
    witnesses.append(f'<div class="witness"><div>참조 표기: {esc(e.get("locator"))} · 시작 위치: {esc(" / ".join(e.get("source_unit_path",[])))}</div><blockquote>{esc(e["witness"])}</blockquote></div>')
   kind=labels.get(pred,'명시 참조')
   relations.append(f'<details class="relation"><summary>[{numbers[src]}] → [{numbers[dst]}] · {kind} · 근거 문장 {len(witnesses)}개</summary>{"".join(witnesses)}</details>')
   if pred=='APPLIES_MUTATIS_MUTANDIS' and src!=dst:examples.append((cid,numbers[src],numbers[dst],es[0]))
  error=f'<p class="error">재검토 실패: {esc(r["error"]["type"])}. 성공적으로 0개를 선택한 결과가 아닙니다.</p>' if r['error'] else ''
  relation_html=''.join(relations) or '<p>선택 조항 사이에서 원문으로 검증한 명시 관계를 확인하지 못했습니다.</p>'
  parts.append(f'<details class="case" id="{esc(cid)}"><summary><b>{esc(cid)}</b> · {r["baseline_count"]} → {r["final_count"]}조항 · 평가 원문 {r["gold_final"]}/{r["gold_total"]}</summary><h2>{esc(questions[cid])}</h2>{error}<h3>선택 출처</h3><ol>{"".join(cards)}</ol><h3>조문 사이의 관계</h3>{relation_html}<p class="muted">원문 문구·좌표 확인 / 질문에 대한 법적 적용성 미확정. 답변 생성 전 산출물이며 실제 답변 인용 여부는 미검증.</p></details>')
 page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>최종 출처와 조문 관계 검토</title><style>body{font:16px/1.65 system-ui,sans-serif;margin:36px auto;max-width:1050px;padding:0 20px;color:#203443;background:#f9fbfc}h1{font-size:28px}h2{font-size:18px}h3{font-size:16px}summary{cursor:pointer;padding:12px 0}.case{background:white;border:1px solid #d5e0e6;border-radius:8px;padding:4px 22px;margin:14px 0}.relation{border-top:1px solid #dde4e8}blockquote{white-space:pre-wrap;margin:10px 0 16px;padding:12px 16px;background:#eef5f8;border-left:3px solid #2c829a}.muted{font-size:13px;color:#526a79}.error{color:#ac3e32}li{padding:6px}li p{margin:2px 0;color:#506879}.witness{padding:8px 0}img{max-width:100%}</style><h1>최종 출처와 조문 관계 검토</h1><p>개수 목표 없이 기존 최종 선택을 원문으로 재검토한 실험입니다. 문항을 펼치면 선택 출처, 조문 사이의 방향, 실제 관계 문장을 볼 수 있습니다.</p><p class="muted">공개61문항 · Gemma · 실제 답변 작성 전 검토용 산출물 · MAIN/GENOS 미반영. 이 화면의 평가 원문 점수는 답변 정확도가 아닙니다.</p><img src="article-count-comparison.png" alt="기존과 재검토 후 조항 수 분포">'''+''.join(parts)+'</html>'
 (O/'reviewed-sources.html').write_text(page)
 example=examples[0] if examples else None
 (O/'relation-example.json').write_text(json.dumps(example,ensure_ascii=False,indent=2)+'\n')
 text=f'''# 최종 선택 원문 재검토 결과

사용자 최신 지시대로 5개 목표·개수 제한을 제거했다. 이미 선택된 원문에서 출발해 불필요·중복이 확인될 때만 제거하고, 필요한 원문은 개수와 관계유형에 무관하게 유지하는 격리 후보를 구현했다.

| 항목 | 결과 |
|---|---:|
| 전체 시도 | {t['cases']}문항 |
| 신규 호출 오류 | {t['error_cases']}문항 |
| 양쪽 정상 처리 비교 | {len(pairs)}문항 |
| 같은 정상 문항의 평균 조항 수 | {t['comparable_baseline_mean']:.2f} → {t['comparable_candidate_mean']:.2f} |
| 전체 필수 원문 유지 | 80/90 → {t['gold_final']}/90 |
| 새로 회복 / 기존 보존 원문 손실 | {t['gold_gained']} / {t['gold_lost']} |
| 전체 후보 평균(오류0 포함, 별도 지표) | 6.11 → {t['final_count_mean']:.2f} |
| 추가 재검토 p50 / p95 | {t['selection_p50']:.1f} / {t['selection_p95']:.1f}초 |
| 과거 회수+과거 선별+이번 재검토 합산 p95 | {t['full_chain_composed_p95']:.1f}초 |
| 모델 호출 / 비용 | {t['physical_calls']}회 / ${t['cost_usd']:.4f} |

![분포 비교](article-count-comparison.png)

[문항별 출처·관계 화면](reviewed-sources.html), [비교 CSV](comparison.csv).

기존 출력 코드 `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`의 render → _sources → _tier_sources 경로는 source-tiers-v4 source_bundle의 CORE/SUPPLEMENTAL을 법령명·좌표·발췌·선택 이유로 표시한다. source_bundle 없는 경로는 claims의 evidence_ids가 있으면 실제 사용된 문맥만 표시한다. 따라서 현재 출처 표시는 존재하지만, v4/v5 선택 출처 전체가 답변에서 실제 인용됐다는 뜻은 아니다. 로컬 표시 계약4개가 통과했으며 GENOS 현장 확인은 하지 않았다.

이번 후보는 선택 조항 사이의 참조 원문과 해시, 두 끝점, 방향을 확인해 관계 목록을 만든다. 같은 조문 쌍·유형은 화면에서 묶고 서로 다른 원문 문장은 보존했다. 네이티브 참조 역할은 원문의 단서이며 법적 적용 승인으로 표시하지 않는다. 질문에 적용되는지 평가하지 않은 관계는 그대로 미확정이다. 확정 못한 관계는 숨겨 정답처럼 바꾸지 않는다.

후보 계약10개, 기존 출처 렌더링 계약4개 통과. 실행 시작 시 scoped transport 초기화 실패가 있었고 외부 호출0회인 run-001을 보존했다. 실제 모델 평가는 run-002다. 설정·기준·선별 알고리즘은 실제 호출 전에 동결했으며 비교 도중 튜닝하지 않았다.

사전 기준 통과: **{s['criteria_met']}**. 인샘플 고정61문항이며 최종답변 생성·정확도·독립 평가·GENOS 성능은 미측정이다. 합산시간은 서로 다른 실행의 시간을 더한 값이며 새로운 실제 종단시간이 아니다. 새 출처·관계 표시는 실험 산출물에 연결했고 운영 API·활성 MAIN에는 반영하지 않았다.

[ADR 기록](../../../../04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop/README.md) · [문항별 원본](../../../../04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop/실험/README.md)
'''
 (O/'README.md').write_text(text)
 print(json.dumps({'output':str(O),'comparable':len(pairs),'relation_example_case':example[0] if example else None},ensure_ascii=False))
if __name__=='__main__':main()
