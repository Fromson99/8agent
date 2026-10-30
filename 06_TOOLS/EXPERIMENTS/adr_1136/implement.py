from pathlib import Path
import json
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_1136/framework-r1';T=Path(__file__).parent
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
S=C/'snapshot';L=S/'02_BACKEND/semantic_runtime/legal_agent'
def edit(p,a,b):
 s=p.read_text();assert a in s,(p,a);p.write_text(s.replace(a,b))
# One explicit feature gate. Disabled requests never consult stored ontology data.
edit(L/'law_candidates.py',"'ontology_context': {'mode':'A0'},", "'ontology_enabled': False, 'ontology_context': {'mode':'A0'},")
edit(L/'law_candidates.py',"    from .ontology_context import configuration\n", "    if type(result['ontology_enabled']) is not bool:raise ContractError('ontology_enabled must be bool')\n    from .ontology_context import configuration\n")
edit(L/'ontology_context.py',"def config(inv):\n    value", "def enabled(policy):\n    return policy.get('ontology_enabled') is True and policy.get('ontology_context', {}).get('mode', 'A0') != 'A0'\n\n\ndef config(inv):\n    if not enabled(inv.policy):\n        return {'mode': 'A0'}\n    value")
edit(L/'ontology_assessment.py',"return (policy.get('ontology_direct_assessment') is True", "return (context.enabled(policy) and policy.get('ontology_direct_assessment') is True")
edit(L/'law_navigation.py',"self.policy.get('ontology_context',{}).get('mode','A0')!='A0'", "self.policy.get('ontology_enabled') is True and self.policy.get('ontology_context',{}).get('mode','A0')!='A0'")
# Generic offline authoring supports a separately approved publication, without upgrading research records.
p=L/'ontology_scenarios.py';s=p.read_text();line=next(x for x in s.splitlines() if x.startswith('AUTHORITY =') or x.startswith('AUTHORITY='));s=s.replace(line,line+"\nAPPROVED_AUTHORITY = 'APPROVED_SOURCE_SCENARIOS'")
s=s.replace("recipe['authority']!=AUTHORITY", "recipe['authority'] not in (AUTHORITY, APPROVED_AUTHORITY)")
s=s.replace("    sources=_index(originals,'originals')", "    if recipe['authority']==APPROVED_AUTHORITY and not (isinstance(recipe['authoring'],dict) and isinstance(recipe['authoring'].get('approval_ref'),str) and recipe['authoring']['approval_ref'].strip()):raise ContractError('approved scenario requires approval reference')\n    sources=_index(originals,'originals')")
s=s.replace("'authority':AUTHORITY,'bundle_id':recipe['bundle_id']", "'authority':recipe['authority'],'bundle_id':recipe['bundle_id']")
s=s.replace("package.get('authority')!=AUTHORITY", "package.get('authority') not in (AUTHORITY, APPROVED_AUTHORITY)")
s=s.replace("    _index(package['paths'],'paths');", "    if package['authority']==APPROVED_AUTHORITY and not (isinstance(package.get('authoring'),dict) and isinstance(package['authoring'].get('approval_ref'),str) and package['authoring']['approval_ref'].strip()):raise ContractError('approved scenario requires approval reference')\n    _index(package['paths'],'paths');")
p.write_text(s)
edit(L/'ontology_context.py',"from .ontology_scenarios import verify_package\n        verify_package(value['scenario_package'])", "from .ontology_scenarios import verify_package, APPROVED_AUTHORITY\n        package=verify_package(value['scenario_package'])\n        if package['authority'] != APPROVED_AUTHORITY:\n            raise ContractError('runtime scenario requires approved publication; research data is not loadable')")
# Explicitly published synthetic fixtures only; no actual ontology data enters serving inventory.
edit(T/'test_scenario_native.py',"package=sc.compile_package(recipe,originals)", "recipe['authority']=sc.APPROVED_AUTHORITY;recipe['authoring']={'approval_ref':'synthetic-contract-only'}\n    package=sc.compile_package(recipe,originals)")
# Include module identities in durable request binding.
newmods=sorted(p.name for p in L.glob('ontology_*.py'))
edit(L/'unified_rag.py',"'completion_budget.py','memory_binding.py')", "'completion_budget.py','memory_binding.py',"+','.join(repr(n) for n in newmods)+")")
p=S/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json';v=read(p);v['candidate_navigation'].update(ontology_enabled=False,ontology_context={'mode':'A0'},ontology_direct_assessment=True);put(p,v)
# Operator switch applies through the common service profile path, local and Oracle.
p=S/'service.py'
edit(p,"def _investigation_profile(value):", "def _ontology_environment():\n    raw = os.environ.get('GENOS_RAG_ONTOLOGY_ENABLED', '').strip().lower()\n    if not raw:return None\n    if raw in ('on', 'true', '1'):return True\n    if raw in ('off', 'false', '0'):return False\n    raise ValueError('GENOS_RAG_ONTOLOGY_ENABLED must be on or off')\n\n\ndef _ontology_status(value):\n    policy = value.get('candidate_navigation', {})\n    context = policy.get('ontology_context', {'mode': 'A0'})\n    enabled = policy.get('ontology_enabled') is True\n    configured = context.get('mode', 'A0') != 'A0'\n    return {'enabled': enabled, 'data_configured': configured,\n            'active': enabled and configured,\n            'fallback': 'ordinary-rag' if not (enabled and configured) else None}\n\n\ndef _investigation_profile(value):")
edit(p,"    return result\n\n\ndef _investigation_budget", "    ontology = _ontology_environment()\n    if ontology is not None:\n        result['candidate_navigation']['ontology_enabled'] = ontology\n        if ontology:result['candidate_navigation']['ontology_direct_assessment'] = True\n    return result\n\n\ndef _investigation_budget")
edit(p,"        _BINDING=dict(_APP.binding)\n", "        _BINDING=dict(_APP.binding)\n        _BINDING.update(ontology_environment=_ontology_environment(), ontology=_ontology_status(_APP.profile))\n    elif (_BINDING or {}).get('ontology_environment') != _ontology_environment():\n        raise RuntimeError('ontology setting changed; restart this process')\n")
edit(p,"    if _APP is not None:\n        from semantic_runtime.oracle_dp", "    if _APP is not None:\n        if (_BINDING or {}).get('ontology_environment') != _ontology_environment():\n            raise RuntimeError('ontology setting changed; restart this process')\n        from semantic_runtime.oracle_dp")
edit(p,"            binding.update(\n                investigation_budget", "            binding.update(\n                ontology_environment=_ontology_environment(),\n                ontology=_ontology_status(options['legal_agent_profile']),\n                investigation_budget")
print('Implemented gate, published scenario contract and service binding')
