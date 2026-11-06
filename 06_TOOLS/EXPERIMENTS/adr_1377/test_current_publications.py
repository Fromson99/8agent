"""Use the synthetic provider's current wire grammar for the existing native publication cases."""
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec
import json
import pytest
from conftest import term_glossary
from test_wiki_workspace import env, ws
from test_wiki_workspace_native import test_workspace_native_api_delivery_and_revocation as native
import test_legal_agent_double_harness as harness
from semantic_runtime.legal_agent import need_continuity, source_goal_control
from semantic_runtime.legal_agent.bounded_source_session import _Gateway
ROOT=Path(__file__).resolve().parents[3]
spec=spec_from_file_location('assigned_review_fixture',ROOT/'06_TOOLS/EXPERIMENTS/adr_1363/test_assignments.py')
assigned=module_from_spec(spec);spec.loader.exec_module(assigned)

@pytest.mark.parametrize('mode',['active','withdraw_during_assess','withdraw_on_replay'])
def test_current_native_publication(env,ws,tmp_path,term_glossary,monkeypatch,mode):
    assigned.prior.prior.per_original_wire.__wrapped__(monkeypatch)
    encode=harness.wire
    project=source_goal_control.model_projection
    request=_Gateway.request
    current={}
    def projection(schema):
        result=project(schema)
        wire=result[0]
        current['fields']=set(wire.get('properties',{})).union(*(b.get('properties',{}) for b in wire.get('anyOf',[])))
        return result
    def capture(self,phase,view,schema_name,**kwargs):
        result=request(self,phase,view,schema_name,**kwargs)
        if view.get('source_stage','').startswith('memory-assess'):
            current['question']=view['read_judgments']['need_continuity']['question']
        return result
    def wire(value):
        v=need_continuity.scope_claim_model_copy(value)
        review=v.get('read_judgment_review',{})
        scopes=review.pop('scope_reviews',None)
        if scopes is not None:
            refs={}
            for row in scopes:
                for group in row['groups']:
                    refs.setdefault(group['basis_refs'][0],group)
            review['original_reviews']={f'R{i}':group for i,group in enumerate(refs.values(),1)}
            assigned.assign(review)
        for row in review.get('judgments',[]):
            for purpose in (row.get('change_review') or {}).get('purpose_reviews',[]):
                purpose.pop('claim_refs',None)
        for row in review.get('needs',[]):
            if row.get('status')=='NOT_NEEDED' and 'scope_quote' in row:
                q=current['question'];quote=row.pop('scope_quote')
                if not quote:row['exclusion_basis']='ORIGINALS'
                elif quote==q:row['exclusion_basis']='CURRENT_REQUEST'
                else:
                    start=q.index(quote)
                    row.update(exclusion_basis='REQUEST_SPAN',quote_span={'start_cp':start,'end_cp':start+len(quote)})
        for field in ('source_targets','source_goal_exclusions'):
            if v.get(field)==[] and field not in current.get('fields',set(v)):v.pop(field)
        return encode(v)
    monkeypatch.setattr(harness,'wire',wire)
    monkeypatch.setattr(_Gateway,'request',capture)
    monkeypatch.setattr(source_goal_control,'model_projection',projection)
    native(env,ws,tmp_path,term_glossary,monkeypatch,mode)
