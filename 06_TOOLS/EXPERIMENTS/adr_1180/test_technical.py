from pathlib import Path
from types import SimpleNamespace
import importlib.util
import io
import json
import sys
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
from saved_timing import Timing, collect


@pytest.fixture
def candidate(monkeypatch):
    sys.path.insert(0,str(ROOT/'02_BACKEND'))
    path = ROOT/'02_BACKEND/lawrag/research/candidates/adr_1180/chunk-cache/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/fulltext.py'
    spec = importlib.util.spec_from_file_location('semantic_runtime.adr1180_fulltext',path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls = []
    def tokenize(text):
        calls.append(text)
        return [SimpleNamespace(form=x,tag='NNG') for x in text.split(' ')]
    monkeypatch.setattr(mod.term_morph,'tokenize',tokenize)
    return mod,calls


@pytest.mark.parametrize('text',['',' ','a  b','한글 조문 내용\n반복 문구','단어 '*500,'x'*800,'\t\n'])
def test_exact_chunks(candidate,text):
    mod,calls = candidate
    expected = ' '.join(x for part in mod._index_chunks(text) for x in part.split(' '))
    assert mod._search_forms(text) == expected
    assert mod._search_forms(text) == expected


def test_repeated_chunk_hits(candidate):
    mod,calls = candidate
    a = mod._chunk_search_forms('같은 문구')
    assert mod._chunk_search_forms('같은 문구') == a
    assert calls == ['같은 문구']
    assert mod._CHUNK_FORM_STATS == {'hits':1,'misses':1}


def test_failure_not_cached(candidate,monkeypatch):
    mod,_ = candidate
    count = [0]
    def tokenize(text):
        count[0] += 1
        if count[0] == 1:
            raise RuntimeError('expected')
        return []
    monkeypatch.setattr(mod.term_morph,'tokenize',tokenize)
    with pytest.raises(RuntimeError): mod._chunk_search_forms('실패')
    assert mod._chunk_search_forms('실패') == ()
    assert count == [2]


def test_tokenizer_and_tags_bound(candidate,monkeypatch):
    mod,calls = candidate
    assert mod._chunk_search_forms('a') == ('a',)
    monkeypatch.setattr(mod,'TAGS',('OTHER',))
    assert mod._chunk_search_forms('a') == ()
    monkeypatch.setattr(mod.term_morph,'tokenize',lambda t:[SimpleNamespace(form='changed',tag='OTHER')])
    assert mod._chunk_search_forms('a') == ('changed',)
    assert len(calls) == 2


def test_eviction(candidate,monkeypatch):
    mod,calls = candidate
    monkeypatch.setattr(mod,'_CHUNK_FORM_ENTRIES',2)
    for text in ['a','b','c']:
        mod._chunk_search_forms(text)
    assert len(mod._CHUNK_FORMS) == 2
    assert mod._CHUNK_FORM_BYTES <= mod._CHUNK_FORM_LIMIT
    mod._chunk_search_forms('a')
    assert len(calls) == 4
    monkeypatch.setattr(mod,'_CHUNK_FORM_LIMIT',1)
    mod._chunk_search_forms('oversized')
    assert not any(key[-1]=='oversized' for key in mod._CHUNK_FORMS)


def log():
    rows=['PHASE INDEX','GENERATION fulltext seconds=120.500 reused=False',
          'REBUILD '+json.dumps({'phase':'reuse-inputs-build-serving','status':'DONE','elapsed_seconds':150,'total_elapsed_seconds':155}),
          'REBUILD '+json.dumps({'phase':'verify-serving-assets','status':'DONE','elapsed_seconds':10,'total_elapsed_seconds':165}),
          'PHASE RETURN',
          'PHASE '+json.dumps({'phase':'SOURCE_HASH_CHECK','elapsed_seconds':0}),
          'PHASE '+json.dumps({'phase':'EXPORT_ROWS','elapsed_seconds':20}),
          'PROGRESS '+json.dumps({'phase':'EXPORT_ROWS','elapsed_seconds':50,'cpu_seconds':30,'rows_added':1000}),
          'semantic_runtime.oracle_dp_io.DPError: QUERY_EXPORT_BLOB: source_request',
          '원문과 비밀은 요약에 포함하지 않음']
    return ('\n'.join(rows)+'\n').encode()


@pytest.mark.parametrize('size',[1,7,31,1024])
def test_fragmented_log(size):
    data=log();t=Timing()
    for i in range(0,len(data),size): t.feed(data[i:i+size])
    result=t.result()
    assert result['log_bytes']==len(data)
    assert result['completed_generation_stages'][0]['seconds']==120.5
    assert result['observed_lower_bounds']['index_observed_seconds']==165
    assert result['export_intervals_observed'][0]['observed_seconds']==20
    assert result['export_intervals_observed'][1]['observed_seconds']==30
    assert result['whole_02_seconds'] is None
    assert result['error_codes']==['QUERY_EXPORT_BLOB']
    assert '원문과 비밀' not in json.dumps(result,ensure_ascii=False)


@pytest.mark.parametrize('mode',['good','gap','overlap','missing','range'])
def test_read_only_chunks(mode):
    data=log();mid=len(data)//2;handle='a'*32
    parts=[(0,data[:mid]),(mid,data[mid:])]
    if mode=='gap':parts[1]=(mid+1,data[mid:])
    if mode=='overlap':parts[1]=(mid-1,data[mid:])
    if mode=='missing':parts=parts[:1]
    if mode=='range':parts[1]=(mid,data[mid:]+b'bad')
    chunks={f'attempts/{handle}/logs/{start:016d}.log':body for start,body in parts}
    folder=SimpleNamespace(list_paths_in_partition=lambda:list(chunks),get_download_stream=lambda p:io.BytesIO(chunks[p]))
    controller=SimpleNamespace(t=SimpleNamespace(CHUNK=1024*1024),bounded_read=lambda f,n:f.read(n+1))
    state={'value':{'compute':{'handle':handle},'log_offset':len(data),'phase':'FAILED'}}
    if mode=='good':
        result=collect(folder,controller,state)
        assert result['all_committed_logs_read'] and not result['genos_contacted'] and not result['job_restarted']
    else:
        with pytest.raises(ValueError):collect(folder,controller,state)


def test_r8_failed_phase_kept():
    t=Timing();t.feed(b'PHASE_RESULT {"phase":"RETURN","seconds":42,"status":"FAILED"}\n')
    assert t.result()['phase_results']==[{'phase':'RETURN','seconds':42,'status':'FAILED'}]


def test_unfinished_line_and_invalid_duration():
    t=Timing();t.feed(b'PHASE_RESULT {"phase":"RETURN","seconds":NaN}\nPHASE_RESULT {"phase":"INDEX"')
    assert not t.result()['phase_results']
    assert t.result()['trailing_partial_line_bytes']>0


def test_delivery_syntax_and_no_remote_mutations():
    text=(ROOT/'08_DEPLOYMENT/DATAIKU/pipeline02_timing_20261028_r1/DATAIKU_02_시간진단.txt').read_text()
    compile(text,'diagnostic','exec')
    import ast
    tree=ast.parse(text)
    # Bootstrap recipe helper is defined but never called; inspect top-level calls.
    calls=[n for row in tree.body if not isinstance(row,(ast.FunctionDef,ast.ClassDef)) for n in ast.walk(row) if isinstance(n,ast.Call)]
    assert not any(isinstance(n.func,ast.Attribute) and n.func.attr in {'upload_file','upload_stream','delete_path','set_variables','build','run'} for n in calls)
