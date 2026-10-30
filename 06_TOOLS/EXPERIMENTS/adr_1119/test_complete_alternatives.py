from pathlib import Path
from copy import deepcopy
import gzip,json
import pytest
from jsonschema import Draft202012Validator,ValidationError
from semantic_runtime.legal_agent import read_judgment as rj,read_candidate_pages as pager
from semantic_runtime.legal_agent.minimal_output import Projection
P=Path(__file__).parents[3]/'04_EXPERIMENTS/ADR/ADR-1118-rejected-review-ownership/artifacts/run-002/fsc-hard-005/canonical/002.json.gz'

@pytest.mark.parametrize('kind,relation',[('READ','DIRECT'),('READ','DEPENDENCY'),('FOLLOW_CONNECTION','DIRECT'),('FOLLOW_CONNECTION','DEPENDENCY')])
def test_complete_projected_action_and_visible_target_survive(kind,relation):
 d=json.load(gzip.open(P,'rt'));schema=d['schema'];v=d['view'];ctx=v['read_judgments'];current={s['id']:s for s in v['sources']}
 for b in schema['anyOf']:
  b['properties'].pop('read_review',None);b['required'].remove('read_review');b.pop('allOf',None)
  if b['properties']['choice']['const'] not in ('FINISH','PENDING'):
   node=b['properties']['selections']['items'] if b['properties']['choice']['const']=='READ' else b
   node.pop('allOf',None);node['properties'].pop('judgment_refs',None);node['required'].remove('judgment_refs')
 base=rj.attach(schema,ctx,current,['Q1']);read=next(b for b in base['anyOf'] if b['properties']['choice']['const']=='READ');targets=read['properties']['selections']['items']['properties']['target']['enum'];assert len(targets)>1
 _,s=pager.page_view({'read_candidates':[{'target':t} for t in targets]},base,0,1);projection=Projection(s)
 branch=next(b for b in s['anyOf'] if b['properties']['choice']['const']==kind and (kind=='READ' or b['properties']['relation']['const']==relation));node=branch['properties']['selections']['items'] if kind=='READ' else branch
 jid=ctx['new_review_ids'][0];original=next(x for x in ctx['current_originals'] if x['id']==jid)
 action={'target':node['properties']['target']['enum'][0],'issue_id':'Q1','missing_need':'추가 원문 확인','relation':relation,'source_ref':next(iter(current)) if relation=='DEPENDENCY' else None,'judgment_refs':[jid] if relation=='DEPENDENCY' else []}
 review={'new_reviews':{jid:{'use':'SUPPORT','finding':'시험 원문의 확인 내용','reason':'입력에 제시된 실제 원문을 확인함','basis_refs':original['source_refs']}}}
 raw={'choice':kind,'read_review':review,**({'selections':[action]} if kind=='READ' else action)}
 wire=projection.project(raw);Draft202012Validator(projection.wire).validate(wire);assert projection.expand(wire)==raw
 assert 'choice' in wire and not Draft202012Validator(projection.wire).is_valid({'relation':'DIRECT'})
 missing=deepcopy(wire);a=missing['selections'][0] if kind=='READ' else missing;a.pop('target',None)
 # One visible READ target may be a restored constant, so test an unauthorized
 # supplied value too. Neither a different target nor a field-only root executes.
 wrong=deepcopy(wire);a=wrong['selections'][0] if kind=='READ' else wrong;a['target']='UNAUTHORIZED'
 with pytest.raises(Exception):projection.expand(wrong)
 if kind=='READ':
  wrong=deepcopy(wire);wrong['selections'][0]['target']=targets[1]
  with pytest.raises(Exception):projection.expand(wrong)
 if relation=='DEPENDENCY':
  empty=deepcopy(wire);a=empty['selections'][0] if kind=='READ' else empty;a['judgment_refs']=[]
  with pytest.raises(Exception):projection.expand(empty)
