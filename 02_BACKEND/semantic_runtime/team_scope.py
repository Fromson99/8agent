"""Resolve team selection from generation-bound document metadata, never an ACL."""
import json
import re
import threading
from types import MappingProxyType
from . import observability as obs
from .contracts import digest

log = obs.get_logger('team_scope')
_CACHE = {}
_LOCK = threading.Lock()


def generation_key(store):
    if hasattr(store, 'check_unchanged'):
        store.check_unchanged()
        return ('catalogue-v2', *store.binding_signature(), getattr(store, '_projected_team_binding', None))
    # In-memory adapters are request-local; never borrow another adapter's data.
    return ('catalogue-v2', id(store), digest(store.manifest), getattr(store, '_projected_team_binding', None))


def bind_projected_teams(store, projection):
    """Explicit hash-bound SourceSet membership for legacy unassigned documents.

    This selection metadata grants no access and never overrides native teams.
    The caller loads the projection through the pinned serving profile.
    """
    if projection is None or not projection.get('team_memberships'):
        for name in ('_projected_team_binding', '_projected_teams'):
            if hasattr(store, name): delattr(store, name)
        return
    if any(projection.get(key) != store.manifest[key] for key in ('generation_id', 'store_sha256')):
        raise ValueError('stale team source projection')
    memberships = {}
    if not isinstance(projection['team_memberships'], dict):
        raise ValueError('projected team membership map required')
    for did, teams in projection['team_memberships'].items():
        if did in getattr(getattr(store, 'selection', None), 'excluded', ()):
            continue
        row = store.db.execute('SELECT source_artifact_sha256,json FROM document WHERE document_id=?', (did,)).fetchone()
        origin = projection.get('documents', {}).get(did)
        if not row or not origin or origin.get('status') != 'verified' or origin.get('source_artifact_sha256') != row[0]:
            raise ValueError('team source projection provenance mismatch')
        metadata = json.loads(row[1]).get('document_metadata') or {}
        if any(location.get('team') for location in [metadata, *metadata.get('aliases', [])] if isinstance(location, dict)):
            raise ValueError('team source projection cannot override native teams')
        if not isinstance(teams, list) or not teams or len(teams) != len(set(teams)):
            raise ValueError('explicit unique projected teams required')
        for team in teams:
            validate_team_id(team)
        memberships[did] = frozenset(teams)
    store._projected_team_binding = digest(projection)
    store._projected_teams = MappingProxyType(memberships)


def prepared_catalogue(store):
    key = generation_key(store)
    with _LOCK:
        oracle=getattr(store,'is_oracle_query',False)
        if not oracle and key in _CACHE:
            obs.event(log, 'catalogue.cache.hit', cache_hit=True, document_count=len(_CACHE[key]['ids']))
            return _CACHE[key]
        from .document_roles import role_of_metadata
        if hasattr(store, 'path'):
            from .storage import verify_store_binding
            verify_store_binding(store.path/'store.sqlite', store.manifest['store_sha256'])
        teams, roles = {}, {}
        with obs.step(log, 'team.metadata_scan'):
            for did, raw in store.db.execute("SELECT document_id,json_extract(json,'$.document_metadata') FROM document"):
                metadata = json.loads(raw) if raw else {}
                metadata = metadata or {}
                locations = [metadata, *metadata.get('aliases', [])]
                teams[did] = frozenset(location['team'] for location in locations
                    if isinstance(location, dict) and isinstance(location.get('team'), str)
                    and re.fullmatch(r'[A-Za-z0-9_-]+_team', location['team']))
                if did in getattr(store, '_projected_teams', {}):
                    teams[did] = store._projected_teams[did]
                roles[did] = role_of_metadata(metadata)
        if generation_key(store) != key:
            raise ValueError('source changed during catalogue preparation')
        value = MappingProxyType({'ids': frozenset(teams), 'teams': MappingProxyType(teams),
                                  'roles': MappingProxyType(roles)})
        if not oracle:
            _CACHE.clear()  # One generation per worker; no connections or request state.
            _CACHE[key] = value
        obs.event(log, 'catalogue.cache.ready', cache_hit=False, document_count=len(teams), sql_count=1)
        return value


def document_teams(store):
    return prepared_catalogue(store)['teams']


def validate_team_id(team_id):
    if not isinstance(team_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+_team', team_id):
        raise ValueError('team_id must be an exact team folder name, for example risk_team')


def select_documents(store, team_id):
    validate_team_id(team_id)
    selected = sorted(did for did, teams in document_teams(store).items() if team_id in teams)
    if not selected:
        raise ValueError('team_id has no documents in this generation: '+team_id)
    return selected


def catalogue(store):
    membership = document_teams(store)
    return {'generation_id': store.manifest['generation_id'],
            'teams': [{'team_id': team, 'document_count': sum(team in ts for ts in membership.values())}
                      for team in sorted(set().union(*membership.values()))],
            'unassigned_document_count': sum(not ts for ts in membership.values()),
            'selection_policy': 'selected-team-only; shared glossary; not an access grant'}
