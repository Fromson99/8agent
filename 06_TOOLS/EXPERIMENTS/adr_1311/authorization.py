"""Authorize only product-validated projections tied to the fixed API request."""
def derive(body,state,question,documents,session):
 if body.get('question')!=question or body.get('session_id')!=session or body.get('request_id')!='initial' or body.get('public_question') is not True:
  raise ValueError('Unapproved original request/session')
 if not state.get('document_ids') or not set(state['document_ids'])<=documents:raise ValueError('Unapproved document scope')
 if not isinstance(state.get('task'),str) or not state['task'].strip():raise ValueError('Invalid typed task')
 facts=state.get('facts')
 if not isinstance(facts,list) or any(not isinstance(f,dict) or not isinstance(f.get('value'),str) for f in facts):raise ValueError('Invalid typed facts')
 return '\n'.join(dict.fromkeys([state['task'],*[f['value'] for f in facts if f['value'].strip()]]))
def self_test():
 from copy import deepcopy
 b={'question':'original','session_id':'s','request_id':'initial','public_question':True};s={'task':'validated task','document_ids':['d'],'facts':[{'value':'fact'}]}
 before=deepcopy((b,s));assert derive(b,s,'original',{'d'},'s')=='validated task\nfact' and (b,s)==before
 for key,v in [('question','other'),('session_id','other'),('request_id','other'),('public_question',False)]:
  try:derive({**b,key:v},s,'original',{'d'},'s')
  except ValueError:pass
  else:raise AssertionError(key)
 for key,v in [('document_ids',['other']),('task',''),('facts',[{'value':None}])]:
  try:derive(b,{**s,key:v},'original',{'d'},'s')
  except ValueError:pass
  else:raise AssertionError(key)
 return 8
