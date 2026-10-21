from pathlib import Path
from collections import Counter
from xml.etree import ElementTree as ET
import hashlib,json,re,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0914-answer-first-context-followup';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def unique(xs):return [json.loads(s) for s in sorted({canon(x) for x in xs})]
m=read(A/'실험/manifest.json');f=read(D/'freeze.json');criteria=read(D/'criteria.json')
assert all(sha(R/n)==h for n,h in f['files'].items())
results={};arms=[];ledger_counts={};corpus={}
for arm in ('retained',):
 rows={};cases=[];stage_totals=Counter()
 for scenario in read(D/'cases.json'):
  C=O/arm/scenario['id'];resource=read(A/f"artifacts/resource-{arm}-{scenario['id']}.json")
  for turn in scenario['turns']:
   P=C/turn['id']
   if not (P/'result.json').exists():continue
   subprocess.run([sys.executable,str(Path(__file__).parent/'observe.py'),arm,scenario['id'],turn['id']],check=True,stdout=subprocess.DEVNULL)
   audit=read(P/'audit.json');run=read(P/'result.json');calls=read(P/'call-summary.json');gens=read(P/'generations.json') if (P/'generations.json').exists() else [];body=read(P/'response.json').get('body',{});answer=body.get('answer',{});agent=body.get('assembly',{}).get('term_agent',{})
   rows[turn['id']]={**run,'answer_completed':run['http_status']==200 and bool(answer.get('text')),
    'request_scope':len(read(P/'request.json')['json']['document_ids']),
    'model_seconds':sum(c.get('seconds',0) for c in calls),'cleanup_seconds':sum(g.get('memory_cleanup_seconds',0) for g in gens),
    'phase_counts':dict(Counter(c['phase'] for c in calls)),
    'source_checks':len(audit['span_checks']),'source_mismatches':sum(not s['exact_original_match'] for s in audit['span_checks']),
    'handoffs':sum(e['kind']=='ACQUIRED_ORIGINALS_TO_ASSESS' for e in audit['events']),
    'automatic_gap_reentries':sum(e['kind']=='ASSESSMENT_GAP_REENTRY_PLANNED' for e in audit['events']),
    'research_deferred_to_user':sum(e['kind']=='ASSESSMENT_RESEARCH_DEFERRED_TO_USER' for e in audit['events']),
    'stop_reason':agent.get('stop_reason'),'coverage':agent.get('answer_coverage'),
    'goal_id':body.get('goal_id'),'session_id':body.get('session_id'),'executed':body.get('executed'),
    'peak_rss_bytes':resource['peak_group_rss_bytes'],'resource_stop':resource['stop_reason']}
   plans=m['design']['retrieval_stage_plan']['stages_by_arm'][arm];stages=[];before=[];before_occ=0
   for plan in plans:
    raw=audit['canonical_sets'][plan['stage_id']];after=unique(raw);bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())];reason='Not in committed selected originals or actual final citations; not a legal relevance verdict.'
    stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),'occurrence_counts':{'before':before_occ,'after':len(raw),'canonical_collapsed_before':before_occ-len(before),'canonical_collapsed_after':len(raw)-len(after)},'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]});before=after;before_occ=len(raw)
    stage_totals[plan['stage_id']]+=len(after)
   cases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':turn['id'],'gold_total':0,'gold_identities':[],'stages':stages})
   corpus[arm]=audit['corpus_total']
 results[arm]=rows;put(O/arm/'summary.json',rows);ledger_counts[arm]=dict(stage_totals)
 arms.append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in plans],'cases':cases,'aggregate':{'cases':len(cases),'presented_total':stage_totals['cited'],'gold_total':0}})
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}]};ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
historical=read(R/'04_EXPERIMENTS/ADR/ADR-0913-answer-first-financial-scope/artifacts/run-001/baseline/summary.json')
comparison=[]
for case in ('cm-001','cm-001-followup','cm-033'):
 b=historical.get(case,{});c=results['retained'].get(case,{})
 comparison.append({'case':case,'baseline_calls':b.get('model_calls'),'candidate_calls':c.get('model_calls'),'baseline_seconds':b.get('request_seconds'),'candidate_seconds':c.get('request_seconds'),'candidate_answer_completed':c.get('answer_completed',False)})
allrows=[r for rows in results.values() for r in rows.values()]
result={'status':'complete','by_arm':results,'comparisons':comparison,'contract_disposition':read(A/'artifacts/contract-disposition.json'),
 'all_source_checks_passed':all(r['source_mismatches']==0 for r in allrows),'all_answers_completed':len(allrows)==3 and all(r['answer_completed'] for r in allrows),
 'all_duplicates_identical_without_calls':all(all(r.get('checks',{}).values()) and r.get('checks') for r in allrows),
 'comparison_basis':'Earlier ADR0913 unchanged-code observations in the same financial/public scope; not a simultaneous paired trial',
 'candidate_initial_calls_reduced':sum(results['retained'].get(c,{}).get('model_calls',40) for c in ('cm-001','cm-033'))<sum(historical.get(c,{}).get('model_calls',0) for c in ('cm-001','cm-033')),
 'resource_stops':[r['resource_stop'] for r in allrows if r['resource_stop']],
 'decision_eligible':False,'working_code_integrated':False,'active_MAIN_changed':False,'genos_executed':False,'legal_accuracy_certified':False,
 'limitations':['One run per scenario/arm; known CM questions, no unseen legal accuracy or general speed certification.','Earlier ADR0913 baseline was observed before this candidate freeze. Same financial/public scope; no repeated inference or unseen legal test.','Current API and session software checks are in contract-disposition.json; known parent legacy fixture failures remain recorded in ADR0912.','Zero-call admission and profile-pin preflight failures preserved separately.','Candidate is isolated; working code, selected MAIN87 and GENOS have not changed.']}
put(O/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={arm:{'status':'complete','questions':len(rows),'product_answer_successes':sum(r['answer_completed'] for r in rows.values()),'legal_accuracy':None,'result':str((O/arm/'summary.json').relative_to(R))} for arm,rows in results.items()},comparisons=comparison,judge_disagreements=None,usage={'product_model_calls':sum(r['model_calls'] for r in allrows),'offline_evaluator_calls':0},latency={'sample_size_per_scenario_per_arm':1,'generalizable':False},error_taxonomy=[])
m['retrieval_accounting'].update(corpus_total=next(iter(corpus.values())),before_filter={a:n['native_read'] for a,n in ledger_counts.items()},after_filter={a:n['selected'] for a,n in ledger_counts.items()},presented_total={a:n['cited'] for a,n in ledger_counts.items()},presented_mean={a:n['cited']/len(results[a]) for a,n in ledger_counts.items()},presented_p50={a:None for a in results},presented_p95={a:None for a in results},golden_recall={a:None for a in results},selectivity={a:n['cited']/(corpus[a]*len(results[a])) for a,n in ledger_counts.items()});m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json');put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['확보한 원문을 기존 ASSESS에 먼저 전달하고 현재 질문의 근거 있는 답변을 우선 발행한다. 부족 사항은 유지하고 후속 질문으로 이어진다.','충분성 판단 전에 선택기가 가정적 예외·정의 조사를 계속하고, ASSESS도 이미 근거 있는 답변을 자동 재탐색으로 미뤘다.',json.dumps(criteria,ensure_ascii=False,indent=2),'동결 retained 후보 1회; 이전 ADR0913 baseline을 비교 참고. CM001→같은 세션 예외 후속 질문, 별도 세션 CM033. 단일 프로세스 순차 실행.','Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음. 실제 service.py와 격리된 ASGI 앱. 데이터 공유, 제품 코드·모델 입출력 해시 동결.',json.dumps(comparison,ensure_ascii=False,indent=2),'각 turn의 audit.json, call-summary.json, answer.txt; preflight-admission과 preflight-r1 실패 기록 보존.','각 summary.json: 실제 호출·모델시간·RAM 회수시간·원문 일치. 원시 usage 보존.','최초 답변의 확인 범위와 모든 가능한 예외의 검토를 구분한다. 충분성·관련성은 LLM 판단으로 남는다.','\n'.join(result['limitations']),'인샘플 probe. 작업 코드 통합·MAIN/GENOS 변경 여부는 별도 receipt로만 보고한다.','06_TOOLS/EXPERIMENTS/adr_0914의 prepare/seal/run_tests/live/observe/report.py 및 design/freeze.json. 완료 폴더에 재실행하지 않는다.']
(A/'README.md').write_text('---'+meta+'---\n\n# 확인된 근거 우선 답변과 사용자 후속 조사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{p}' for i,(h,p) in enumerate(zip(heads,parts),1))+'\n')
qheads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
questions={t['id']:t['question'] for s in read(D/'cases.json') for t in s['turns']}
for q in m['questions']:
 cid=q.get('id',q.get('case_id'));cid=cid if cid in questions else next((x for x in questions if x in q['file']),None)
 parts=['run-001 / retained / '+str(cid),questions.get(cid,str(q)),'승인 법률 gold 및 모델 judge 없음. 제품에 정답을 넣지 않음.','design/*.json 및 turn별 request.json/binding.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json; 확보→선택→인용.','turn별 canonical/, wire/ gzip와 raw/ 및 runtime의 실제 입출력.','turn별 call-summary.json 및 audit.json. 평가용 추가 LLM 없음.','실제 원문 span 검사, 소프트웨어 계약 검사. 법률 의미는 수동 관찰이며 정답률 인증 아님.',json.dumps(next((c for c in comparison if c['case']==cid),{}),ensure_ascii=False,indent=2)]
 (A/'실험'/q['file']).write_text('# 질문과 실제 실행\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{p}' for i,(h,p) in enumerate(zip(qheads,parts),1))+'\n')
(A/'실험/README.md').write_text('# 실험 질문 인덱스\n\n'+'\n'.join(f"- [{q.get('id',q['file'])}]({q['file']})" for q in m['questions'])+'\n')
for q in m['questions']:q['sha256']=sha(A/'실험'/q['file'])
put(A/'실험/manifest.json',m)
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen paired experiment and integrity records','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm'))]})
(A/'RESULT.txt').write_text(json.dumps({k:v for k,v in result.items() if k not in ('by_arm','contract_disposition')},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(comparison,ensure_ascii=False))
