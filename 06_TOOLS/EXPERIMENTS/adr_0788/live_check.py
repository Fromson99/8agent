"""Four frozen synthetic product calls; no internal source or screenshot export."""
from pathlib import Path
import json,os
import pytest
from test_navigation_delivery_recovery import tree,session,ready,decision,apply,conflict
from semantic_runtime.legal_agent import law_navigation as ln
from semantic_runtime.legal_agent.output_contract import diagnostics
from lawrag.research.experiment_client import ExperimentClient

@pytest.mark.parametrize('prior',[False,True],ids=['unadopted_insufficient','adopted_insufficient'])
def test_synthetic_model_choice(session,prior):
    inv,data,actions=ready(session)
    if prior:
        v=decision(data,'FINISH');v['next_action']='DECIDE';apply(inv,v,data,actions)
    inv.p['issues'].append({'id':'Q2','question':'제공 원문에 없는 신고기한은 며칠인가?',
        'request_quote':'승인 기준','required':True})
    data,actions=inv.view();captured={}
    class Captured(Exception):pass
    def capture(system,view,schema,phase,timeout):
        captured.update(system=system,view=view,schema=schema);raise Captured()
    inv.invoke=capture
    with pytest.raises(Captured):inv.request_decision(data,actions,'source-law-navigation-2')
    out=Path(os.environ['ADR_LIVE_OUTPUT'])/('adopted_insufficient' if prior else 'unadopted_insufficient')
    out.mkdir(parents=True,exist_ok=False)
    client=ExperimentClient(Path(__file__).resolve().parents[3],out/'raw',max_calls=1,max_output_tokens=6400,max_repairs=0)
    result={'case':out.name,'calls':0,'valid':False,'error':None,'source':'synthetic fixture only','legal_quality_certified':False}
    try:
        value=client.generate(captured['system'],captured['view'],captured['schema'],phase='navigation')
        result['proposal']=value
        try:inv.validate(value,data,actions);result['valid']=True
        except Exception as exc:result['error']={'type':type(exc).__name__,'message':str(exc),'diagnostics':diagnostics(exc)}
    except Exception as exc:
        result['error']={'type':type(exc).__name__,'message':str(exc)}
    result.update(calls=client.calls,usage=client.usage)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    # Operational execution, not a retrospective quality gate. Raw observations persist.
    assert client.calls==1
