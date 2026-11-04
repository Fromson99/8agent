"""Publication and read-time verification of model-selected exact source bindings."""
import json
from ..contracts import digest
from ..storage import verify_store_binding
from .repository import text_hash
from .errors import ContractError


def validate_saved(repo,result):
    if repo.VERSION==6:
        from .unified_publication import validate_saved as validate_case
        return validate_case(repo,result)
    bundle=result.get('assembly',{}).get('term_agent',{}).get('source_bundle')
    if repo.VERSION not in (4,5): return
    if not bundle or bundle.get('schema_version')!='source-tiers-v4': raise ContractError('v4 requires source bundle')
    from .tiers_protocol import validate
    if repo.VERSION == 5:
        from .workflow_tiers_protocol import validate
    validate('FinalSourceBundle',bundle)
    if digest({k:v for k,v in bundle.items() if k!='bundle_hash'})!=bundle.get('bundle_hash'):
        raise ContractError('source bundle hash mismatch')
    if bundle['selection_revision']!=digest(repo.heads('source_selection')) or bundle['binding_hash']!=repo.run()['binding_hash']:
        raise ContractError('source selection changed; rebuild bundle before publication')
    saved=repo.head('source_bundle',bundle['goal_id'])['payload']
    if saved!=bundle: raise ContractError('source bundle differs from journal')
    for card in bundle['sources']:
        h=repo.head('source_selection',card['selection_id'],expected=card['selection_version'])
        p=h['payload']
        if p['status']!='SELECTED' or p['tier']!=card['tier'] or p['view_id']!=card['view_id']:
            raise ContractError('card is not a current model selection')
        if [(s['span_id'],s['block_id'],s['start_cp'],s['end_cp']) for s in card['spans']]!=[(s['span_id'],s['block_id'],s['start_cp'],s['end_cp']) for s in p['basis_spans']]:
            raise ContractError('card selected ranges mismatch')


def validate_current(repo,result,store,*,allowed_documents=None):
    if repo.VERSION==6:
        from .unified_publication import validate_current as validate_case
        return validate_case(repo,result,store,allowed_documents=allowed_documents)
    validate_saved(repo,result)
    if repo.VERSION not in (4,5):return
    oracle=getattr(store,'is_oracle_query',False)
    if oracle: store.check_unchanged()
    current=store.manifest if oracle else json.loads((store.path/'manifest.json').read_text())
    for key in ('generation_id','store_sha256','export_allowed'):
        if current[key]!=repo.binding[key]: raise ContractError('source binding changed before publication/open')
    try:
        if not oracle: verify_store_binding(store.path/'store.sqlite', current['store_sha256'])
    except ValueError as exc:
        raise ContractError('source store changed') from exc
    allowed=set(current['scope']['document_version_ids'])
    if oracle: allowed &= store.oracle_request.sources.allowed
    if allowed_documents is not None: allowed &= set(allowed_documents)
    if set(repo.binding['scope']['document_version_ids'])-allowed:
        raise ContractError('request source scope no longer authorized')
    for c in result['assembly']['term_agent']['source_bundle']['sources']:
        if c['document_id'] not in allowed or c['document_id'] not in repo.binding['scope']['document_version_ids']:
            raise ContractError('selected source no longer authorized')
        doc=store.db.execute('SELECT name,source_artifact_sha256 FROM document WHERE document_id=?',(c['document_id'],)).fetchone()
        if not doc or doc[0]!=c['document_name'] or doc[1]!=c['source_artifact_hash']:raise ContractError('source metadata changed')
        for p in c['spans']:
            raw=store.source(c['document_id'],p['block_id'])
            if (raw['source_artifact_sha256']!=c['source_artifact_hash'] or text_hash(raw['text'])!=p['block_hash'] or
                raw['text'][p['start_cp']:p['end_cp']]!=p['text'] or text_hash(p['text'])!=p['span_hash']):
                raise ContractError('source excerpt mismatch')
