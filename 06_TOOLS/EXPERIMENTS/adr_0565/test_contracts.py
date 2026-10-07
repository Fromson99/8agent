import json
import pytest
from fixtures import OPS, OTHER, PROOF, PURPOSE, SCOPE, ToolAdapter, build, load


@pytest.fixture(scope='module')
def m():
    return load()


@pytest.mark.parametrize('name,operation', list(OPS.items()))
def test_six_operations_apply_one_db_ontology_relation(m,tmp_path,name,operation):
    g=build(m,tmp_path/'g.sqlite'); tool=ToolAdapter(name,operation)
    result=tool.execute(g)
    assert result['node_ids']==['node-A','node-B']
    assert result['policy']['excluded_by']==[{'node_id':'node-C','resource_id':'resource:C','class_id':'class:C','relation_id':'relation:exclude-C'}]
    assert tool.executions[0]['allowed_node_ids']==['node-A','node-B']
    g.close()


def test_policy_persists_and_reopens_without_prompt(m,tmp_path):
    path=tmp_path/'g.sqlite'; g=build(m,path); g.close(); g=m.Graph(path)
    assert ToolAdapter('any-search','discover').execute(g)['node_ids']==['node-A','node-B']
    assert g.db.execute("SELECT source,predicate,target FROM current_relation WHERE id='relation:exclude-C'").fetchone()[:]==(PURPOSE,'EXCLUDES','class:C')
    g.close()


def test_different_tool_name_same_access_operation(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    assert ToolAdapter('vector_provider_changed','discover').execute(g)['node_ids']==['node-A','node-B']
    g.close()


def test_data_class_hierarchy_inherits_exclusion(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite',child=True)
    r=ToolAdapter('browse','list').execute(g)
    assert r['node_ids']==['node-A','node-B'] and r['policy']['excluded_by'][0]['class_id']=='class:C-child'
    g.close()


def test_renamed_projection_nodes_keep_same_ontology(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite',rename=True)
    assert ToolAdapter('browse','list').execute(g,projection='generation-2')['node_ids']==['changed-node-A','changed-node-B']
    edge=dict(g.db.execute('SELECT * FROM current_relation').fetchone())
    assert 'changed-node' not in json.dumps(edge) and 'generation-2' not in json.dumps(edge)
    g.close()


def test_other_purpose_can_access_C(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    assert ToolAdapter('browse','list').execute(g,purpose=OTHER)['node_ids']==['node-A','node-B','node-C']
    assert ToolAdapter('read','read').execute(g,purpose=OTHER,targets=['node-C'])['node_ids']==['node-C']
    g.close()


def test_proposed_relation_is_not_a_constraint(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite',status='PROPOSED')
    assert ToolAdapter('browse','list').execute(g)['node_ids']==['node-A','node-B','node-C']
    g.close()


@pytest.mark.parametrize('facts,expected',[(None,3),({'transaction':'other'},3),({'transaction':'acquisition'},2)])
def test_conditional_relation_uses_current_known_facts(m,tmp_path,facts,expected):
    g=build(m,tmp_path/'g.sqlite',conditions={'transaction':'acquisition'})
    assert len(ToolAdapter('search','discover').execute(g,facts=facts)['node_ids'])==expected
    g.close()


def test_no_context_keeps_normal_scope_and_unknown_context_rejected(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    assert ToolAdapter('browse','list').execute(g,purpose=None)['node_ids']==['node-A','node-B','node-C']
    with pytest.raises(ValueError,match='unknown ontology'):
        ToolAdapter('browse','list').execute(g,purpose='invented-purpose')
    g.close()


def test_permission_scope_cannot_be_expanded_by_graph(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    assert ToolAdapter('browse','list').execute(g,scope={'resource:A'})['node_ids']==['node-A']
    with pytest.raises(m.AccessDenied):
        ToolAdapter('read','read').execute(g,scope={'resource:A'},targets=['node-B'])
    g.close()


def test_direct_read_of_excluded_C_never_calls_backend(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite'); t=ToolAdapter('read','read')
    with pytest.raises(m.AccessDenied):
        t.execute(g,targets=['node-C'])
    assert t.executions==[]
    g.close()


@pytest.mark.parametrize('kwargs',[{'drift':True},{'unknown':True}])
def test_changed_origin_or_unknown_classification_requires_revalidation(m,tmp_path,kwargs):
    g=build(m,tmp_path/'g.sqlite',**kwargs); t=ToolAdapter('search','discover')
    with pytest.raises(m.RevalidationRequired,match='classification missing or source version changed'):
        t.execute(g)
    assert not t.executions
    g.close()


def test_mixed_classification_does_not_silently_remove_potential_rule(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    origin=g.db.execute("SELECT origin_sha256 FROM membership WHERE resource_id='resource:C'").fetchone()[0]
    g.classify('resource:C','class:A',origin,proof=PROOF)
    with pytest.raises(m.RevalidationRequired,match='mixed data'):
        ToolAdapter('search','discover').execute(g)
    g.close()


def test_class_cycles_and_invalid_endpoint_types_rejected(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite',child=True)
    with pytest.raises(ValueError,match='cycle'):
        g.relate('cycle','class:C','IS_A','class:C-child',proof=PROOF,status='ACTIVE')
    with pytest.raises(ValueError,match='endpoint types'):
        g.relate('bad','class:C','EXCLUDES','class:A',proof=PROOF,status='ACTIVE')
    g.close()


def test_rule_retirement_is_new_version_and_keeps_history(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    g.relate('relation:exclude-C',PURPOSE,'EXCLUDES','class:C',proof=PROOF,status='RETIRED')
    assert ToolAdapter('browse','list').execute(g)['node_ids']==['node-A','node-B','node-C']
    assert g.db.execute("SELECT count(*) FROM relation WHERE id='relation:exclude-C'").fetchone()[0]==2
    g.close()


def test_backend_cannot_return_C_after_allowlist_is_applied(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    with pytest.raises(m.AccessDenied,match='backend returned'):
        g.access(PURPOSE,'generation-1',SCOPE,'discover',lambda op,allowed:['node-C'])
    g.close()


def test_provenance_tamper_and_stale_projection_rejected(m,tmp_path):
    g=build(m,tmp_path/'g.sqlite')
    with pytest.raises(m.RevalidationRequired,match='unknown current data'):
        ToolAdapter('read','read').execute(g,projection='old')
    g.db.execute("UPDATE relation SET proof_json='{}'"); g.db.commit()
    with pytest.raises(m.RevalidationRequired,match='provenance hash'):
        ToolAdapter('browse','list').execute(g)
    g.close()
