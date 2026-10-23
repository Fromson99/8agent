"""Close a probe without claiming MAIN adoption or generalized legal accuracy."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4
m=read(ADR/'실험/manifest.json');r=read(ART/'result.json');f=read(ART/'design-freeze.json')
assert all(sha(ROOT/n)==h for n,h in f['runner_hashes'].items())
assert m['design']['success_criteria']==f['design']['success_criteria']
m['in_sample']=True;m['decision_eligible']=False
m['runs'][0].update(status='complete',sha256=sha(ART/'result.json'))
m['results'].update(status='complete',by_arm={a:{'status':'complete','correct':r['correct'][a],'total':8,'graded':r['graded_per_arm'][a],'known':r['known'][a]['checks']} for a in ('baseline','candidate')},comparisons=[r['comparison']],judge_disagreements=0,usage={**r['usage'],'physical_calls':r['physical_calls']},latency=r['latency'],error_taxonomy=[x for rr in r['by_arm'].values() for x in rr if not x['passed']])
known={a:{k:v[k] for k in ('checks','calls','seconds','model_seconds','headings','previous_opinion_navigation_calls','outcome','error')} for a,v in r['known'].items()}
limits=['Known question is in-sample; eight synthetic probes are development checks and not broad legal correctness or a holdout qualification.',
 'No extra semantic-review calls were added. ASSESS and tool selection remain separate stages; their complete fusion was not implemented or claimed. This candidate enriches their existing inputs and reasons.',
 'A prior opinion reaches navigation only with its exact original source/coordinates/text hash in the current input. It is a reviewable opinion, never an automatically accepted legal conclusion.',
 'One service execution per arm cannot establish p95 production latency. Provider failure is not a completed answer and cannot be counted as a speed improvement.',
 'MAIN100, working production files and GENOS remain unchanged. No Git commit/push or field deployment.',
 'Canonical retrieval recall was not measured. The primary probes use fixed original/candidate menus and assess need/action decisions; the separate known trace records what was actually read. This limits adoption eligibility.',
 'Existing global ADR graph errors are reported separately; no global graph repair claim.']
state='Proposed' if r['probe_passed'] or r['status']=='MODEL_EVALUATION_UNAVAILABLE' else 'Rejected'
front=(ADR/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: '+state)
parts=[('Model evaluation unavailable due to provider429; no accuracy/speed conclusion, all failed calls retained and MAIN unchanged.' if r['status']=='MODEL_EVALUATION_UNAVAILABLE' else 'Probe passed; isolated candidate retained for separate qualification.' if r['probe_passed'] else 'Probe did not meet all frozen gates; all outputs retained, MAIN unchanged.'),
 'The tool menu already supported READ, structured lookup, fulltext search and connection traversal. A reopened selection received gap history but lacked the source-bound previously supported explanation. The candidate rebinds that explanation to current page spans and asks the existing assessment/action choice to connect unresolved requested content, proposed exploration and expected answer impact.',
 m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
 m['design']['sampling']+'\n\n'+json.dumps(m['design']['call_order'],ensure_ascii=False),
 'Exact MAIN100 source/code baseline; isolated three-module candidate and frozen engine pins. Qwen3.8 / Parasail FP8 / reasoning none / no fallback. One sequential process and no adaptive whole-case retry. [Frozen design](artifacts/design-freeze.json).',
 json.dumps({'correct':r['correct'],'comparison':r['comparison'],'checks':r['checks'],'contracts':r['contracts'],'known':known},ensure_ascii=False,indent=2),
 json.dumps(r['by_arm'],ensure_ascii=False,indent=2),
 json.dumps({'usage':r['usage'],'physical_calls':r['physical_calls'],'synthetic_latency':r['latency'],'known':{a:{k:v[k] for k in ('calls','seconds','model_seconds')} for a,v in r['known'].items()}},ensure_ascii=False,indent=2),
 'Need/action decisions and provenance are assessed separately. Successful dispatch or schema validation does not prove legal necessity. A source-bearing partial answer remains permitted; unresolved requested dependencies remain investigable.',
 '\n\n'.join(limits),
 'No promotion: this is an in-sample development probe, with any failed/invalid comparison retained. Reverting requires selecting no new candidate because MAIN100 was never changed. A follow-up experiment must reserve a new ADR and retain these exact results.',
 '.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0988/{prepare,make_cases,repin,freeze,full_query,run_case,guard,analyze,finish}.py. Completed frozen calls are immutable and must not be rerun in place. [Results](artifacts/result.json) · [Candidate and release binding](artifacts/stage.json).']
(ADR/'README.md').write_text('---'+front+'---\n\n# 추가 탐색 필요성 실험\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(ADR_HEADINGS,parts)))
cases={c['id']:c for c in read(ART/'cases.json')};gold=read(ART/'grading-only.json')
for q in m['questions']:
 cid=q['case_id'];folder=ART/'known-query' if cid=='known-special-resolution' else ART/'trials'/cid
 links=[]
 for a in ('baseline','candidate'):
  links.append(f'[{a} result](../artifacts/{(folder/a/"result.json").relative_to(ART)})')
  for p in sorted((folder/a/'model').rglob('*.json')):links.append(f'[{a}/{p.parent.name}/{p.name}](../artifacts/{p.relative_to(ART)})')
 values=['run-001; baseline MAIN100 / isolated candidate; exact provider payloads retained.', '상법에서 주주총회 특별결의요건에 대해서 알려줘' if cid=='known-special-resolution' else cases[cid]['question'], json.dumps(f['design']['success_criteria'] if cid=='known-special-resolution' else gold[cid],ensure_ascii=False), '[Frozen source inputs](../artifacts/cases.json) and [binding](../artifacts/design-freeze.json).', 'Fixed originals and menus; no measured corpus retrieval ledger. Actual model input/output links below; do not infer full corpus coverage.', '\n\n'.join(links), 'Existing model phases only. Extra review calls: 0. All transport attempts recorded.', 'Offline frozen criteria; no LLM judge or product-visible gold.', json.dumps(known if cid=='known-special-resolution' else {a:next(x for x in r['by_arm'][a] if x['case_id']==cid) for a in ('baseline','candidate')},ensure_ascii=False,indent=2)]
 p=ADR/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+''.join(h+'\n\n'+v+'\n\n' for h,v in zip(QUESTION_HEADINGS_V4,values)));q['sha256']=sha(p)
(ADR/'실험/README.md').write_text('# 실험 질문\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
save(ADR/'실험/manifest.json',m)
items=[]
for p in sorted(ART.rglob('*')):
 if not p.is_file() or p==ART/'manifest.json' or 'runtime' in p.relative_to(ART).parts:continue
 items.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen inputs, exact outputs, failures, diagnostics and comparison','contains_raw_prompts_and_outputs':'model' in p.parts})
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0988','files':items})
print(state,'probe complete; MAIN unchanged')
