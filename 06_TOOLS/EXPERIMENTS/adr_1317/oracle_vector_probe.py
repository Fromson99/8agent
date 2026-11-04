"""Operator-only Oracle publication/encoding probe; no source-file fallback."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'02_BACKEND'), str(ROOT)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document-id', action='append', required=True, help='Authorized development document; repeat to add')
    parser.add_argument('--metadata-only', action='store_true', help='Read Oracle metadata without an embedding request')
    parser.add_argument('--question')
    args = parser.parse_args()
    if os.environ.get('DP') != 'oracle' or os.environ.get('GENOS_ORACLE_TABLE_MAPPING') != 'development_g19_1':
        parser.error('DP=oracle and GENOS_ORACLE_TABLE_MAPPING=development_g19_1 required')
    if not args.metadata_only and not args.question:
        parser.error('--question required unless --metadata-only')
    from semantic_runtime.oracle_dp import client_from_environment
    from semantic_runtime.oracle_agent_records import RecordSQL
    from semantic_runtime.oracle_query_service import environment_binding
    from semantic_runtime.oracle_query_request import open_request
    from semantic_runtime.oracle_query_vector import Retriever
    from semantic_runtime.oracle_dp_io import digest
    client = client_from_environment()
    deadline = time.monotonic()+120
    check = client.schema_map.preflight(RecordSQL(client, binding=environment_binding(), deadline=deadline))
    release = os.environ.get('DP_QUERY_RELEASE_ID', '').strip() or None
    channel = os.environ.get('DP_QUERY_CHANNEL', '').strip() or (None if release else 'main')
    req = open_request(client, connection_binding=environment_binding(), document_ids=args.document_id,
                       deadline=deadline, release_id=release, channel=channel, max_calls=200)
    reader = Retriever(req)
    head, profile = reader.publication()
    out = {'status':'METADATA_VERIFIED', 'query_release_id':req.release_id,
           'source_release_id':req.snapshot.release_id, 'dataset_version':req.snapshot.dataset_version,
           'vector_publication_id':head['VCTR_POST_ID'], 'vector_revision':head['CHAN_NO'],
           'profile':profile, 'required_GENOS_EMBED_PROFILE_SHA256':digest(profile), 'preflight':check,
           'embedding_calls':0, 'local_source_files':False}
    if not args.metadata_only:
        reader.pin = (head, profile)
        result = reader.search(args.question, args.document_id)
        verified = []
        for row in result['rows'][:5]:
            refs = req.records.page('native.source', lookup_id=row['SOURCE_ID'], limit=2)['rows']
            if len(refs) != 1 or refs[0]['document_id'] != row['DOC_ID']:
                raise RuntimeError('Vector coordinate is not in the selected native source publication')
            verified.append({'document_id':row['DOC_ID'], 'source_id':row['SOURCE_ID'], 'distance':row['DISTANCE'],
                             'heading':refs[0].get('heading')})
        out.update(status='VECTOR_QUERY_COMPLETED', candidate_count=len(result['rows']),
                   embedding_calls=result['embedding_calls'], top5=verified, truncated=result['truncated'])
    out['query_sql_calls'] = req.sql.calls
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
