"""Finalize the actual frozen qualification; never change a threshold after calls."""
from common import *
import sys,gzip,statistics
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
m=read(ADR/'실험/manifest.json');a=read(ART/'analysis.json');f=read(ART/'design-freeze.json');s=read(ART/'stage.json');contracts=read(ART/'contracts-final.json')
rejected='--rejected' in sys.argv
assert (rejected or a['strict_success']) and contracts['passed']
for group in ('test_bindings','script_bindings'):
 for n,h in f['design'][group].items():assert sha(ROOT/n)==h,n
if not rejected:assert all(sha(ROOT/n)==h and sha(ROOT/s['roots']['candidate']/n)==h for n,h in s['files']['candidate'].items())
consumers={} if rejected else {mode:read(ART/f'consumer-{mode}.json') for mode in ('candidate','working')}
assert all(v['status']=='PASS' for v in consumers.values())
known=read(ART/'known-query/result.json');review=read(ART/'known-query-review.json');assert rejected or review['passed']
def bound(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
usage={k:sum(r.get(k) or 0 for r in a['usage']+known['usage']) for k in ('input_tokens','output_tokens','thinking_tokens','cost_usd')}
calls=a['physical_model_calls']+known['model_calls'];usage['physical_model_calls']=calls
checks={**a['checks'],'native_contracts':contracts['passed'],'candidate_working_consumers':not rejected,'all419_exact':not rejected,'known_query_verified':review['passed'],'frozen_bindings':True}
result={'strict_success':not rejected,'status':'REJECTED_INCOMPLETE_QUALIFICATION' if rejected else 'QUALIFIED_FOR_MAIN','checks':checks,'correct':a['correct'],'total_per_arm':16,
 'contracts':contracts['tests'],'physical_model_calls':calls,'fresh_entry_calls':a['physical_model_calls'],'known_diagnostic_calls':known['model_calls'],
 'usage':usage,'known_query':bound(ART/'known-query-review.json'),'analysis':bound(ART/'analysis.json'),'contracts_result':bound(ART/'contracts-final.json'),
 'consumers':{x:bound(ART/f'consumer-{x}.json') for x in consumers},'quality_certified':False,'genos_verified':False,
 'limits':['16 previously unexecuted scope expressions do not certify legal answer accuracy or traffic-wide generalization.',
 'The known commercial-law question is separately labelled in-sample diagnostic; it is not part of the fresh 16-case accuracy denominator.',
 'Retrieval ledger measures all paginatable synthetic heading candidates before page slicing, not legal relevance or answer recall. Existing request/context/time/page bounds remain.',
 'Unchanged data contains two previously recorded malformed nested article bindings; unambiguous stored article roots and legacy divisions are traversable, but unknown source identities are not invented.',
 'Historical global ADR graph/test issues outside this frozen suite remain separate. The rejected ADR0977 p7 and obsolete fixture failures are retained.',
 'External Qwen3.8 performance does not verify GENOS internal model, Oracle adapter or deployment. No GENOS connection, release deployment, Git commit or push.']}
save(ART/'result.json',result)
m['decision_eligible']=not rejected;m['in_sample']=False;m['lineage']['hypothesis_delta']=m['design']['hypothesis']
for arm in m['design']['arms']:
 arm['changes']='Selected MAIN99' if arm['id']=='baseline' else 'Same frozen integrated scope/candidate/assessment/hierarchy/multiturn code plus scoped content search and stored parent context at read choice'
 arm['controls']='Same public metadata, synthetic structure, Qwen3.8 policy and one-call scope budget; no answer-specific product hints'
m['runs'][0].update(status='complete',selection_rule=f['design']['call_order'],artifact_path=str((ART/'result.json').relative_to(ROOT)),sha256=sha(ART/'result.json'))
latency={arm:{'p50_seconds':statistics.median(r['seconds'] for r in ts),'p95_seconds':sorted(r['seconds'] for r in ts)[round((len(ts)-1)*.95)]} for arm,ts in a['by_arm'].items()}
m['results'].update(status='complete',by_arm={arm:{'status':'complete','correct':n,'total':16,'strict_success':arm=='candidate'} for arm,n in a['correct'].items()},comparisons=[a['comparison']],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=result['limits'])
if rejected:
 result['executed_scope_cases']={arm:sum(x['executed'] for x in ts) for arm,ts in a['by_arm'].items()}
 result['limits'].insert(0,'Fresh scope experiment NOT RUN. Known service diagnostic recovered original434 but returned INSUFFICIENT/limited original excerpts, not a completed explanation. No integration or MAIN mutation.')
 for arm,row in m['results']['by_arm'].items():row.update(strict_success=False,executed_scope_cases=result['executed_scope_cases'][arm],evaluation_complete=False)
 save(ART/'result.json',result);m['runs'][0]['sha256']=sha(ART/'result.json')
ret=m['retrieval_accounting']
for metric in ('presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity'):ret[metric]={arm:r[metric] for arm,r in a['retrieval'].items()}
ret['before_filter']={arm:64 for arm in a['correct']};ret['after_filter']=ret['presented_total'];ret['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json')
cases=read(ART/'cases.json');gold=read(ART/'grading-only.json');questions=[]
for p in (ADR/'실험').glob('질문-*.md'):
 with gzip.open(ART/('initial-scaffold-'+p.name+'.gz'),'wb') as out:out.write(p.read_bytes())
 p.unlink()
for n,case in enumerate(cases,1):
 cid=case['id'];name=f'질문-{n:03d}-{cid}.md';links=[]
 for arm in ('baseline','candidate'):
  links.append(f'run-001 / {arm}: [complete decision and resolver result](../artifacts/trials/{cid}/{arm}/result.json)')
  for p in sorted((ART/'trials'/cid/arm/'model').rglob('*.json')):links.append(f'[{p.parent.name}/{p.name}](../artifacts/{p.relative_to(ART)})')
 values=['run-001, one physical model request per arm; no repair in fresh entry sample.',case['question'],json.dumps(gold[cid],ensure_ascii=False),
 '[Product questions](../artifacts/cases.json), [synthetic metadata](../artifacts/documents.json), [frozen design](../artifacts/design-freeze.json).',
 '[Measured independent heading-candidate ledger](../artifacts/retrieval-ledger.json). Candidate metadata availability before pagination; not actual model source READ or legal answer relevance.',
 '\n\n'.join(links),'Only initial entry model; no judge/hidden calls. Separately known question uses actual bounded service, see known-query/result.json.',
 'Offline exact-name/coordinate comparison after decisions; no LLM judge.',
 json.dumps({arm:next(x for x in ts if x['case_id']==cid) for arm,ts in a['by_arm'].items()},ensure_ascii=False,indent=2)]
 p=ADR/'실험'/name;p.write_text('# '+cid+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)))
 questions.append({'number':n,'case_id':cid,'file':name,'sha256':sha(p)})
m['questions']=questions
(ADR/'실험/README.md').write_text('# Fresh scope qualification\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in questions)+'\n\nKnown query is separate: [service diagnostic](../artifacts/known-query-review.json).\n')
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted').replace('in_sample: true','in_sample: false').replace('decision_eligible: false','decision_eligible: true').replace('main_wiring: unchanged','main_wiring: promotion-candidate')
if rejected:front=front.replace('status: Accepted','status: Rejected').replace('decision_eligible: true','decision_eligible: false').replace('main_wiring: promotion-candidate','main_wiring: unchanged')
texts=['Accepted: exact frozen candidate qualified for authorized local MAIN promotion. Field deployment is separate.',
 'Independent title and scope choices allowed a selected title with KEEP/null. Metadata gates removed navigable articles; any existing claim deferred material gaps. One scope decision now drives both search modes, model materiality/reasons remain intact, and existing structural/multiturn fixes are integrated.',
 m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
 m['design']['sampling']+'\n\nParent ADR0978 is rejected and complete. Its original-question service failure and unexecuted qualification are preserved; these 16 cases were frozen but never called in that parent. ADR0977 probe outcomes are not counted as fresh success.',
 'Qwen3.8 / Parasail FP8 / reasoning none / no fallback. Same public metadata grant and generation; 16 previously unexecuted questions ×2 arms. All product inputs and expected outcomes were frozen separately before calls.',
 json.dumps({'fresh_correct':a['correct'],'contracts':contracts['tests'],'checks':checks,'known_query':review},ensure_ascii=False,indent=2),
 'The prior p7 miss is preserved in ADR0977. Missing named documents are unresolved scopes rather than permission to widen. Team-name/old-output test fixture errors were migrated explicitly; original failures remain in this artifact directory.',
 json.dumps({'calls':calls,'usage':usage,'latency':latency,'metadata_retention':a['retrieval']},ensure_ascii=False,indent=2),
 'Evidence supports tested scope/source contracts and the known original question recovery. Metadata recall is a reachability metric, not legal relevance; no general legal quality certification.',
 '\n\n'.join(result['limits']),
 'Promote only with exact candidate/working/release hash agreement and native service binding. On ACL/original/hash/state or selected-service mismatch restore MAIN99 using preserved pointer and release rollback. No quality waiver.',
 '06_TOOLS/EXPERIMENTS/adr_0980/{run_case,guard,analyze,run_final_contracts,consumer,integrate_working,seal_release,finish,promotion_record}.py. Completed calls are immutable. Stable adr_structure.py validate --final and graph checks are recorded. [Result](artifacts/result.json), [candidate binding](artifacts/stage.json), [integration](artifacts/integration.json).']
if rejected:
 texts[0]='Rejected. Known query recovered original434 and both ratios, but model over-expanded the question and returned INSUFFICIENT original excerpts only. 309 deterministic contracts passed. Fresh qualification not started; MAIN unchanged.'
 texts[4]='Qwen3.8 / Parasail FP8 / reasoning none / no fallback. Planned 16×2 fresh decisions; none executed. Known original question separately executed8 calls. All fresh cases are explicitly NOT RUN.'
 texts[5]=json.dumps({'executed_scope_cases':result['executed_scope_cases'],'contracts':contracts['tests'],'known_query':review},ensure_ascii=False)
 texts[10]='MAIN99 and working code unchanged. Preserve all frozen inputs, failures and partial calls. Next candidate requires a new ADR; no same-ADR product modification or model retry.'
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR0980 unified scope qualification\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,texts)))
save(ADR/'실험/manifest.json',m)
files=[]
for p in sorted(ART.rglob('*')):
 if not p.is_file() or p==ART/'manifest.json' or any(x.startswith('tmp-') or x.startswith('runtime') for x in p.relative_to(ART).parts):continue
 files.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen qualification and exact integration evidence','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':files})
print('Qualified',a['correct'],'contracts',contracts['tests'],'physical calls',calls)
