"""Authoring uses existing bounded transport; Oracle details follow NFS policy."""
from ..contracts import digest
from .. import detailed_log_storage as detail
from .authoring_model import generate as generate_once


def generate(store, actor, prompt, context, schema):
    target = store
    if detail.oracle_mode():
        class DiagnosticStore:
            def put(self, value):
                ref = detail.capture(value, kind='ontology-authoring-wire', owner=actor,
                                     ident=digest([context, schema]))
                return store.put({'version': 'ontology-authoring-wire-ref-v1',
                                  'status': value.get('status'), 'detail': ref})
        target = DiagnosticStore()
    return generate_once(target, prompt, context, schema)
