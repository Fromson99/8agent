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
        return ('catalogue-v2', *store.binding_signature())
    # In-memory adapters are request-local; never borrow another adapter's data.
    return ('catalogue-v2', id(store), digest(store.manifest))


def prepared_catalogue(store):
    key = generation_key(store)
    with _LOCK:
        if key in _CACHE:
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
                roles[did] = role_of_metadata(metadata)
        if generation_key(store) != key:
            raise ValueError('source changed during catalogue preparation')
        value = MappingProxyType({'ids': frozenset(teams), 'teams': MappingProxyType(teams),
                                  'roles': MappingProxyType(roles)})
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
