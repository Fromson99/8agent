"""Keep original streaming assertions with MAIN87 read-choice/assessment fixture replies."""
import json
import pytest
import test_genos_output_unlimited as legacy
from test_source_span_norm import proposal
from test_legal_agent_double_harness import wire
from semantic_runtime.legal_agent.navigation_input import expand_cards
tree=legacy.tree

@pytest.mark.parametrize('fail',[False,True])
def test_current_uncapped_stream_and_interruption(tmp_path,tree,monkeypatch,fail):
    class CurrentRich(legacy.RichTransport):
        def send_once(self,*,body,ticket):
            view=expand_cards(json.loads(body['messages'][1]['content'])['view'])
            phase=view.get('source_stage',view.get('phase',''))
            if '-read-choice' in phase:
                self.phases.append(phase)
                if view['sources']:
                    return wire({'choice':'FINISH','basis_refs':[s['id'] for s in view['sources']],
                        'issue_refs':[i['id'] for i in view['issues']],'evidence_sufficient':True,'reason':'요청 원문 확인'})
                return wire({'choice':'READ','selections':[{'target':view['read_candidates'][0]['target'],
                    'issue_id':view['issues'][0]['id'],'missing_need':'요청 조문 원문','relation':'DIRECT','source_ref':None}]})
            if phase.startswith('memory-assess'):
                self.phases.append(phase)
                ref=next(o['id'] for o in view['evidence_options'] if '승인 후 보고한다.' in o['text'])
                value=proposal('승인 후 보고한다.','OBLIGATION',[ref],ref)
                value.pop('disposition')
                for row in value['issue_assessments']:row.pop('reason')
                return wire(value)
            return super().send_once(body=body,ticket=ticket)
    monkeypatch.setattr(legacy,'RichTransport',CurrentRich)
    legacy.test_native_streaming_output_is_uncapped_and_interruption_never_publishes(tmp_path,tree,fail)
