"""Resolve team selection from generation-bound document metadata, never an ACL."""
import json
import re
from . import observability as obs

log = obs.get_logger('team_scope')


def document_teams(store):
    result = {}
    with obs.step(log, 'team.metadata_scan'):
        for did, raw in store.db.execute('SELECT document_id,json FROM document'):
            metadata = json.loads(raw or '{}').get('document_metadata') or {}
            # Exact duplicate locations retained by ingestion can belong to several teams.
            locations = [metadata, *metadata.get('aliases', [])]
            result[did] = frozenset(location['team'] for location in locations
                                   if isinstance(location, dict) and isinstance(location.get('team'), str)
                                   and re.fullmatch(r'[A-Za-z0-9_-]+_team', location['team']))
    obs.event(log, 'team.metadata_scan.ready', document_count=len(result))
    return result


def select_documents(store, team_id):
    if not isinstance(team_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+_team', team_id):
        raise ValueError('team_id must be an exact team folder name, for example risk_team')
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
