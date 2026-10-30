from common import *
S=ROOT/read(DES/'candidate.json')['snapshot'];B=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(n,old,new):
 p=B/n;s=p.read_text();assert old in s,(n,old[:70]);p.write_text(s.replace(old,new,1))
p=B/'output_contract.py';s=p.read_text();start=s.index('def schema_issue(error):');end=s.index('\ndef decision_issues',start)
s=s[:start]+'''def schema_issue(error):
    row = issue('SCHEMA_'+str(error.validator).upper(), pointer(error.absolute_path),
        rule='json-schema:'+pointer(error.absolute_schema_path),
        expected=deepcopy(error.validator_value))
    # A bounded diagnostic preview, not a source or a new executable proposal.
    value = error.instance
    row['received'] = (value[:300] if isinstance(value,str) else deepcopy(value)
                       if value is None or isinstance(value,(bool,int,float)) else
                       {'type':type(value).__name__})
    row['message'] = error.message[:500]
    return row


def schema_issues(errors):
    """Explain only the uniquely selected branch; acceptance still uses all rules."""
    rows = []
    def collect(error):
        if len(rows) >= MAX_ISSUES:return
        if error.validator in ('anyOf','oneOf') and error.context:
            selected = None
            if isinstance(error.instance,dict):
                for key in ('choice','next_action','operation','kind','status','disposition'):
                    if key not in error.instance:continue
                    matches = [n for n,branch in enumerate(error.validator_value)
                        if isinstance(branch,dict) and
                        branch.get('properties',{}).get(key,{}).get('const',object()) == error.instance[key]]
                    if len(matches)==1:
                        selected=matches[0];break
            if selected is not None:
                children=[child for child in error.context if list(child.schema_path)[:1]==[selected]]
                if children:
                    for child in children:collect(child)
                    return
            row=schema_issue(error)
            row['expected_constraint']='one complete permitted action alternative'
            row['message']='Choose one permitted action and supply its required fields.'
            if isinstance(error.instance,dict):
                choices=list(dict.fromkeys(b.get('properties',{}).get('choice',{}).get('const')
                    for b in error.validator_value if isinstance(b,dict)))
                choices=[x for x in choices if x is not None]
                if choices and error.instance.get('choice') not in choices:
                    row.update(path=pointer((*error.absolute_path,'choice')),
                        expected_constraint={'enum':choices},received=error.instance.get('choice'))
            rows.append(row);return
        if error.validator=='required' and isinstance(error.instance,dict):
            for name in error.validator_value:
                if name not in error.instance and len(rows)<MAX_ISSUES:
                    row=schema_issue(error);rule=error.schema.get('properties',{}).get(name,{})
                    row.update(path=pointer((*error.absolute_path,name)),received={'missing':True},
                        expected_constraint={k:deepcopy(v) for k,v in rule.items() if k in ('type','enum','const','minItems','maxItems')},
                        message='Required field is missing.')
                    if row not in rows:rows.append(row)
            return
        row=schema_issue(error)
        if error.validator=='enum' and list(error.absolute_path)[-1:]==['coordinate_scope']:
            row['message']='coordinate_scope selects a structural branch (body/addendum/annex/form/repeated/appendix); 조/항/호/목 are levels.'
        if row not in rows:rows.append(row)
    for error in errors:collect(error)
    return rows[:MAX_ISSUES]


def validate_shape(value, schema, *, reference_space='canonical'):
    errors = schema_issues(Draft202012Validator(schema).iter_errors(value))
    if errors:
        exc=OutputContractError('model output does not match the original schema', errors)
        exc.reference_space=reference_space
        raise exc
    return value

''' +s[end:]
s=s.replace("'repairable': repairable(cur), 'issues': cur.issues", "'repairable': repairable(cur), 'issues': cur.issues,\n                    'reference_space':getattr(cur,'reference_space','canonical')")
s=s.replace("'repairable': True, 'issues': [schema_issue(cur)]", "'repairable': True, 'issues': getattr(cur,'response_contract_issues',None) or schema_issues([cur]),\n                    'reference_space':'canonical'")
p.write_text(s)
edit('schema_preparation.py',"error = best_match(validator.iter_errors(instance))\n            if error is not None:\n                raise error", "errors = list(validator.iter_errors(instance))\n            error = best_match(errors)\n            if error is not None:\n                from .output_contract import schema_issues\n                error.response_contract_issues = schema_issues(errors)\n                raise error")
edit('navigation_input.py',"try:Draft202012Validator(wire_schema).validate(value)\n        except ValidationError as exc:raise ProposalError('invalid request-local selection at '+str(list(exc.absolute_path))+': '+exc.message) from exc", "from .output_contract import validate_shape\n        validate_shape(value,wire_schema,reference_space='wire')")
edit('navigation_input.py',"if key=='reference_registry':return deepcopy(value)", "if key=='reference_registry':return deepcopy(value)\n            # A rejected wire response already uses the exact current aliases.\n            # Never allocate/remap its unknown IDs into apparently valid choices.\n            if value.get('contract_version')=='output-contract-v1' and value.get('reference_space')=='wire':return deepcopy(value)")
edit('stable_references.py',"if key in (FIELD,'minimal_input_binding'", "if key in ('repair_contract','rejected_decision','contract_error',FIELD,'minimal_input_binding'")
# Keep errors typed, with original paths. Persisted corruption remains non-repairable.
edit('source_goal_control.py',"def validate_scope(value, *, persisted=False):", "def validate_scope(value, *, persisted=False, path='/source_targets/coordinate_scope'):")
edit('source_goal_control.py',"error = ContractError if persisted else ProposalError\n        raise error('source_targets.coordinate_scope must name a structural branch: '+', '.join(COORDINATE_SCOPES)+'. 조/항/호/목 are levels, not scopes; preserve the target and correct the scope before lookup.')", "message='source_targets.coordinate_scope must name a structural branch: '+', '.join(COORDINATE_SCOPES)+'. 조/항/호/목 are levels, not scopes; preserve the target and correct the scope before lookup.'\n        if persisted:raise ContractError(message)\n        from .output_contract import OutputContractError,issue\n        row=issue('INVALID_COORDINATE_SCOPE',path,expected={'enum':list(COORDINATE_SCOPES)})\n        row.update(received=value,message=message)\n        raise OutputContractError(message,[row])")
edit('source_goal_control.py',"for row in value.get('source_targets',[]):\n        validate_scope(row.get('coordinate_scope'))", "for index,row in enumerate(value.get('source_targets',[])):\n        validate_scope(row.get('coordinate_scope'),path='/source_targets/'+str(index)+'/coordinate_scope')")
edit('source_goal_control.py',"def resolve(inv,data,actions,payload,value,decision,expand,st):", "def resolve(inv,data,actions,payload,value,decision,expand,st,*,preselection=False):")
edit('source_goal_control.py',"terminal=decision['next_action'] in ('FINISH','PENDING','RESEARCH')", "terminal=decision['next_action'] in ('FINISH','PENDING')")
edit('source_goal_control.py',"    # A genuinely new intermediate route may investigate the unresolved goal.", "    if preselection:\n        # No exact action is available now. Keep the durable goals and receipts,\n        # but let the existing selector repair the route before any handoff.\n        inv.s.repo.event('SOURCE_GOAL_SELECTION_REQUIRED',{'goal_ids':[g['goal_id'] for g in pending],\n            'remaining_intermediate_routes':max(0,2-len(st.get('source_goal_bridges',[]))),\n            'goals_resolved':False,'model_call':False})\n        return None\n    # A genuinely new intermediate route may investigate the unresolved goal.")
edit('source_goal_control.py',"lambda value:native_decision(inv,data,actions,value),st)\n\n\ndef validate_gap_closure", "lambda value:native_decision(inv,data,actions,value),st,preselection=True)\n\n\ndef validate_recovery_choice(inv,data,actions,value):\n    \"\"\"Premature termination is a proposal error owned by the current selector.\"\"\"\n    if not enabled(inv) or value.get('choice') not in ('FINISH','PENDING'):return\n    st=state(inv,data)\n    excluded={r['goal_id'] for r in value.get('source_goal_exclusions',[])}\n    pending=[g for g in st.get('source_goals',[]) if g['status'] in ('REQUIRED','BLOCKED') and g['goal_id'] not in excluded]\n    if not pending or len(st.get('source_goal_bridges',[]))>=2:return\n    available=[k for k,a in actions.items() if a['action'] not in ('FINISH','PENDING','DECIDE')]\n    if not available:return\n    from .output_contract import OutputContractError,issue\n    row=issue('REQUIRED_SOURCE_RECOVERY_CHOICE','/choice',expected='Select a current investigation action or give a grounded source_goal_exclusions entry.')\n    row.update(received=value['choice'],goal_ids=[g['goal_id'] for g in pending],\n        message='The required original is still missing. An unsuccessful lookup does not exhaust the current investigation menu.')\n    raise OutputContractError('required source needs a bounded alternative investigation choice',[row],category='DECISION_CONFLICT')\n\n\ndef validate_gap_closure")
edit('decision_projection.py',"if goals.enabled(inv):goals.validate(value,inv,data,actions)","if goals.enabled(inv):\n            goals.validate(value,inv,data,actions)\n            goals.validate_recovery_choice(inv,data,actions,value)")
edit('law_navigation.py',"except ProgressHandoff:\n", "except ProgressHandoff as handoff:\n")
edit('law_navigation.py',"return self.bounded_result('NO_ANSWER_PROGRESS')\n                except", "return self.bounded_result(str(handoff) or 'NO_ANSWER_PROGRESS')\n                except")
print('diagnostics, wire mapping, selector recovery, exact handoff patched')
