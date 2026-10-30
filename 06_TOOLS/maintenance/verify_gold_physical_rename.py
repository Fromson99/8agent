"""Verify the default Gold connector after the explicitly requested name change."""
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261030-gold-physical-rename'
sys.path.insert(0, str(ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'))
sys.dont_write_bytecode = True
import connect


def main():
    logging.disable(logging.CRITICAL)
    result = {'model_calls': 0, 'embedding_calls': 0, 'verification_data_writes': 0, 'checks': []}
    with connect.open_store(seconds=180, max_calls=500) as (store, request, transport):
        cfg = store.gold_ports.mapping
        assert cfg.revision == '20261030-photo-names-preserved-types-r1'
        assert cfg.column('DOC_VER', 'DOC_ID') == 'RGLT_DOC_ID'
        assert cfg.column('VCTR_HEAD', 'CHAN_NO') == 'CHAN_ORD'
        assert cfg.column('VCTR_ITEM', 'EMBD_VCTR_VALU') == 'EMBD_VCTR'
        store.selection.require_latest()
        result.update(mapping=store.gold_ports.preflight, query_release_id=request.release_id,
                      documents=len(request.sources.allowed), binding=request.sql.binding)
        result['checks'].append('default_active_mapping_and_actual_13_tables_60_columns')
        did = sorted(request.sources.allowed)[0]
        document = request.sources.document(did)
        block = request.sources.blocks(did, limit=1)['rows'][0]
        anchor = {'document_id': did, 'version': document['source_artifact_sha256'], 'unit_id': block['unit_id']}
        text = store.gold_ports.source_reader(anchor)
        assert block['text'] in text
        result['checks'].append('mapped_original_document_block_unit_and_source_hash')
        from semantic_runtime.ontology_work import runtime as ontology_runtime
        assert ontology_runtime.repository() is store.gold_ports.ontology
        assert store.gold_ports.ontology.lookup(anchor, {did}) == []
        result['checks'].append('ontology_request_wired_and_real_data_empty')
        glossary = store.gold_ports.glossary_binding()
        try:
            page = glossary.reader.lookup('이사회', limit=1)
            assert page['concepts']
            first = page['concepts'][0]
            ref = glossary.restore(first['source'], first['node_id'])
            store.gold_ports.ontology.glossary_validator([ref])
        finally:
            glossary.reader.close()
        result['checks'].append('mapped_query_and_glossary_reference_exact_restore')
        from gold_connection import VectorReader
        parent = SimpleNamespace(release_id=request.records.manifest['extension']['base_query_id'],
                                 snapshot=request.snapshot, sql=request.sql, sources=request.sources)
        reader = VectorReader(parent, cfg)
        head = reader.active()
        meta = reader.metadata(head['VCTR_POST_ID'])
        row = request.sql.query('SELECT VECTOR_SERIALIZE(EMBD_VCTR_VALU RETURNING CLOB) AS V FROM ' +
                                cfg.table('VCTR_ITEM') + ' WHERE VCTR_POST_ID=:pub AND DOC_ID=:did FETCH FIRST 1 ROWS ONLY',
                                [('pub', head['VCTR_POST_ID'], 'VARCHAR2'), ('did', did, 'VARCHAR2')], limit=1)[0]
        vector = json.loads(row['V'])
        hits = reader.search(vector, profile_sha256=meta['completion']['profile_sha256'], documents={did}, limit=3)
        assert len(vector) == 1024 and hits and all(r['DOC_ID'] == did for r in hits)
        result['checks'].append('new_vector_column_exact_search_scope_and_publication_binding')
        import engine_runtime
        class StoredVector:
            def __init__(self, profile):
                self.calls = 0
            def encode(self, question):
                return vector
        previous = engine_runtime.LocalEncoder
        engine_runtime.LocalEncoder = StoredVector
        try:
            native = engine_runtime.Retriever(request).search('physical rename SQL contract', set(request.sources.allowed))
        finally:
            engine_runtime.LocalEncoder = previous
        assert len(native['rows']) == 100 and all(r['DOC_ID'] in request.sources.allowed for r in native['rows'])
        result['checks'].append('native_packed_search_vector_join_100_candidates')
        result.update(sql_calls=request.sql.calls, vector_dimensions=len(vector), vector_rows=len(hits),
                      native_vector_rows=len(native['rows']), ontology_publications_consumed=0,
                      vector_input='existing stored vector; no new question embedding')
    result['status'] = 'PASS_NEW_PHYSICAL_NAMES_DEFAULT_CONNECTOR'
    (OUT / 'consumer-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
