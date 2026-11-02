"""Mock model vocabulary conversion only; never imported by product code."""
from copy import deepcopy
import json

def share(value):
 out=deepcopy(value);links=[];by_key={}
 def walk(node):
  if isinstance(node,list):return [walk(x) for x in node]
  if not isinstance(node,dict):return node
  result={k:walk(v) for k,v in node.items()}
  if 'claim_refs' in node and 'basis_refs' in node:
   row={k:result.pop(k) for k in ('claim_refs','basis_refs')};key=json.dumps(row,sort_keys=True)
   if key not in by_key:
    ident='review-link:'+str(len(links)+1);by_key[key]=ident;links.append({'id':ident,**row})
   result['link_ref']=by_key[key]
  return result
 for field in ('read_judgment_review','requirement_review'):
  if field in out:out[field]=walk(out[field])
 out['review_links']=links
 return out
