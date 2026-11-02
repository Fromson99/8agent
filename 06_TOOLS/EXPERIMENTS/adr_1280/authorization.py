"""Experiment-only authorization of the fixed question and server-issued actions."""
def derive(body,state,questions,documents):
 if body.get('question') not in questions or state.get('task') not in questions:raise ValueError('Unapproved request/task')
 if not state.get('document_ids') or not set(state['document_ids'])<=documents:raise ValueError('Unapproved source')
 facts=state.get('facts')
 if not isinstance(facts,list) or any(not isinstance(f,dict) or not isinstance(f.get('value'),str) for f in facts):raise ValueError('Invalid host facts')
 return '\n'.join(dict.fromkeys([state['task'],*[f['value'] for f in facts if f['value'].strip()]]))
def self_test():
 state={'task':'question','document_ids':['d'],'facts':[{'name':'cost','value':'1500000'}]}
 assert derive({'question':'action'},state,{'question','action'},{'d'})=='question\n1500000'
 for key,value in [('task','foreign'),('document_ids',['foreign']),('document_ids',[]),('facts',[{'value':None}])]:
  try:derive({'question':'action'},{**state,key:value},{'question','action'},{'d'})
  except ValueError:pass
  else:raise AssertionError(key)
 return 5
