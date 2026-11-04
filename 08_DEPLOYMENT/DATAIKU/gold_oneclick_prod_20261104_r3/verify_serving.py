"""Fresh-process read-only integration check for a disposable Flow publication."""
from pathlib import Path
import json
import sys

REPO=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(REPO/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'))
import connect


def main():
    work=Path(sys.argv[1]);credentials=Path(sys.argv[2])
    report=json.loads((work/'report.json').read_text())
    documents=json.loads((work/'documents.json').read_text())
    profile=json.loads((work/'embedding-profile.json').read_text())
    calls=[]
    def encode(text):calls.append(text);return [1.,0.,0.,0.]
    with connect.open_store(mapping=work/'serving-mapping.json',mapping_sha256=report['serving_mapping_sha256'],
                            credentials=credentials,documents=[documents[0]],release_id=report['query_release_id'],
                            embedding=encode,embedding_profile=profile) as (store,request,transport):
        from semantic_runtime import initial_vector
        from semantic_runtime.initial_vector import VectorError
        assert request.sources.document(documents[0])
        retriever=initial_vector.Retriever(request)
        value=retriever.search('합성 검증',documents=[documents[0]])
        assert value['rows'] and all(r['DOC_ID']==documents[0] for r in value['rows'])
        assert retriever.search('합성 검증',documents=[documents[0]])==value and len(calls)==1
        assert not retriever.search('합성 검증',documents=[documents[0]],source_ids=[])['rows']
        assert not retriever.search('합성 검증',documents=[documents[0]],source_ids=['absent-source'])['rows']
        try:retriever.search('합성 검증',documents=documents)
        except VectorError:pass
        else:raise AssertionError('vector ACL accepted unauthorized document')
        from plain_vector import install
        install(None,encode,dict(profile,revision='wrong'))
        count=len(calls)
        try:initial_vector.Retriever(request).search('합성 검증',documents=[documents[0]])
        except VectorError:pass
        else:raise AssertionError('wrong embedding profile accepted')
        assert len(calls)==count
        print(json.dumps({'status':'PASS','sql_calls':len(transport.statements),'embedding_stub_calls':len(calls)},ensure_ascii=False))


if __name__=='__main__':main()
