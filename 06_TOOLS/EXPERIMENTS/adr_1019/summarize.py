"""Post-run offline accounting only; never changes model inputs or answers."""
from common import *
from report_common import finish_documents,seal
import sys,statistics,sqlite3,gzip
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
raw=read(RUN/'result.json');reviews=read(ART/'offline/manual-review.json');m=read(ADR/'실험/manifest.json')
criteria=read(ART/'offline/criteria.json');cases=read(DES/'cases.json');arms=['baseline','candidate'];rows=[];graded=[]
sources={s['id']:s for s in read(DES/'curated-source-values.json')['sources']};extra=read(ART/'offline/extra-source.json');sources[extra['id']]=extra
for result in raw['results']:
 cid,arm=result['case_id'],result['arm'];p=RUN/'agent_layer'/arm/cid;a=read(p/'audit.json');review=reviews['cases'][cid][arm];delivery=read(p/'delivery-audit.json');required=read(p/'required-audit.json')
 assert len(review['required_status'])==len(criteria[cid]['required'])
 rec=StageLedgerRecorder(cid,arm,identity_canonicalizer);rec.record_stage('original_read','source',a['read_coordinates']);final={(x['doc_id'],x['node']) for x in a['final_coordinates']}
 rec.record_stage('final_cited','present',a['final_coordinates'],parent_stage_ids=['original_read'],discard_reasons=[{'coordinate':x,'reason':'Read source not cited in final output'} for x in a['read_coordinates'] if (x['doc_id'],x['node']) not in final]);capture=rec.capture();put(p/'retrieval-capture.json',capture)
 gold=[{'doc_id':sources[s]['document_id'],'node':int(sources[s]['node'])} for s in criteria[cid]['source_ids']];graded.append(grade_capture(capture,gold))
 checks=a['span_checks'];technical=all(x['exact_match'] and x['authorized'] for x in checks) and not a['unmapped_citations']
 reentries=[e for e in a['events'] if e['kind']=='ASSESSMENT_GAP_REENTRY_PLANNED'];closed=[e for e in a['events'] if e['kind']=='KNOWLEDGE_CLOSED_EVIDENCE_DECISION']
 failures=[]
 for f in (p/'raw').glob('*/response.json'):
  value=read(f)
  if isinstance(value,dict):
   for choice in value.get('choices',[]):
    if choice.get('finish_reason')=='length':failures.append(str(f.relative_to(ROOT)))
 prompt_checks=[]
 for f in (p/'wire').glob('*.gz'):
  with gzip.open(f,'rt') as stream:v=json.load(stream)
  system=v['messages'][0]['content']
  if '이번 요청은' in system:prompt_checks.append(('이번 평가는 현재 질문에 필요한 설명을 완성하는 작업이다.' in system)==True)
 novel=(extra['document_id'],int(extra['node']))
 rows.append({'case_id':cid,'arm':arm,'reuse_mode':result['reuse_mode'],'seconds':result['seconds'],'model_calls':result['model_calls'],'http_status':result.get('http_status'),
  'technical_source_check':technical,'verified_spans':sum(x['span_count'] for x in checks),'read_articles':len(a['read_coordinates']),'final_cited_articles':len(final),
  'required_items_met':review['required_status'].count('met'),'required_items_total':len(review['required_status']),'core_pass':all(x=='met' for x in review['required_status']) and not review['forbidden_violations'],
  'additional_research_reentries':len(reentries),'closed_gate_decisions':len(closed),'closed_gate_blocked_gaps':sum(len(e['payload']['blocked_gaps']) for e in closed),
  'length_failures':failures,'actual_prompt_verified':bool(prompt_checks) and all(prompt_checks),'assessment_prepared_refs_present':delivery['every_assessment_prepared_refs_present'],
  'novel_source_read':novel in {(x['doc_id'],x['node']) for x in a['read_coordinates']},'novel_source_cited':novel in final,'review':review,'required_review_audit':{k:v for k,v in required.items() if k not in ('events','wire','display')}})
ledger=build_experiment_artifact('ADR-1019',m['experiment_id'],[build_run_artifact('run-001',graded,{a:['original_read','final_cited'] for a in arms})]);put(RUN/'retrieval-ledger.json',ledger)
usage={k:sum((u.get(k) or 0) for r in raw['results'] for u in r['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']};by_arm={}
for arm in arms:
 rr=[r for r in rows if r['arm']==arm]
 by_arm[arm]={'status':'complete','evaluated':len(rr),'planned':5,'unexecuted':5-len(rr),'correct':sum(r['core_pass'] for r in rr),'total':len(rr),'accuracy':sum(r['core_pass'] for r in rr)/len(rr) if rr else None,
  'required_items_met':sum(r['required_items_met'] for r in rr),'required_items_total':sum(r['required_items_total'] for r in rr),'model_calls':sum(r['model_calls'] for r in rr),'total_seconds':sum(r['seconds'] for r in rr),
  'p50_seconds':statistics.median(r['seconds'] for r in rr) if rr else None,'p95_seconds':max((r['seconds'] for r in rr),default=None),'length_failures':sum(len(r['length_failures']) for r in rr)}
paired={'candidate_only':[],'baseline_only':[],'both_correct':[],'both_incomplete':[],'unpaired':[]};coverage_regressions=[]
for case in cases:
 pair={r['arm']:r for r in rows if r['case_id']==case['id']}
 if len(pair)!=2:paired['unpaired'].append(case['id']);continue
 b,c=pair['baseline'],pair['candidate'];paired['both_correct' if b['core_pass'] and c['core_pass'] else 'candidate_only' if c['core_pass'] else 'baseline_only' if b['core_pass'] else 'both_incomplete'].append(case['id'])
 if c['required_items_met']<b['required_items_met']:coverage_regressions.append(case['id'])
b,c=by_arm['baseline'],by_arm['candidate'];novel=next((r for r in rows if r['case_id']=='cm-new-lockup' and r['arm']=='candidate'),{})
success={'all_requests':raw['complete'],
 'required_items_retained':len([r for r in rows if r['arm']=='candidate'])==5 and all(r['required_review_audit']['structural_pass'] for r in rows if r['arm']=='candidate'),
 'model_coverage_not_lower':c['required_items_met']>=b['required_items_met'] and not coverage_regressions,
 'no_candidate_forbidden':all(not r['review']['forbidden_violations'] for r in rows if r['arm']=='candidate'),
 'source_integrity':all(r['technical_source_check'] for r in rows),
 'call_bound':c['model_calls']<=b['model_calls']+5,'latency_bound':c['total_seconds']<=1.5*b['total_seconds']}

summary={'status':'complete','all_requests_executed':raw['complete'],'native_api_requests':len(rows),'product_model_calls':sum(r['model_calls'] for r in rows),'usage':usage,'by_arm':by_arm,'rows':rows,'paired':paired,'coverage_regressions':coverage_regressions,'success_criteria':success,'all_success_criteria_met':all(success.values()),
 'main_changed_by_this_experiment':False,'active_pointer_change_observed':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')!=read(DES/'active-before.json'),'experiment_source_generation':100,'current_active_generation':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'],
 'oracle_executed':False,'genos_executed':False,'holdout':False,'semantic_quality_certified':False,'scope':'Same use-first prompt, readable source notes, delivery and policy gate; candidate alone persists required items and renders their outcomes. Closed gate begins after initial source acquisition, not a no-navigation initial fast path.'}
put(RUN/'summary.json',summary);m['runs'][0].update(status='complete',artifact_path=str((RUN/'summary.json').relative_to(ROOT)),sha256=sha(RUN/'summary.json'))
m['results'].update(status='complete',by_arm=by_arm,comparisons=[paired],judge_disagreements=0,usage={'product_model_calls':summary['product_model_calls'],'offline_evaluator_calls':0,**usage},latency={'scope':'Single sequential observation per case/arm; no statistical certification','by_arm':by_arm},error_taxonomy=[{'case':r['case_id'],'arm':r['arm'],'type':'required_issue_omission' if r['http_status']==200 else 'other','note':r['review']['note']} for r in rows if not r['core_pass']])
selected=read(DES/'selected.json');docs=read(RUN/'binding.json')['public_documents'];nav=sqlite3.connect((ROOT/selected['release']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True);corpus=nav.execute('select count(*) from source where document_id in ('+','.join('?' for _ in docs)+')',docs).fetchone()[0];nav.close()
a=m['retrieval_accounting'];counts={arm:[r['final_cited_articles'] for r in rows if r['arm']==arm] for arm in arms};a.update(corpus_total=corpus,before_filter={arm:sum(r['read_articles'] for r in rows if r['arm']==arm) for arm in arms},after_filter={arm:sum(counts[arm]) for arm in arms},presented_total={arm:sum(counts[arm]) for arm in arms},presented_mean={arm:statistics.mean(counts[arm]) if counts[arm] else 0 for arm in arms},presented_p50={arm:statistics.median(counts[arm]) if counts[arm] else 0 for arm in arms},presented_p95={arm:max(counts[arm],default=0) for arm in arms},golden_recall={},selectivity={arm:(statistics.mean(counts[arm]) if counts[arm] else 0)/corpus for arm in arms})
for arm in arms:
 hit=total=0
 for r in rows:
  if r['arm']!=arm:continue
  au=read(RUN/'agent_layer'/arm/r['case_id']/'audit.json');gold={(sources[s]['document_id'],int(sources[s]['node'])) for s in criteria[r['case_id']]['source_ids']};hit+=len(gold&{(x['doc_id'],x['node']) for x in au['final_coordinates']});total+=len(gold)
 a['golden_recall'][arm]=hit/total if total else 0
a['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json');put(ADR/'실험/manifest.json',m)

print(json.dumps(summary,ensure_ascii=False,indent=2))
