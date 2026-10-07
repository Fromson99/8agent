"""Explicit candidate imports. No registry/default-path discovery."""
from contextlib import contextmanager
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys

R=Path(__file__).resolve().parents[3]
C=R/'02_BACKEND/lawrag/research/candidates/adr_0576'
A=R/'04_EXPERIMENTS/ADR/ADR-0576-guide-direct-retrieval-shortcut'
for p in [R/'02_BACKEND',R/'05_TESTS',R/'05_TESTS/CONTRACTS']:
    sys.path.insert(0,str(p))
sys.dont_write_bytecode=True

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

MODULES=[('semantic_runtime.action_memory_store','02_BACKEND/semantic_runtime/action_memory_store.py'),('lawrag.core.action_memory','02_BACKEND/lawrag/core/action_memory.py'),
    ('lawrag.pipeline.action_memory','02_BACKEND/lawrag/pipeline/action_memory.py'),
    ('semantic_runtime.legal_agent.gateway','02_BACKEND/semantic_runtime/legal_agent/gateway.py'),('semantic_runtime.fulltext','02_BACKEND/semantic_runtime/fulltext.py'),
    *[('semantic_runtime.legal_agent.'+n,'02_BACKEND/semantic_runtime/legal_agent/'+n+'.py') for n in
      ['source_query_planning','source_selection','source_recall_global','source_recall','workflow_tiers_policy','action_memory','bounded_source_session']],
    ('semantic_runtime.legal_agent_adapter','02_BACKEND/semantic_runtime/legal_agent_adapter.py'),('semantic_runtime.app','02_BACKEND/semantic_runtime/app.py')]

@contextmanager
def candidate(*,snapshot=False,arm='baseline'):
    selected=(R/'02_BACKEND/lawrag/research/candidates/adr_0575/integrated' if arm=='baseline'
        else C/arm.replace('_','-'))
    root=selected/'snapshot' if snapshot else selected/'revisions/rev-001/snapshot'
    if not snapshot:
        manifest=json.loads((selected/'candidate.json').read_text());rev=manifest['revisions'][-1]
        for f in rev['files']:
            assert sha(R/f['frozen_path'])==f['snapshot_sha256'],f['target_path']
    saved={};attrs={}
    try:
        for name,p in MODULES:
            parent_name,child=name.rsplit('.',1);parent=importlib.import_module(parent_name)
            saved[name]=sys.modules.get(name);attrs[name]=(parent,getattr(parent,child,None))
            spec=importlib.util.spec_from_file_location(name,root/p);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;setattr(parent,child,m);spec.loader.exec_module(m)
        yield
    finally:
        for name in reversed(list(saved)):
            if saved[name] is None: sys.modules.pop(name,None)
            else: sys.modules[name]=saved[name]
            parent,value=attrs[name];child=name.rsplit('.',1)[1]
            if value is None:
                if hasattr(parent,child): delattr(parent,child)
            else: setattr(parent,child,value)

def fixture(path):
    from conftest import term_glossary
    from test_legal_agent_double_harness import generation
    path.mkdir(parents=True,exist_ok=True)
    glossary=term_glossary.__wrapped__(path)
    return generation.__wrapped__(path,glossary)

def app(path,generation,transport,*,arm='baseline'):
    from semantic_runtime.app import create_app
    from semantic_runtime.legal_agent.workflow_tiers_policy import DEFAULT_PROFILE
    profile={**DEFAULT_PROFILE,'model_binding':transport.binding,'max_model_attempts':14,'max_tool_actions':1024,
        'output_schema_in_prompt_enabled':True,'bounded_source_selection_enabled':True,'final_review_enabled':False,'max_schema_repairs':0,'max_transport_retries':0}
    profile.update(action_memory_enabled=True,small_pool_full_originals_enabled=True,merge_bounded_question_plan_enabled=True)
    if arm in ('guide_direct','guide_compact'):
        profile['guide_direct_enabled']=True
    if arm=='guide_compact':
        profile.update(merge_bounded_question_plan_enabled=False,single_piece_plan_enabled=True)
    return create_app(path,generation,contracts_root=R,workspace_root=R,runtime_root=path/'runtime',
        provider=object(),implementation='legal-agent-tools-v5',legal_agent_profile=profile,legal_agent_transport=transport)

def phases(transport):
    return [json.loads(b['messages'][1]['content'])['view'].get('source_stage',json.loads(b['messages'][1]['content'])['view'].get('phase')) for b in transport.calls]

def synthetic_transport():
    from test_bounded_source_main import Transport
    from test_legal_agent_double_harness import wire
    from test_legal_agent_v5 import plan
    class Synthetic(Transport):
        def send_once(self,*,body,ticket):
            v=json.loads(body['messages'][1]['content'])['view'];phase=v.get('source_stage',v.get('phase'))
            if phase=='source-query-plan' and ('investigation_concepts' in v or 'question_pieces' in v):
                result=super().send_once(body=body,ticket=ticket);value=json.loads(result['body_json']['choices'][0]['message']['content'])
                if 'investigation_concepts' in v: value['query_concepts']=[v['investigation_concepts'][0]['id'] for _ in value['queries']]
                if 'question_pieces' in v: value['question_plan']=plan()
                return wire(value)
            if phase=='source-triage' and v.get('originals'):
                self.calls.append(body)
                return wire({'issues':['승인 원칙과 위임 예외'],'choices':[{'id':r[0],'reason':'승인 원칙과 위임 예외 확인'} for r in v['candidates']['rows']]})
            return super().send_once(body=body,ticket=ticket)
    return Synthetic()
