"""Ontology model metadata, after exact server-side source binding checks.

Opaque anchor identities and hashes remain in the approved snapshot, acquired
plan, source journal and review receipt. Human labels, semantic values and all
selectable source references remain literal. This module performs no I/O.
"""
from copy import deepcopy

VERSION = 'ontology-prompt-payload-v1'
ANCHOR_PROOF = {'document_id', 'version', 'unit_id', 'content_sha256'}


def payload(value):
    def project(item, key=None):
        if isinstance(item, list):
            return [project(row) for row in item]
        if not isinstance(item, dict):
            return deepcopy(item)
        if key == 'anchor' and ANCHOR_PROOF <= set(item) and 'label' in item:
            return {k: deepcopy(v) for k, v in item.items() if k not in ANCHOR_PROOF}
        return {k: project(v, k) for k, v in item.items()}
    result = project(value)
    result.pop('bundle_sha256', None)
    return result
