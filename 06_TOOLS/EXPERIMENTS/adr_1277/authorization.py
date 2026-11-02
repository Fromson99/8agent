"""Experiment grant covers validated host derivation of two fixed approved turns."""
def derive(body,state,questions,documents):
    if body.get('question') not in questions or state.get('task') not in questions:
        raise ValueError('Unapproved original request/task')
    if not state.get('document_ids') or not set(state['document_ids'])<=documents:
        raise ValueError('Unapproved document scope')
    facts=state.get('facts')
    if not isinstance(facts,list) or any(not isinstance(f,dict) or not isinstance(f.get('value'),str) for f in facts):
        raise ValueError('Invalid typed host fact state')
    return '\n'.join(dict.fromkeys([state['task'],*[f['value'] for f in facts if f['value'].strip()]]))

def self_test():
    from copy import deepcopy
    body={'question':'follow'};state={'task':'initial','document_ids':['d'],'facts':[{'name':'f','value':'approved fact'}]}
    assert derive(body,state,{'initial','follow'},{'d'})=='initial\napproved fact'
    assert derive(body,{**state,'facts':[]},{'initial','follow'},{'d'})=='initial'
    for key,value in [('task','foreign'),('document_ids',['foreign']),('document_ids',[]),('facts',[{'value':None}])]:
        changed=deepcopy(state);changed[key]=value
        try:derive(body,changed,{'initial','follow'},{'d'})
        except ValueError:pass
        else:raise AssertionError(key)
    try:derive({'question':'foreign'},state,{'initial','follow'},{'d'})
    except ValueError:pass
    else:raise AssertionError('foreign body')
    return 7
