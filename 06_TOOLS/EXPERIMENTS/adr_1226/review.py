from common import *
from copy import deepcopy
x=read(ART/'live/execution.json');assert len(x['results'])==2
norms=[read(ART/f'live/saved-007-{c}-normalized.json')['normalized'] for c in ('a','b')]
ka=read(ART/'live/saved-007-a-knowledge.json');kb=read(ART/'live/saved-007-b-knowledge.json')
pa=ka['proposal'];pb=kb['proposal']
na={n['id']:n for n in pa['graph']['nodes']};nb={n['id']:n for n in pb['graph']['nodes']}
assert set(na)=={'n-001','n-002','n-003'} and set(nb)==set(na)|{'n-004','n-005','n-006','n-007'}
assert all(na[k]==nb[k] for k in na) and kb['diff']['nodes']['removed']==[]
assert len(kb['comparison_history'])==2 and len(kb['observation_ledger'])==3
source_ids=[r['source'] for r in pb['comparisons'][0]['basis']];assert source_ids==['S2','S3','S4','S5']
assert nb['n-005']['text']=='취득방법: 사모의 방법으로 발행된 주식을 취득할 것'
assert nb['n-006']['text']=='취득시기: 상장예비심사 신청일부터 신규상장 신청일까지 해당 주식을 취득할 것'
assert '나머지 수량' in nb['n-007']['text'] and '포함할 것' in nb['n-007']['text']
fields=[]
for c,n in zip(('a','b'),norms):
 for o in n['proposal']['observations']:
  for field in ('reason','purpose'):
   if o[field]['state']=='PRESENT':fields.append({'case':c,'observation_id':o['id'],'field':field,'value':o[field]['value'],'raw_pointers':[v['pointer'] for v in o[field]['locators']]})
assert len(fields)==6
assert pa['comparisons'][0]['verdict']=='SUPPORTED' and '독립된 의무가 아닌' in pa['comparisons'][0]['reason']
assert na['n-001']['kind']=='CONDITION' and '취득하는 경우' in na['n-001']['text']
assert na['n-002']['slots']['action']['value']=='보유' and na['n-002']['slots']['conditions']['value']==['n-001']
errors=[]
for i,s in enumerate(x['stage_receipts'],1):
 context=read(ART/f'live/input-{i:03d}.json')['context']
 if context.get('repair'):errors.append({'phase':s['phase'],'attempt':s['attempt'],'error':context['repair']['previous']['error']})
put(ART/'content-review.json',{'all_predeclared_content_conditions_passed':False,'method':'Read-only analyst review against pre-frozen expectations and exact recorded raw/source fields. No evaluator model or new product input.','structural_pipeline_completed':True,'coverage_and_locators':True,'absent_reason_purpose_preserved':False,'present_fields_without_explicit_raw_reason_purpose':fields,'a_obligation_correction':False,'a_evidence':{'comparison_verdict':pa['comparisons'][0]['verdict'],'comparison_reason':pa['comparisons'][0]['reason'],'condition_node':'n-001','effect_node':'n-002','effect_action':'보유','dependency':'n-002 REQUIRES_CONDITION n-001','full_original_sentence_preserved':True,'finding':'The full statement includes acquire-and-hold, but typed action keeps only holding and comparison explicitly treats acquisition as prerequisite rather than independent obligation; criterion unmet.'},'b_three_acquisition_rules_present':True,'b_evidence':{'nodes':['n-005','n-006','n-007'],'source_ids':['S3','S4','S5'],'method':'사모','time':'상장예비심사 신청일부터 신규상장 신청일까지','quantity':'인수계약 잔여 수량 포함'},'b_previous_nodes_preserved':True,'b_previous_misinterpretation_also_preserved':True,'history_revisions':2,'observations_retained':3,'repair_errors':errors,'limitations':['Both fresh normalizations copy the statement or identifier into reason/purpose although raw subtrees contain no explicit reason/purpose; exact locators do not certify field meaning.','A treats acquisition as a prerequisite for holding, supports the original condition-like opinion, and keeps only holding in action; frozen acquisition-obligation criterion fails. B preserves that prior graph unchanged.','Both compiled previews remain PARTIAL due to unrecorded review slots; no knowledge approval or publication.','Known two-case probe, no holdout/generalized legal accuracy or latency causal claim.']})
print('Structure2/2; B prior nodes+3criteria preserved; content failed: absent reason/purpose and A obligation classification')
