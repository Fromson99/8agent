"""Predeclared literal-requirement audit with fixed synthetic statements, model0."""
from common import *
from copy import deepcopy
f=read(DES/'freeze.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import scenario_review as review
from semantic_runtime.legal_agent.scenario_branch import compare
from semantic_runtime.legal_agent.scenario_facts import options
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent.errors import ProposalError
old=ROOT/'04_EXPERIMENTS/ADR/ADR-1280-scenario-bound-facts-live/artifacts/live/review-whatif/canonical/007.json.gz'
v=read(old)['view'];catalog=next(c['payload']['assembly_catalog'] for c in v['ontology_bundles'] if c.get('payload',{}).get('assembly_catalog'))
state={'facts':v['current_facts']};bindings={'cost':[x['id'] for x in options(state) if x['value']=='1380000원']}
e={'ontology':{'bundles':[{'assembly':catalog}]},'items':[],'outcome':'INSUFFICIENT','content_sha256':'synthetic-audit-baseline'}
c=compare(e,state,{'limit':{'type':'money','unit':'KRW','value':'2450000'}},kind='RULE',operation_id='burden-probe',bindings=bindings)
context={k:c[k] for k in ('kind','changes','changed_fields','evaluations','unresolved')};context['schema_version']='scenario-context-v3';context['content_sha256']=digest(context)
cases=[('canonical_value','가정한도2450000원에서 비용1380000원은 금액조건을 충족한다. 승인은 미확인이다.'),
 ('equivalent_korean_units','가정 한도245만원에서 비용138만원은 금액조건을 충족한다. 승인은 미확인이다.'),
 ('explicit_before_after_comparison','실제 규정의1000000원 한도를 가정에서2450000원으로 바꾸면, 비용1380000원은 금액조건을 충족한다. 승인은 미확인이다.')]
rows=[]
for label,text in cases:
 value={'claims':[{'claim_id':'C1','rule':None,'explanation':text}], 'scenario_review':{'context_hash':context['content_sha256'],'condition_results':review.results(context),'outcome':'UNCONFIRMED','application_links':[{'claim_id':'C1','condition_ids':['scenario-condition:1']}]}}
 try:review.check(value,context,state['facts']);codes=[]
 except ProposalError as exc:codes=[x['code'] for x in exc.issues]
 rows.append({'case':label,'text':text,'rejected':bool(codes),'codes':codes,'reviewer_observation':'All three express the same synthetic threshold result and keep approval unknown; comparisons and unit spelling differ. Existing strict authoring contract can reject the latter two.'})
put(ART/'burden-probes.json',{'model_calls':0,'candidate_revision':f['candidate_revision'],'rows':rows,'limits':'Targeted deterministic contract audit, not new real-model quality samples. No product or recorded output altered.'})
print(json.dumps(rows,ensure_ascii=False))
