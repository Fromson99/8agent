from common import *
p=Path(__file__).parent/'fixtures.py';s=p.read_text()
s=s.replace(' out=deepcopy(value);links=[];by_key={}', ''' out=deepcopy(value);links=[];by_key={}
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
  if field in out:out[field]=restore(out[field])''')
p.write_text(s)
put(ART/'fixture-double-sharing-fix.json',{'cause':'Scenario mock derives a branch from a baseline mock response. Ordinary baseline now contains shared links, so old share() cleared definitions on a second pass, leaving dangling purpose-review references. Actual captured failure REVIEW_LINK_INVALID allowed_ids=[].', 'correction':'Test fixture expands its existing exact definitions before resharing new branch; leaves unknown reference faults intact. No product or validator changes; rev001 unchanged.', 'fixture':bind(p)})
