"""The automatic projection must retain each decision and its own source and recorded judgment."""
from copy import deepcopy
from pathlib import Path
import gzip
import json
import pytest
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.ontology_work.wiki_projection import compile_selection
from test_wiki_workspace import env, ws, seed, projection_generator


@pytest.mark.parametrize('fault', ['none', 'switch-owner', 'foreign-basis', 'rewrite', 'lost-judgment', 'fifth-valid', 'no-inclusion'])
def test_owned_build_through_workspace(env, ws, fault):
    item = seed(env, ws)
    extra = ws.apply(change_id='original-only', raw_ids=[item.raw['bundle_id']], operations=[{
        'op':'ADD_STATEMENT','target':'@context','value':{
        'text':'다른 절차의 맥락', 'origin_refs':[], 'source_basis':ws.item(item.sid)['content']['source_basis'], 'open_items':[]}}])
    other = extra['handles']['@context']
    calls, projects, reviews = [], [], []
    old_fixture = projection_generator(env, item, calls)
    def generate(prompt, context, schema):
        if context.get('operation') == 'WIKI_SELECT':
            options = context['statement_options']
            reviews.append(options)
            answer = {}
            for key, option in options.items():
                decisions=schema['properties'][key]['properties']['decision']['enum']
                assert ('INCLUDED' in decisions) == bool(option['observation_refs'])
                answer[key] = {'decision':'INCLUDED' if option['observation_refs'] and fault!='no-inclusion' else 'CONTEXT_ONLY',
                               'reason':'입력 목적에 따라 확인한 판단 또는 참고 원문'}
            return answer, {'review':True}
        if context.get('operation') != 'WIKI_PROJECT':
            return old_fixture(prompt, context, schema)
        included=context['included_statements']
        assert len(included)==1
        ref, = included
        old_context = {**context, 'statements':[ws.item(item.sid)]}
        old, receipt=old_fixture(prompt,old_context,schema)
        result=old['accumulation']
        graph_node, = result['graph']['nodes']
        link, = result.pop('norm_links')
        graph_node['source_norm']={k:v for k,v in link.items() if k!='node_id'}
        origin={'statement':ref,'basis':graph_node.pop('basis'),'observation_refs':graph_node.pop('observation_refs')}
        del graph_node['text'], graph_node['slots']['statement']
        result['graph']['nodes']=[{'origin':origin, 'node':graph_node}]
        projects.append(context)
        if fault=='switch-owner':
            origin['statement']=next(k for k in reviews[0] if k!=ref)
        if fault=='foreign-basis':
            origin['basis'][0]['quote']='not verified in any selected original'
        if fault=='rewrite':
            graph_node['text']='다른 문장'
        if fault=='lost-judgment' or (fault=='fifth-valid' and len(projects)<5):
            origin['observation_refs']=[]
        return result, receipt
    ws.generate = generate
    args=dict(statement_ids=[item.sid,other],purpose='원문 규칙 재사용',profile_id=env.profile_id,
              profile_work_hash=env.profile_work_hash,originals=[env.source])
    if fault in ('none','fifth-valid'):
        row=compile_selection(env.w,ws,**args)
        stored=env.w.load(row['bundle_id'])
        coverage={r['statement_id']:r for r in stored['workspace_projection']['coverage']}
        assert coverage[item.sid]['node_ids']==['N1'] and coverage[other]['node_ids']==[]
        assert env.w.preview(row['bundle_id'])['paths'][0]['body']==ws.item(item.sid)['content']['text']
        assert compile_selection(env.w,ws,**args)['reused']
        assert len(projects)==(1 if fault=='none' else 5)
    else:
        with pytest.raises(ContractError):
            compile_selection(env.w,ws,**args)
        with pytest.raises(ContractError):
            compile_selection(env.w,ws,**args)
        assert len(projects)==(0 if fault=='no-inclusion' else 5)
    assert len(reviews)==1
