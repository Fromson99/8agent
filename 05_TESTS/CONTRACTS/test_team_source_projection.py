"""Pinned legacy SourceSet membership cannot override native teams or grant ACL."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
import pytest
from semantic_runtime.team_scope import bind_projected_teams, document_teams, select_documents

@pytest.fixture
def source():
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE document(document_id,name,source_artifact_sha256,json)')
    db.executemany('INSERT INTO document VALUES(?,?,?,?)', [('legacy','공개보충원문','legacy-hash','{}'),
        ('native','팀원문','native-hash',json.dumps({'document_metadata': {'team': 'risk_team'}}))])
    store = SimpleNamespace(db=db, manifest={'generation_id': 'g1', 'store_sha256': 'store-hash'})
    projection = {'generation_id': 'g1', 'store_sha256': 'store-hash', 'documents': {
        'legacy': {'status': 'verified', 'source_artifact_sha256': 'legacy-hash'},
        'native': {'status': 'verified', 'source_artifact_sha256': 'native-hash'}},
        'team_memberships': {'legacy': ['financial_team','risk_team']}}
    yield store, projection
    db.close()

def test_rebind_unassigned_original_preserves_native_membership_and_source_bytes(source):
    store, projection = source
    before = store.db.execute('SELECT * FROM document ORDER BY document_id').fetchall()
    assert document_teams(store)['legacy'] == frozenset()
    bind_projected_teams(store, projection)
    assert select_documents(store, 'financial_team') == ['legacy']
    assert select_documents(store, 'risk_team') == ['legacy','native']
    assert store.db.execute('SELECT * FROM document ORDER BY document_id').fetchall() == before
    changed = deepcopy(projection); changed['team_memberships']['legacy'] = ['financial_team']
    bind_projected_teams(store, changed)
    assert select_documents(store, 'risk_team') == ['native']
    bind_projected_teams(store, None)
    assert document_teams(store)['legacy'] == frozenset()
    with pytest.raises(ValueError, match='no documents'): select_documents(store, 'financial_team')

@pytest.mark.parametrize('field,value', [('generation_id','g2'), ('store_sha256','different')])
def test_stale_generation_is_rejected(source,field,value):
    store, projection = source; projection[field] = value
    with pytest.raises(ValueError, match='stale'): bind_projected_teams(store, projection)

def test_forged_source_and_native_override_are_rejected(source):
    store, projection = source
    bad = deepcopy(projection); bad['documents']['legacy']['source_artifact_sha256'] = 'forged'
    with pytest.raises(ValueError, match='provenance'): bind_projected_teams(store, bad)
    bad = deepcopy(projection); bad['team_memberships'] = {'native': ['financial_team']}
    with pytest.raises(ValueError, match='override'): bind_projected_teams(store, bad)
    assert not hasattr(store, '_projected_teams')

@pytest.mark.parametrize('teams', [[], ['risk_team','risk_team'], ['../risk_team'], ['not-a-team']])
def test_invalid_projected_selection_cannot_be_admitted(source,teams):
    store, projection = source; projection['team_memberships']['legacy'] = teams
    with pytest.raises(ValueError): bind_projected_teams(store, projection)

def test_external_default_scope_intersects_team_and_public_approval(source):
    from semantic_runtime.app import external_documents
    store, projection = source; bind_projected_teams(store, projection)
    assert external_documents(None, ['legacy','native'], store, 'financial_team') == ['legacy']
    assert external_documents(None, ['native'], store, 'risk_team') == ['native']
    with pytest.raises(ValueError, match='unapproved'):
        external_documents(None, ['native'], store, 'financial_team')
    with pytest.raises(ValueError, match='unapproved'):
        external_documents(['private'], ['legacy','native'], store, 'risk_team')
    # Explicit cross-team inputs reach the existing strict Pipeline.plan check;
    # the admission helper does not silently drop a requested source.
    assert external_documents(['native'], ['legacy','native'], store, 'financial_team') == ['native']
