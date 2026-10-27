"""Decode the actual request-local dictionary; never regenerate its numbering.

Read-only post-run adapter. It calls only the frozen product's presentation
codecs. No model, source acquisition, policy, prompt or answer is modified.
"""
from copy import deepcopy
import json


def restore(compact_expected,wire,receipt):
    from semantic_runtime.contracts import digest
    from semantic_runtime.legal_agent.errors import ContractError
    from semantic_runtime.legal_agent import model_input_projection as mp
    from semantic_runtime.legal_agent import navigation_values as nv
    from semantic_runtime.legal_agent.navigation_input import expand_cards
    if 'navigation_values' not in receipt:
        return mp.restore_wire_view(compact_expected,wire,receipt)
    if receipt['navigation_values']!=nv.VERSION or digest(wire)!=receipt.get('wire_view_sha256'):
        raise ContractError('actual wire reference dictionary binding differs')
    if type(receipt.get('navigation_cards_expanded',False)) is not bool:
        raise ContractError('invalid stored navigation expansion mode')
    decoded=nv.expand(wire)
    base={'messages':[{'role':'user','content':mp.encoded({'view':compact_expected})}]}
    direct=mp._view(mp.without_judgment_pool(base))[1]['view']
    for value in (compact_expected,direct):
        for scopes in (True,False):
            for guidance in (False,True):
                codec=mp.Projection(value,share_scopes=scopes,hide_guidance=guidance,
                    share_values=False,bind_scopes='bound_scope_references' in receipt)
                keys=('version','canonical_view_sha256','expanded_view_sha256',
                    'scope_references','server_metadata_fields','stage_guidance_fields')
                if any(codec.receipt[k]!=receipt.get(k) for k in keys):continue
                if len(codec.bound_scopes)!=receipt.get('bound_scope_references',0):continue
                expected=(expand_cards(codec.pre_values,expand_shared=False)
                          if receipt.get('navigation_cards_expanded') else codec.pre_values)
                if digest(decoded)!=digest(expected):continue
                # Independent source/state binding plus exact restoration of
                # hidden integrity metadata; no hash or permission bypass.
                return codec.verify(compact_expected,codec.wire)
    raise ContractError('actual transmitted values differ from saved presentation')


def test_rejection(expected,wire,receipt):
    """A caller must not pass corrupted content by merely updating its wire hash."""
    from semantic_runtime.contracts import digest
    from semantic_runtime.legal_agent.errors import ContractError
    changed=deepcopy(wire);changed['injected_scope']='forged'
    for update_hash in (False,True):
        r=deepcopy(receipt)
        if update_hash:r['wire_view_sha256']=digest(changed)
        try:restore(expected,changed,r)
        except ContractError:pass
        else:raise AssertionError('corrupted wire was accepted')
    stale=deepcopy(expected);stale['base_state_revision']=stale.get('base_state_revision',0)+1
    try:restore(stale,wire,receipt)
    except ContractError:pass
    else:raise AssertionError('stale source view was accepted')
