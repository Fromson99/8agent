from copy import deepcopy
from types import SimpleNamespace
import pytest
from workflow import presentation
from workflow.contracts import WorkflowError

@pytest.mark.parametrize('change,included',[
 ({},True),({'side':'internal'},False),({'document_id':'other'},False),({'source_id':'other'},False),
 ({'parent_issue_refs':['other']},False),({'parent_issue_refs':['other','q']},True),
 ({'source_complete':False},True),({'version_verified':False},True)])
def test_original_context_does_not_bypass_boundaries_or_require_semantic_approval(monkeypatch,change,included):
 head=dict(evidence_id='selected',side='external',document_id='doc',source_id='source',parent_issue_refs=['q'])
 sibling={**head,'evidence_id':'context',**change};state={'immutable':True}
 def originals(ctx,s,ids=None):return deepcopy([head,sibling] if ids is None else [head])
 monkeypatch.setattr(presentation,'evidence',originals)
 got=presentation.source_context(None,state,{'selected'},'q')
 assert ('context' in got)==included
 assert 'selected' in got and state=={'immutable':True}
