"""Mock model vocabulary conversion only; never imported by product code."""
from copy import deepcopy
import json

def share(value):
 out=deepcopy(value);links=[];by_key={}
 # The scenario fixture derives a branch from an ordinary mock response.
 # Ordinary responses now already use shared links. Expand those definitions
 # before factoring the changed fixture again, preserving invalid unknown refs.
 existing={r['id']:r for r in out.get('review_links',[]) if isinstance(r,dict)}
 def restore(node):
  if isinstance(node,list):return [restore(x) for x in node]
  if not isinstance(node,dict):return node
  result={k:restore(v) for k,v in node.items()}
  if result.get('link_ref') in existing:
   definition=existing[result.pop('link_ref')]
   result.update({k:deepcopy(definition[k]) for k in ('claim_refs','basis_refs')})
  return result
 for field in ('read_judgment_review','requirement_review'):
  if field in out:out[field]=restore(out[field])
 def walk(node):
  if isinstance(node,list):return [walk(x) for x in node]
  if not isinstance(node,dict):return node
  result={k:walk(v) for k,v in node.items()}
  if ('claim_refs' in node and 'basis_refs' in node
      and not (('request_refs' in node and node.get('status') in ('UNRESOLVED','EXCLUDED'))
               or node.get('disposition') in ('UNRESOLVED','NOT_USED'))):
   row={k:result.pop(k) for k in ('claim_refs','basis_refs')};key=json.dumps(row,sort_keys=True)
   if key not in by_key:
    ident='review-link:'+str(len(links)+1);by_key[key]=ident;links.append({'id':ident,**row})
   result['link_ref']=by_key[key]
  elif 'claim_refs' in node and 'basis_refs' in node and node['claim_refs']==[]:
   result.pop('claim_refs')
  return result
 for field in ('read_judgment_review','requirement_review'):
  if field in out:out[field]=walk(out[field])
 out['review_links']=links
 return out
