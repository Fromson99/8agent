"""Offline descriptive comparison only. Gold never enters the selection runner."""
from pathlib import Path
import json,hashlib,statistics,importlib.util,subprocess,sys
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations'
P=R/'04_EXPERIMENTS/ADR/ADR-0513-preserved-source-union'
B=R/'04_EXPERIMENTS/ADR/ADR-0518-five-source-replacement-loop'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0519/selection'
RUN='run-001'
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(8*1024*1024):h.update(b)
 return h.hexdigest()
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
def pct(v,p):return sorted(v)[round((len(v)-1)*p)]
def main():
 m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json');gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']}
 for p,hsh in read(A/'artifacts/frozen-design.json')['grader_only_hashes'].items():assert sha(R/p)==hsh
 spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 index=read(A/'artifacts'/RUN/'results.json');case_rows=[];records={'baseline':[],'selection':[]};stages_by_case={};outs={};parents={};usage=[]
 for cid in m['runs'][-1]['case_ids']:
  parent=read(P/'artifacts/run-001'/cid/'result.json');base=read(B/'artifacts/run-002'/cid/'result.json');out=read(R/index['cases'][cid]);outs[cid]=out;parents[cid]=parent
  assert sha(R/out['input_parent_path'])==out['input_parent_sha256']
  pool=parent['read_complete'];baseids=base['final_ids'];initial=out.get('selected_root_ids',[]);final=out['final_ids']
  assert set(initial)<=set(pool) and set(final)<=set(pool)
  hist=out.get('selection_history',[])
  # Independent reachability recomputation, without gold.
  adjacency={}
  for target,routes in parent['routes'].items():
   for route in routes:
    if route.get('anchor'):adjacency.setdefault(route['anchor'],set()).add(target)
  reachable=set(initial);queue=list(initial)
  for origin in queue:
   for target in sorted(adjacency.get(origin,set())):
    if target not in reachable:reachable.add(target);queue.append(target)
  expected=set(pool)&reachable
  if not out.get('error'):assert set(final)==expected,(cid,'root bundle preservation or exclusive-branch removal failed')
  round1=hist[1]['source_ids'] if len(hist)>1 else []
  round2=hist[2]['source_ids'] if len(hist)>2 else round1
  originals={e['evidence_id']:e for p in parent['packets'] for e in p['evidence']}
  sent={e['evidence_id']:e for p in out.get('final_packets',[]) for e in p['evidence']}
  assert sent=={k:v for k,v in originals.items() if v['source_id'] in final}
  assert all(p['delivery_status']=='PREPARED_NOT_SENT' for p in out.get('final_packets',[]))
  coords={e['source_id']:{'doc_id':e['document_id'],'node':int(e['unit_id'])} for e in parent['evidence']}
  reverse_coords={h.key(v):k for k,v in coords.items()}
  golden=gold[cid]['decisive_source_ids'];g=h.ordered(coords[s] for s in golden)
  for arm in records:
   prev=[];stages=[];sets={'acquired':pool,'root_candidates':out.get('root_ids',[]),'root_selection':initial,'bundle_expansion':final,'final_pool':baseids if arm=='baseline' else final}
   for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
    stage_id=plan['stage_id'];after=h.ordered(coords[s] for s in sets[stage_id]);bk={h.key(x) for x in prev};ak={h.key(x) for x in after};discarded=[x for x in prev if h.key(x) not in ak]
    detail={}
    if stage_id.startswith('replace_'):
     i=int(stage_id[-1]);detail=hist[i].get('discard_reasons',{}) if len(hist)>i else {}
    reason='inherited_parent_selection' if arm=='baseline' else 'root_candidate_view_only' if stage_id=='root_candidates' else 'root_not_selected' if stage_id=='root_selection' else 'no_selected_root_reaches_source'
    reasons={h.key(x):detail.get(reverse_coords[h.key(x)],reason) for x in discarded}
    st=h.stage(stage_id,plan['kind'],plan['parent_stage_ids'],prev,[x for x in after if h.key(x) not in bk],discarded,reasons,g)
    stages.append(st);prev=st['after']
   rec={'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':stages}
   records[arm].append(rec);stages_by_case.setdefault(cid,{})[arm]=rec
  appendix=out.get('source_appendix',{});relations=appendix.get('relations',[])
  for rel in relations:
   assert rel['from_source_id'] in final and rel['to_source_id'] in final
   assert hashlib.sha256(rel['witness'].encode()).hexdigest()==rel['witness_sha256']
   assert rel['witness_status']=='VERIFIED_LITERAL' and rel['applicability']=='NOT_ASSESSED'
  meta={e['source_id']:e['metadata'] for e in parent['evidence']}
  missing=[s for s in golden if s not in final];lost=sorted(set(golden)&(set(baseids)-set(final)));gained=sorted(set(golden)&(set(final)-set(baseids)))
  usage.extend(out['usage'])
  case_rows.append({'case_id':cid,'gold_total':len(golden),'acquired_count':len(pool),'baseline_count':len(baseids),'first_count':len(initial),'root_candidate_count':len(out.get('root_ids',[])),'root_selected_count':len(initial),'protected_linked_count':len(set(final)-set(initial)),'protected_loss':len(expected-set(final)),'unacquired_reachable_count':len(out.get('reachable_unacquired_ids',[])),'gold_in_roots':len(set(initial)&set(golden)),'final_count':len(final),
   'removed_count':len(set(baseids)-set(final)),'added_count':len(set(final)-set(baseids)),'orphan_branch_removed_count':len(set(pool)-set(final)),
   'gold_baseline':len(set(baseids)&set(golden)),'gold_final':len(set(final)&set(golden)),
   'gold_gained':gained,'gold_lost':lost,'missing':[{'source_id':s,'document_name':meta[s]['document_name'],'heading':meta[s]['heading']} for s in missing],
   'error':out['error'],'unresolved_issues':out.get('unresolved_issues',[]),'relation_count':len(relations),
   'selection_seconds':out['selection_wall_seconds'],'composed_seconds':out['composed_seconds'],'physical_calls':out['physical_model_calls'],'baseline_error':base.get('error'),'full_chain_composed_seconds':out['composed_seconds']})
 corpus=read(P/'실험/manifest.json')['retrieval_accounting']['corpus_total']
 arms=[{'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':rs,'aggregate':{'presented_total':sum(x['stages'][-1]['after_count'] for x in rs),'gold_after':sum(x['stages'][-1]['gold_after'] for x in rs),'gold_total':sum(x['gold_total'] for x in rs)}} for arm,rs in records.items()]
 ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':RUN,'arms':arms}],
  'audit':{'corpus_total':corpus,'final_present_semantics':'Prepared complete-original source packets, not sent to answer model. Selector sees logged bounded verbatim excerpts.','actual_answer_model_calls':0,'baseline':'Historical ADR0518 run002 final selections','protected_semantics':'Reachable acquired originals from selected roots; exclusively unselected-root branches removed; shared nodes survive','no_fresh_corpus_wide_retrieval':True}}
 ledger['artifact_sha256']=h._canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
 counts=[x['final_count'] for x in case_rows];basecounts=[x['baseline_count'] for x in case_rows];times=[x['selection_seconds'] for x in case_rows];composed=[x['composed_seconds'] for x in case_rows]
 totals={'cases':len(case_rows),'gold_total':sum(x['gold_total'] for x in case_rows),'gold_baseline':sum(x['gold_baseline'] for x in case_rows),'gold_final':sum(x['gold_final'] for x in case_rows),
  'gold_gained':sum(len(x['gold_gained']) for x in case_rows),'gold_lost':sum(len(x['gold_lost']) for x in case_rows),
  'baseline_count_mean':statistics.mean(basecounts),'final_count_mean':statistics.mean(counts),'final_count_p50':statistics.median(counts),'final_count_p95':pct(counts,.95),'final_count_max':max(counts),
  'fewer_sources_cases':sum(x['final_count']<x['baseline_count'] for x in case_rows),'more_sources_cases':sum(x['final_count']>x['baseline_count'] for x in case_rows),
  'all_gold_retained_cases':sum(not x['missing'] for x in case_rows),'error_cases':sum(bool(x['error']) for x in case_rows),'relations':sum(x['relation_count'] for x in case_rows),
  'selection_p50':statistics.median(times),'selection_p95':pct(times,.95),'composed_p50':statistics.median(composed),'composed_p95':pct(composed,.95),
  'physical_calls':sum(x['physical_calls'] for x in case_rows),'input_tokens':sum(x.get('input_tokens',0) or 0 for x in usage),'output_tokens':sum(x.get('output_tokens',0) or 0 for x in usage),'cost_usd':sum(x.get('cost_usd',0) or 0 for x in usage)}
 comparable=[x for x in case_rows if not x['error'] and not x['baseline_error']]
 totals.update(comparable_success_cases=len(comparable),comparable_baseline_mean=statistics.mean(x['baseline_count'] for x in comparable),comparable_candidate_mean=statistics.mean(x['final_count'] for x in comparable),full_chain_composed_p50=statistics.median(x['full_chain_composed_seconds'] for x in case_rows),full_chain_composed_p95=pct([x['full_chain_composed_seconds'] for x in case_rows],.95))
 totals.update(root_candidates_mean=statistics.mean(x['root_candidate_count'] for x in case_rows),selected_roots_mean=statistics.mean(x['root_selected_count'] for x in case_rows),protected_linked_mean=statistics.mean(x['protected_linked_count'] for x in case_rows),protected_loss=sum(x['protected_loss'] for x in case_rows),gold_in_roots=sum(x['gold_in_roots'] for x in case_rows),orphan_branch_removed=sum(x['orphan_branch_removed_count'] for x in case_rows),unacquired_reachable_mean=statistics.mean(x['unacquired_reachable_count'] for x in case_rows))
 passed=totals['gold_final']==90 and totals['protected_loss']==0 and totals['error_cases']==0 and totals['composed_p95']<=240
 paired={'candidate_only_complete':sum(x['gold_final']==x['gold_total'] and x['gold_baseline']<x['gold_total'] for x in case_rows),
  'baseline_only_complete':sum(x['gold_baseline']==x['gold_total'] and x['gold_final']<x['gold_total'] for x in case_rows),
  'both_complete':sum(x['gold_baseline']==x['gold_final']==x['gold_total'] for x in case_rows),
  'neither_complete':sum(x['gold_baseline']<x['gold_total'] and x['gold_final']<x['gold_total'] for x in case_rows)}
 summary={'totals':totals,'paired':paired,'criteria_met':passed,'in_sample':True,'decision_eligible':False,'main_changed':False,'actual_answer_model_calls':0,'source_count_target':None,'by_case':case_rows}
 write(A/'artifacts/summary.json',summary)
 for arm,rs in records.items():
  cs=[x['stages'][-1]['after_count'] for x in rs];got=sum(x['stages'][-1]['gold_after'] for x in rs)
  stats={'before_filter':sum(x['stages'][0]['after_count'] for x in rs),'after_filter':sum(cs),'presented_total':sum(cs),'presented_mean':statistics.mean(cs),'presented_p50':statistics.median(cs),'presented_p95':pct(cs,.95),'golden_recall':got/90,'selectivity':statistics.mean(cs)/corpus}
  for k,v in stats.items():m['retrieval_accounting'][k][arm]=v
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'artifacts/retrieval-stage-ledger.json')
 m['runs'][-1].update(status='complete',sha256=sha(A/'artifacts'/RUN/'results.json'))
 m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','gold':72,'cases':61,'replayed':True},'selection':{'status':'complete',**totals}},comparisons=[{'paired':paired,'gold_delta':totals['gold_final']-72,'count_mean_delta':statistics.mean(counts)-statistics.mean(basecounts),'criteria_met':passed}],usage={k:totals[k] for k in ['physical_calls','input_tokens','output_tokens','cost_usd']},latency={k:totals[k] for k in ['selection_p50','selection_p95','composed_p50','composed_p95']},error_taxonomy=[{'case_id':x['case_id'],'type':'governing_rule_selection' if x['gold_lost'] else 'retrieval_miss' if x['missing'] else 'other','detail':x} for x in case_rows if x['missing'] or x['error']])
 m['gemma_binding']['live_calls']=totals['physical_calls'];write(A/'실험/manifest.json',m)
 verdict='Proposed' if passed else 'Rejected'
 conclusion=f"필수 원문72/90 → {totals['gold_final']}/90; 시작점 평균{totals['selected_roots_mean']:.2f}개, 연결 보존 평균{totals['protected_linked_mean']:.2f}개, 전체 평균{totals['final_count_mean']:.2f}개. 연결 보호 손실{totals['protected_loss']}개; 오류{totals['error_cases']}문항."
 sections=[('결정 요약',conclusion+' '+verdict+'; MAIN unchanged.'),
 ('문제와 변경 전 구조','518에서 연결 원문도 개별 제거하다 필수 원문을 잃었다. 사용자 지시대로 첫 시작점만 선택하고 해당 연결 가지를 함께 보존한다. 시작점 제외 시 그 시작점에만 연결된 원문도 제외한다. 공유 원문은 채택 시작점이 하나라도 연결되면 유지한다.'),
 ('가설과 사전 판정 기준','[PLAN 최종 정정](PLAN.md), [최종 동결 설계](artifacts/frozen-design.json). 전체90/90, 선택 시작점에 연결된 회수완료 원문 손실0, 공유 연결 보존·배타적 제외 가지 제거,오류0,합산p95<=240초. 개수 목표 없음.'),
 ('실험 설계','동일513 회수 완료 풀·경로 재생 → 직접 질의 시작점만 Gemma에 제시(원문320자 이내) → 선택 시작점에서 기록된 anchor→candidate 회수 간선을 따라 도달 가능한 회수 완료 원문을 전부 결합. 연결 원문 개별 제거 호출 없음. 순환·중복은 집합으로 처리하며 선택 시작점별 소유 경로 보존. 모델 오류 시 전체 풀을 보존하지만 DEGRADED로 표시한다. 법적 참조 방향과 탐색 회수 방향을 구분한다.'),
 ('데이터·모델·재현성','공개145문서·고정61문항·평가원문90개. Gemma google/gemma-4-31b-it / OpenRouter DeepInfra FP8 / thinking off / temperature0 / 출력2304. 최대1회/문항·3worker. 기준답변은 사후 채점 전용. 기존 원문 풀 밖을 새로 회수하는 실험은 아니다.'),
 ('결과',block(totals)+block(paired)),('사례별 오류 분석','[문항별](실험/README.md), [누락 원문](artifacts/summary.json), [단계별 원장](artifacts/retrieval-stage-ledger.json). 보호된 연결 손실과 시작점 선택 실패를 분리한다.'),
 ('비용·지연·회수 규모',block({k:totals[k] for k in ['physical_calls','input_tokens','output_tokens','cost_usd','selection_p50','selection_p95','composed_p50','composed_p95']})+'합산은 과거513 회수+이번 시작점 선별·묶음 준비 시간. 실제 신규 종단시간이 아니며 최종답변 생성은 포함하지 않는다. 연결 원문 전체가 답변 모델에 전송된 것은 아니다.'),
 ('해석',conclusion+' 연결된 모든 원문 보존 정책 때문에 전체 후보 수가 이전 개별 선별보다 커질 수 있다. 시작점 수와 연결 원문 수를 분리해 해석한다.'),
 ('한계와 일반화 가능 범위','in_sample=true,decision_eligible=false. 원문320자 발췌 기반 시작점 판단,공개 노출61문항,실제 최종답변·GENOS·독립 평가 미측정. 회수 완료 풀 밖 연결은 reachable_unacquired_ids로 남기며 전체 코퍼스 연결 전수회수를 주장하지 않는다. ambiguous 회수 경로는 보존 가능하나 관계의 법적 확정으로 승격하지 않는다.'),
 ('운영 결정·롤백 조건',verdict+'. 운영 API·MAIN·GENOS 미반영. research runner가 기존 evidence/packet/routes를 소비하며 후보만 격리 구현했다. 선택 시작점·보호 연결 출처와 확인된 관계 문장을 산출물로 준비했다.'),
 ('재현 명령','`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-0519-root-selection-protected-relations --final` 및 `adr_structure.py graph --adr-root 04_EXPERIMENTS/ADR`. 완료 호출 재실행은 새 ADR로 기록한다.')]
 front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+verdict)
 (A/'README.md').write_text('---'+front+'---\n\n# 시작점 선택과 연결 원문 묶음 보존\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(sections,1))+'\n')
 qlookup={c['case_id']:c for c in prod['cases']};rows={x['case_id']:x for x in case_rows}
 table='# 시작점 선택·연결 보호61문항\n\n|문항|기존 조항|묶음 전체|기존 필수|묶음 필수|손실|관계|출처 목록|\n|---|---:|---:|---:|---:|---:|---:|---|\n'
 for q in m['questions']:
  cid=q['case_id'];out=outs[cid];row=rows[cid];parent=parents[cid];calls=[]
  for call in sorted((A/'artifacts'/RUN/cid/'model').glob('call-*')):calls.append({'path':str(call.relative_to(R)),**{p.name:read(p) for p in call.glob('*.json')}})
  inputs={'question':qlookup[cid]['question'],'parent_record':out['input_parent_path'],'parent_sha256':out['input_parent_sha256'],'root_candidates':out.get('root_ids',[]),'selected_roots':initial if False else out.get('selected_root_ids',[]),'original_packets':parent['packets'],'routes':{sid:parent['routes'].get(sid,[]) for sid in parent['read_complete']}}
  parts=[('실행 메타',block({'run_id':RUN,'model':'google/gemma-4-31b-it','answer_model_calls':0})),('사용자 질문 원문',qlookup[cid]['question']),('기준답변 — 채점 전용, 제품 입력 비공개',block(gold[cid])),('제품 입력을 구성한 원값',block(inputs)+'\n### 회수·탈락 단계 원장 — run·arm별\n'+block(stages_by_case[cid])),('제품 모델 호출 — run·arm별 실제 원문',block(calls)),('중간 LLM 호출 — router/compiler/verifier/repair','시작점 선별1회. 연결 원문 개별 제거0회. 모델 오류 시 전체 원문 보존을 별도 표시하며 다른 모델/provider fallback 없음.\n'+block(out)),('채점 호출과 반복 판정','모델 채점0회. 제품 선택 완료 뒤 canonical source 좌표·최종 전문 패킷·관계 witness 해시·양끝 선택 여부 검증.'),('사례 최종 판정',block(row))]
  (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
  link=f'[출처·관계](../artifacts/{RUN}/{cid}/sources-and-relations.md)' if out.get('source_appendix') else '오류'
  table+=f"|[{cid}]({q['file']})|{row['baseline_count']}|{row['final_count']}|{row['gold_baseline']}/{row['gold_total']}|{row['gold_final']}/{row['gold_total']}|{len(row['gold_lost'])}|{row['relation_count']}|{link}|\n"
 (A/'실험/README.md').write_text(table)
 subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_structure.py','hash','--path',str(A.relative_to(R))],check=True)
 files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ['manifest.json','completion.json','validation-final.txt','graph-check.txt','validation-preclose.txt']]
 files += [A/'PLAN.md',A/'product-cases.json',A/'gold-cases.json',C/'candidate.json']+list(Path(__file__).parent.glob('*.py'))+[R/f['frozen_path'] for rev in read(C/'candidate.json')['revisions'] for f in rev['files']]
 write(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Original run, source witness, frozen revision or post-selection audit'} for p in sorted(set(files))]})
 print(json.dumps(totals,ensure_ascii=False))
if __name__=='__main__':main()
