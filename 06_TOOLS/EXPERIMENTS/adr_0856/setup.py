from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0856-host-assembled-output-contract';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');m=read(R/p['manifest_path']);assert p['generation']==82
names=[x['target_path'] for x in read(R/'02_BACKEND/lawrag/research/candidates/adr_0853/integrated/candidate.json')['files']]
assert all(sha(R/n)==h for n,h in m['files'].items())
put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':m})
put(D/'working-before.json',{n:sha(R/n) for n in names})
put(D/'data-binding.json',{'path':m['data_path'],'manifest_sha256':m['data_manifest_sha256']})
criteria={'hypothesis':'Action-specific generation alternatives retain their required values and identity pools. Host-owned constants/neutral fields are omitted and assembled once; no semantic value is guessed.',
 'success':['Known missing-queries boundaries reconstruct without model repair','Wrong-action target is forbidden on wire and after reconstruction','All model adapters retain original evidence, state, budgets and failure owners','Each active schema is inventoried and generation schema is valid','Latest MAIN82 workflow/basis/data/search bytes preserved except reviewed codec/pins'],
 'failure':['Invented search query, reason, evidence or legal conclusion','Permission/state/hash bypass','Lost latest MAIN feature','Wire-valid required semantic omission or cross-action target accepted'],
 'evaluation':'In-sample defect reproduction and software contract probe; no legal accuracy claim and no promotion from this probe. Separate prospective qualification follows completed probe.',
 'calls':0,'recovery':'Codec never calls model. Existing gateway/stage owns bounded repair and preserves journal/counters/deadline; malformed/conflicting semantic output rejected; transport and partial-output states unchanged.',
 'planned_changes':['decision_projection: root common requirements, branch-specific inactive readOnly fields, retain legacy normalization','minimal_output: exact anyOf generation alternatives; no permissive property/identity union','wire_schema: preserve action alternatives in provider schema'],
 'matrix':['saved ADR0855 accepted/rejected boundaries','typed/untyped SEARCH_STRUCTURE','all navigation actions + missing semantic field + cross-action target','constant omitted/exact/conflicting','numbered references, partial legacy output, AD, workflow recovery, VLM','source read/fulltext + state/ACL/budget regression']}
put(D/'criteria.json',criteria)
cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','assembled','--experiment-id','ADR-0856-experiment-v1','--arm-id','assembled','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Lossless host assembly and branch-specific wire/canonical agreement',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='ADR0855-captured-boundaries-and-schema-catalogue',version='20261018-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
for arm in m['design']['arms']:arm.update(changes='Selected MAIN82' if arm['id']=='baseline' else criteria['planned_changes'],controls=['same complete MAIN82 pipeline/data/profile/model policy','zero real model calls','same failure and retry ownership'])
m['runs'][0].update(selection_rule=criteria['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
why='Software schema and reconstruction probe with recorded/synthetic proposals; no retrieval or legal quality comparison.'
m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why
put(A/'실험/manifest.json',m)
for name in ('run_tests.py','consumer.py','preview.py'):
 t=(Path(__file__).parent.parent/'adr_0853'/name).read_text().replace('adr_0853/integrated','adr_0856/assembled').replace('ADR-0853-basis-wire-integration','ADR-0856-host-assembled-output-contract').replace('basis-lifecycle-integrated-preview','host-assembled-probe-preview')
 (Path(__file__).parent/name).write_text(t)
print('Frozen criteria; isolated 711-file MAIN82 candidate prepared')
