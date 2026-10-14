"""Derive case binding from frozen code/config/data without calling a model."""
from pathlib import Path
import sys,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification';D=A/'artifacts/design'
b=json.loads((D/'bindings.json').read_text());code=R/b['stage'];out=A/'artifacts/binding-check';out.mkdir(exist_ok=False)
sys.path.insert(0,str(code/'02_BACKEND'));sys.dont_write_bytecode=True
from semantic_runtime.app import create_app
from semantic_runtime.legal_agent.local_gemma import LocalGemmaTransport
from semantic_runtime.legal_agent.unified_runtime import open_cases
transport=LocalGemmaTransport(code,R)
profile=json.loads((code/'00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json').read_text());profile['model_binding']=transport.binding
app=create_app(out,R/b['source_generation'],contracts_root=code,workspace_root=R,provider=object(),
    implementation='legal-agent-unified-v6',legal_agent_profile=profile,legal_agent_transport=transport,
    runtime_root=out/'runtime',memory_identity=lambda _:None)
cases=open_cases(app.state.pipeline,out/'runtime',{}, {'user_id':'binding-check','team_id':'public-laws','document_ids':list(transport.public_scope)})
try:(out/'expected.json').write_text(json.dumps({'binding':cases.executor.binding,'model_calls':0},ensure_ascii=False,indent=2)+'\n')
finally:cases.close();app.state.pipeline.store.close()
print('Expected runtime binding derived without model calls')
