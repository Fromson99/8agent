from semantic_runtime import fulltext


def test_automatic_workers_preserves_large_input_parallelism():
    assert fulltext.automatic_workers(0)==1
    assert fulltext.automatic_workers(16*1024*1024)==1
    assert fulltext.automatic_workers(16*1024*1024+1)==2
