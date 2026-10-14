from pathlib import Path
R=Path(__file__).resolve().parents[3];p=R/'06_TOOLS/EXPERIMENTS/adr_0719/audit.py'
s=(R/'06_TOOLS/EXPERIMENTS/adr_0712/audit.py').read_text().split("candidate=diagnostics['compact'];",1)[0]
s=s.replace('ADR-0712-compact-direct-read-context','ADR-0719-request-repair-public-qualification').replace("'compact'","'repaired'").replace("cid.startswith('R')","cid.startswith('S')")
a=s.index('def gap_errors(state):');b=s.index("arms=['baseline'",a)
s=s[:a]+'''def gap_errors(state):
 errors=[]
 for r in state.get('gap_rounds',[]):
  receipts={x['id']:x for x in r.get('action_receipts',[])};gaps={g['gap_id']:g for g in r['gaps']}
  for v in r.get('resolutions',[]):
   if v['status']=='NOT_AVAILABLE':
    acts=[receipts.get(x,{}) for x in v.get('action_refs',[])]
    if not acts or any(a.get('status')!='COMPLETED' or v['gap_id'] not in a.get('gap_ids',[]) or
       a.get('outcome',{}).get('target_key')!=gaps[v['gap_id']]['gap_key'] or
       a.get('outcome',{}).get('absence_proven') is not True for a in acts):errors.append('absence not bound to exact target')
   if v['status']=='RESOLVED':
    from semantic_runtime.legal_agent.request_repair import covers_target
    if not covers_target(gaps[v['gap_id']]['target_binding'],state,v.get('basis_refs',[])):errors.append('resolved target lacks exact delivered spans')
 return errors
import sys
sys.path.insert(0,str(R/read(D/'freeze.json')['code_root']/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.legal_agent import completion_contracts as cc,completion_v5 as v5
''' + s[b:]
s=s.replace("  diagnostics[arm].append(row);",'''  assessment=latest.get('ASSESS',{});composition=latest.get('COMPOSE',{})
  integrity=[]
  if arm=='repaired' and r['http_status']==200:
   try:
    cc.verify_composition(assessment,composition)
    for claim in claims:
     v5.verify_content(claim)
     if claim['text'] not in output['answer']['text']:raise ValueError('claim missing from published answer')
    if meta.get('accepted_outcome',{}).get('assessment_hash')!=hashlib.sha256(canon(assessment).encode()).hexdigest():raise ValueError('accepted outcome hash differs')
   except Exception as exc:integrity.append(str(exc))
  attempts=r['attempts'];last_assess=max((i for i,a in enumerate(attempts) if a['phase']=='memory-assess'),default=len(attempts))
  row.update(content_integrity_errors=integrity,accepted_outcome=meta.get('accepted_outcome'),
      answer_coverage=meta.get('answer_coverage'),model_proposal=assessment.get('model_proposal'),
      physical_attempt_seconds=sum(x['seconds'] for x in attempts),
      final_answer_excluded_calls=last_assess,final_answer_excluded_seconds=sum(x['seconds'] for x in attempts[:last_assess]),
      memory=output.get('execution_stats',{}).get('memory'),attempts=attempts,
      backend_model_policy_valid=all(read(c/'response.json').get('provider')=='Parasail' and read(c/'response.json').get('model')=='qwen/qwen3.8-27b' for c in (folder/'provider').glob('call-*') if (c/'response.json').exists()))
  if r['http_status']==200:(folder/'answer.txt').write_text(output['answer']['text']+'\\n')
  diagnostics[arm].append(row);''')
s+='''
candidate=diagnostics['repaired'];primary=[x for x in candidate if x['case_id'].startswith('H')];repeated=[x for x in candidate if x['case_id'].startswith('S')]
paired={x['case_id']:x for x in diagnostics['baseline']};frozen=read(D/'freeze.json')
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration/artifacts/run-001/result.json')
checks={'all_requests':sum(map(len,diagnostics.values()))==9,
 'candidate_primary_supported':sum(x['supported_response'] for x in primary)==3,
 'candidate_repeat_supported':sum(x['supported_response'] for x in repeated)==3,
 'no_paired_supported_regression':all(x['supported_response'] or not paired[x['case_id']]['supported_response'] for x in primary),
 'all_successful_citations_verified':all(x['quote_count']>0 and x['all_quotes_supported'] for x in candidate if x['http_status']==200),
 'all_candidate_primary_gold_presented':all(x['gold_presented'] for x in candidate),
 'public_scope_only':all(x['public_scope_valid'] for x in candidate),
 'actual_binding_valid':all(x['expected_binding_matches'] for x in candidate),
 'approved_judgment_and_gap_state_valid':all(not x['accepted_judgment_hash_errors'] and not x['gap_receipt_errors'] for x in candidate),
 'raw_diagnostics_in_public_zero':all(not x['public_diagnostic_keys'] for x in candidate),
 'no_new_contract_regressions':not parent['new_regressions'],
 'all20_new_contracts_pass':parent['new_contracts']['tests']==20 and not parent['new_contracts']['failed'],
 'same_code_to_release':all(sha(R/frozen['code_root']/p)==h for p,h in frozen['serving_files'].items()),
 'unseen_primary_roots':not(set(read(D/'selection-audit.json')['primary_roots'])&set(read(D/'excluded-source-ids.json'))),
 'physical_call_accounting':all(x['physical_model_attempts']==x['model_calls']==len(x['attempts']) for xs in diagnostics.values() for x in xs),
 'content_preserved':all(not x['content_integrity_errors'] for x in candidate),
 'unexpected_http500_zero':all(x['http_status']!=500 for x in candidate),
 'main_unchanged':all(x['main_unchanged'] for xs in diagnostics.values() for x in xs),
 'frozen_files_unchanged':all(sha(R/p)==h for p,h in frozen['files'].items()),
 'actual_model_provider_binding':all(x['backend_model_policy_valid'] for xs in diagnostics.values() for x in xs)}
result={'strict_success':all(checks.values()),'checks':checks,'by_arm':{a:{'status':'complete','cases':xs,
 'supported':sum(x['supported_response'] for x in xs),'calls':sum(x['physical_model_attempts'] for x in xs),
 'input_tokens':sum(x['usage']['input_tokens'] for x in xs),'output_tokens':sum(x['usage']['output_tokens'] for x in xs),
 'request_seconds':sum(x['request_seconds'] for x in xs)} for a,xs in diagnostics.items()},
 'quality_certified':False,'semantic_correctness_absolute_gate':False,'genos_deployed':False,'main_wiring':'unchanged',
 'inherited_contract_failures':parent['baseline_all']['failed']}
result['primary_comparison']={a:{'supported':sum(x['supported_response'] for x in xs if x['case_id'].startswith('H')),
 'calls':sum(x['physical_model_attempts'] for x in xs if x['case_id'].startswith('H')),
 'input_tokens':sum(x['usage']['input_tokens'] for x in xs if x['case_id'].startswith('H')),
 'request_seconds':sum(x['request_seconds'] for x in xs if x['case_id'].startswith('H')),
 'final_answer_excluded_calls':sum(x['final_answer_excluded_calls'] for x in xs if x['case_id'].startswith('H')),
 'final_answer_excluded_seconds':sum(x['final_answer_excluded_seconds'] for x in xs if x['case_id'].startswith('H'))} for a,xs in diagnostics.items()}
put(O/'result.json',result)
m['results'].update(status='complete',by_arm=result['by_arm'],comparisons=[],judge_disagreements=None,
 usage={a:{k:sum(x['usage'][k] for x in xs) for k in ('input_tokens','output_tokens','cost_usd','seconds')} for a,xs in diagnostics.items()},
 latency={a:{'request_p50':statistics.median(x['request_seconds'] for x in xs)} for a,xs in diagnostics.items()},error_taxonomy=[k for k,v in checks.items() if not v])
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));ra=m['retrieval_accounting'];ra['corpus_total']=max(x['corpus_roots'] for xs in diagnostics.values() for x in xs)
for metric,key in [('before_filter','recalled_roots'),('after_filter','acquired_roots'),('presented_total','presented_roots')]:ra[metric]={a:sum(x[key] for x in xs) for a,xs in diagnostics.items()}
for metric,fn in [('presented_mean',statistics.mean),('presented_p50',statistics.median),('presented_p95',lambda v:sorted(v)[round((len(v)-1)*.95)])]:ra[metric]={a:fn([x['presented_roots'] for x in xs]) for a,xs in diagnostics.items()}
ra['golden_recall']={a:sum(x['gold_presented'] for x in xs)/len(xs) for a,xs in diagnostics.items()};ra['selectivity']={a:ra['presented_mean'][a]/ra['corpus_total'] if ra['corpus_total'] else 0 for a in diagnostics}
sys.path.insert(0,str(R/'06_TOOLS/EXPERIMENTS/adr_0697'))
from ledger_skips import complete_ledger
ledger=complete_ledger(ledger,dataset,m);ledger.pop('artifact_sha256');ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json.gz',ledger)
ra['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json.gz');put(A/'실험/manifest.json',m)
print(json.dumps({'checks':checks,'primary':result['primary_comparison'],'strict_success':result['strict_success']},ensure_ascii=False,indent=2))
'''
p.write_text(s)
