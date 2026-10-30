from common import *
from copy import deepcopy
import gzip,importlib.util
f=read(DES/'freeze.json');b=read(DES/'baseline.json');C=ROOT/f['code_root']
sys.path[:0]=[str(C/'02_BACKEND'),str(C)]
from semantic_runtime.legal_agent.wire_schema import project_request
from semantic_runtime.legal_agent import read_judgment_final as final
from jsonschema import Draft202012Validator

def expand(s):
 defs=s.get('$defs',{})
 def visit(v,seen=()):
  if isinstance(v,dict):
   if set(v)=={'$ref'}:
    r=v['$ref'];assert r.startswith('#/$defs/') and r not in seen
    return visit(defs[r[8:]],seen+(r,))
   return {k:visit(c,seen) for k,c in v.items() if k!='$defs'}
  if isinstance(v,list):return [visit(c,seen) for c in v]
  return v
 return visit(s)
rows=[]
for row in read(ROOT/'04_EXPERIMENTS/ADR/ADR-1209-cumulative-main-input-audit/artifacts/input-wire-size-audit.json')['rows']:
 p=ROOT/row['source']['path'];assert sha(p)==row['source']['sha256']
 request=json.loads(gzip.decompress(p.read_bytes()));original=deepcopy(request)
 wire,receipt=project_request(request);s=request['response_format']['json_schema']['schema'];w=wire['response_format']['json_schema']['schema']
 check=(w==s if '$defs' in s else expand(w)==s)
 assert check and request==original
 remainder=deepcopy(wire);remainder['response_format']['json_schema']['schema']=s;assert remainder==request
 Draft202012Validator.check_schema(w)
 rows.append({'adr':row['adr'],'call':row['call'],'source':row['source'],'receipt':receipt,'schema_equivalent':check,'request_except_schema_exact':True})
assert len(rows)==49
oldpath=ROOT/b['manifest']['code_root']/'02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py'
spec=importlib.util.spec_from_file_location('semantic_runtime.legal_agent._baseline_final',oldpath);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
branch=[]
for count in range(4):
 for purpose in ('none','first','all'):
  for enforce in (False,True):
   ctx={'judgments':[{'id':'J'+str(i),'review_purposes':[{'id':'P'+str(i)}] if purpose=='all' or purpose=='first' and i==0 else []} for i in range(count)],'needs':[],'conflicts':[],'change_review':True}
   a=old.review_schema(ctx,[{'id':'B1'}],enforce_claim_shape=enforce);z=final.review_schema(ctx,[{'id':'B1'}],enforce_claim_shape=enforce);restored=deepcopy(z)
   if count and purpose!='none':
    target=restored['properties']['judgments']['items'];parts=[]
    for v in target['anyOf']:
     if v['properties']['disposition']=={'enum':['USE','CONDITIONAL']}:
      for disposition in ('USE','CONDITIONAL'):
       copy=deepcopy(v);copy['properties']['disposition']={'const':disposition};parts.append(copy)
     else:parts.append(v)
    target['anyOf']=parts
   assert restored==a,(count,purpose,enforce)
   branch.append({'judgments':count,'purposes':purpose,'enforce_claim_shape':enforce,'unmerged_structural_equality':True})
put(ART/'historical-schema-preservation.json',{'rows':rows,'count':49,'schema_equivalent':True,'request_except_schema_exact':True,'changed':sum(r['receipt']['changed'] for r in rows),'external_model_calls':0,'note':'Read-only diagnostics on historical input schemas. Existing local refs are intentionally unchanged; no replay of historical outputs as quality evidence.'})
put(ART/'final-branch-equivalence.json',{'cases':branch,'all24_exact':len(branch)==24,'note':'Splitting only the combined USE/CONDITIONAL enum reproduces the complete MAIN119 schema byte-for-structure for each context, including NOT_USED requirements.'})
print('Historical49 exact,',sum(r['receipt']['changed'] for r in rows),'factored; final24 structural equivalence')
