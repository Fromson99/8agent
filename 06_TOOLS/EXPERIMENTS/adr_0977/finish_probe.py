"""Close diagnostic probe without making it eligible for MAIN."""
from common import *
import sys, gzip, statistics
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS, QUESTION_HEADINGS_V4
m=read(ADR/'실험/manifest.json'); cases=read(ART/'probe-cases.json');gold=read(ART/'probe-grading-only.json')
rows=[];usage={};latency={}
for case in cases:
 for arm in ('baseline','candidate'):
  r=read(ART/'probe'/case['id']/arm/'result.json');command=r.get('command') or {}
  actual=sorted({t['document'] for t in (command.get('search_scope_change') or {}).get('targets',[])})
  row={'case_id':case['id'],'arm':arm,'selected_names':actual,'expected_names':sorted(gold[case['id']]),
       'scope_decision_correct':actual==sorted(gold[case['id']]),'error':r['error'],'seconds':r['seconds']}
  rows.append(row)
  for u in r['usage']:
   for k,v in u.items():
    if isinstance(v,(int,float)):usage[k]=usage.get(k,0)+v
for ar in ('baseline','candidate'):
 values=[r['seconds'] for r in rows if r['arm']==ar];latency[ar]={'p50':statistics.median(values),'max':max(values)}
counts={ar:sum(r['scope_decision_correct'] for r in rows if r['arm']==ar) for ar in ('baseline','candidate')}
result={'status':'DIAGNOSTIC_COMPLETE_NOT_QUALIFIED','rows':rows,'scope_decision_correct':counts,'total_per_arm':8,'physical_calls':16,
 'usage':usage,'latency':latency,'contracts_passed':40,'contract_evidence':'contracts-current-3.xml','decision_eligible':False,
 'limitations':['Scope decision metric is separate from resolution: 민법 is absent from the 65-document public grant; its unresolved scope is preserved, not widened.',
 'Candidate p7 incorrectly selects AUTHORIZED_SCOPE despite explicit 민법. This semantic miss remains a failure.',
 'Known query p1 is diagnostic only; no end-to-end legal accuracy claim.',
 'Earlier broad audit had 51 failures; obsolete mocks and expected removed heuristics require explicit migration and regression classification in the next ADR.',
 'No production code integration, MAIN pointer change or GENOS deployment in this probe.']}
save(ART/'result.json',result)
m['integration']['rationale']=m['integration']['reason'];m['lineage']['hypothesis_delta']=m['design']['hypothesis']
for arm in m['design']['arms']:
 arm['changes']='Selected MAIN99 unchanged' if arm['id']=='baseline' else 'Single scope decision, complete lexical candidates, semantic assessment, hierarchy and existing multiturn repairs'
 arm['controls']='Same actual public grant, generation, model policy, questions and single-call budget'
m['runs'][0].update(selection_rule=m['design']['call_order'],status='complete',artifact_path=str((ART/'result.json').relative_to(ROOT)),sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={ar:{'status':'complete','scope_decision_correct':counts[ar],'total':8} for ar in counts},
 comparisons=[{'baseline':'baseline','candidate':'candidate','scope_decision_correct':counts}],judge_disagreements=0,usage=usage,latency=latency,error_taxonomy=result['limitations'])
reason='This live probe executes entry selection and metadata resolution only; no article retrieval or answer generation. Candidate retrieval modifications are deterministic contracts only here and require a measured fresh qualification.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
for p in (ADR/'실험').glob('질문-*.md'):
 with gzip.open(ART/('initial-scaffold-'+p.name+'.gz'),'wb') as f:f.write(p.read_bytes())
 p.unlink()
m['questions']=[]
for n,case in enumerate(cases,1):
 cid=case['id'];name=f'질문-{n:03d}-{cid}.md'
 links=[]
 for ar in ('baseline','candidate'):
  folder=ART/'probe'/cid/ar
  links.append(f'run-001 / {ar}: [result](../artifacts/probe/{cid}/{ar}/result.json)')
  links.extend(f'[{p.name}](../artifacts/{p.relative_to(ART)})' for p in sorted(folder.rglob('*.json')) if p.name!='result.json')
 values=['run-001, baseline/candidate, each one actual request, no retries.',case['question'],json.dumps(gold[cid],ensure_ascii=False),
 '[Frozen input](../artifacts/probe-cases.json); public metadata only, same 65 approved documents.',reason,'\n\n'.join(links),
 'Only request-entry runs; no hidden evaluator or repair calls.', 'Offline exact names comparison after selection; no LLM grading.',
 json.dumps([r for r in rows if r['case_id']==cid],ensure_ascii=False,indent=2)]
 p=ADR/'실험'/name;p.write_text(f'# {cid}\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)))
 m['questions'].append({'number':n,'case_id':cid,'file':name,'sha256':sha(p)})
(ADR/'실험/README.md').write_text('# Scope diagnostic records\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
values=['Probe completed; not eligible for MAIN. Candidate p7 semantic scope miss remains recorded.',
 'MAIN99 independently chose title hints and KEEP; structural title/term gates discarded navigable candidates. See scope-decisions.json.',
 json.dumps(m['design'],ensure_ascii=False,indent=2),
 'Eight frozen public scope questions × two arms. Completed parents ADR0974 and ADR0976; working changes preserved in snapshot.',
 'Qwen3.8 / Parasail FP8 / none / no fallback. Same generation and grant; raw outputs and hashes preserved.',
 json.dumps({'correct_scope':counts,'contracts':40},ensure_ascii=False), '\n\n'.join(result['limitations']),
 json.dumps({'usage':usage,'latency':latency},ensure_ascii=False)+'\n\n'+reason,
 'Single decision fixes the known conflicting representation; model semantics and unavailable documents remain distinct failure classes.',
 'Development probe, not held-out legal correctness or performance evidence.',
 'MAIN99 unchanged. Next ADR must freeze fresh examples and final contracts before calls.',
 '06_TOOLS/EXPERIMENTS/adr_0977/probe_case.py and run_contracts.py. Completed outputs must not be overwritten. [Artifacts](artifacts/manifest.json).']
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR0977 diagnostic\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,values)))
save(ADR/'실험/manifest.json',m)
files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved diagnostic evidence','contains_raw_prompts_and_outputs':'model' in p.parts} for p in sorted(ART.rglob('*')) if p.is_file() and p.name!='manifest.json' and 'runtime' not in p.parts]
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0977','created_at':m['reservation']['created_at'],'files':files})
print(counts)
