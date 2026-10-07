"""Bulk transport/ledger contracts with scripted responses only, never real model calls."""
from contextlib import closing
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

import pytest
from semantic_runtime.contracts import digest, sha, write
from lawrag.pipeline import glossary_review as review
from test_genos_meaning_variants import prepared, reference_calls, tool as variants

ROOT = Path(__file__).resolve().parents[2]
sys.modules['genos_meaning_variants'] = variants
spec = importlib.util.spec_from_file_location('meaning_bulk', ROOT / '06_TOOLS/OFFLINE/genos_meaning_bulk_v2.py')
bulk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bulk)


def settings(**values):
    return {'batch_size':32,'workers':4,'max_tokens':8192,'timeout':120,
            'max_request_chars':105000,'split_retries':2,'index_reserve_hours':12, **values}


def jobs(context):
    with closing(review.v1.read_db(context['parent'] / 'review/review.sqlite')) as db:
        return [dict(r) for r in db.execute('SELECT * FROM job ORDER BY id')]


class Fake:
    def __init__(self, output, mode='normal'):
        self.output, self.mode = output, mode
        self.calls = self.active = self.maximum = 0
        self.lock = threading.Lock()
        self.models = {'llm':'synthetic-contract'}
    def prepare(self): return {'backend':'genos','model':'synthetic-contract'}
    def request(self, kind, path, request, role):
        assert request['max_tokens'] == 8192
        with self.lock:
            self.calls += 1; self.active += 1; self.maximum = max(self.maximum,self.active)
        try:
            time.sleep(.01)
            data = json.loads(request['messages'][1]['content'])['context']
            rows = [{'job_key': j['job_key'],
                     'identity': {'decision':'SAME','evidence_ids':j['fields']['evidence']['evidence_refs']},
                     'relation_assessment':'NOT_ESTABLISHED','relations':[],
                     'rationale':'모의 근거 검사','missing_information':''} for j in data['jobs']]
            value = {'results':rows}
            if self.mode == 'transport': raise RuntimeError('scripted server outage')
            if self.mode == 'cross' and len(rows)>1:
                first = data['jobs'][0]['fields']['evidence']['evidence_refs']
                foreign = next(e for e in data['evidence'] if e not in first)
                rows[0]['identity']['evidence_ids'] = [foreign]
            content = json.dumps(value,ensure_ascii=False)
            if self.mode == 'duplicate': content = content[:-1] + ',"results":[]}'
            finish = 'length' if self.mode == 'split' and len(rows)>1 else 'stop'
            raw = {'choices':[{'finish_reason':finish,'message':{'content':content}}]}
            folder = self.output / uuid.uuid4().hex; folder.mkdir(parents=True)
            write(folder / 'request.json',request); write(folder / 'response.json',raw)
            write(folder / 'receipt.json',{'request_sha256':sha(folder/'request.json'),
                                          'response_sha256':sha(folder/'response.json'),'model':'synthetic-contract'})
            return raw, {'path':str(folder/'receipt.json'),'sha256':sha(folder/'receipt.json')}
        finally:
            with self.lock: self.active -= 1


def test_original_review_remains_immutable_and_bulk_fork_resumes_without_calls(prepared, tmp_path, reference_calls):
    original = {p:sha(p) for p in (prepared['parent']/'review').iterdir() if p.is_file()}
    context = bulk.fork(prepared,settings(batch_size=2))
    assert context['parent'] != prepared['parent']
    assert bulk.fork(prepared,settings(batch_size=2)) == context
    fake = Fake(tmp_path/'calls')
    result = bulk.worker(context,settings(batch_size=2),provider=fake)
    assert result['completed'] and fake.maximum == 2
    assert fake.calls == 2
    summary = review.inspect(context['parent']/'review')
    assert summary['jobs']['complete'] == summary['total_jobs'] == 4
    proof = json.loads((context['parent']/'review/bulk-status.json').read_text())
    assert proof['physical_calls_all_runs'] == 2 and proof['logical_job_attempts_all_runs'] == 4
    assert all(sha(p)==pin for p,pin in original.items())
    assert bulk.worker(context,settings(batch_size=2),provider=fake)['cached']
    assert fake.calls == 2
    on = variants.build_variant(context,'on')
    off = variants.build_variant(context,'off')
    assert on['reference_llm'] and off['reference_llm'] and len(reference_calls)==2
    with sqlite3.connect(Path(on['generation_path'])/'navigation/navigation.sqlite') as db:
        assert any(json.loads(r[0]).get('code')=='SAME' for r in db.execute('SELECT json FROM edge'))
    shared = tmp_path/'shared'; shared.mkdir()
    assert bulk.VERSION in json.loads((context['parent']/'origin.json').read_text())['identity']['schema_version']
    assert prepared['parent'].name in variants.publish(Path(off['release_path']),shared)['path']


def test_pack_is_lossless_with_source_spans_and_scopes(prepared):
    original = jobs(prepared)
    value,schema,bindings,inverse = bulk.pack(original)
    def restore(v):
        if isinstance(v,str): return inverse.get(v,v)
        if isinstance(v,list): return [restore(x) for x in v]
        if isinstance(v,dict): return {k:restore(x) for k,x in v.items()}
        return v
    for row,job in zip(value['jobs'],original):
        rebuilt = {}
        for name,v in row['fields'].items():
            if isinstance(v,dict) and 'pool_ref' in v: rebuilt[name] = value['pool'][v['pool_ref']]
            elif isinstance(v,dict) and 'source_refs' in v: rebuilt[name] = {k:value['sources'][k] for k in v['source_refs']}
            elif isinstance(v,dict) and 'evidence_refs' in v: rebuilt[name] = [value['evidence'][k] for k in v['evidence_refs']]
            else: rebuilt[name] = v
        assert restore(rebuilt) == json.loads(job['input_json'])
    assert 'job_id' not in schema['properties']['results']['items']['properties']


@pytest.mark.parametrize('bad', ['{"a":1,"a":2}','{"x":NaN}','```json\n{}\n```','{}\n{}'])
def test_strict_parser_rejects_duplicate_keys_constants_prose_and_extra_object(bad):
    with pytest.raises(bulk.BatchJSONError): bulk.strict_json(bad)


def test_truncated_batch_splits_boundedly_and_preserves_physical_failures(prepared,tmp_path):
    fake = Fake(tmp_path/'calls','split')
    result,count = bulk.call_batch(fake,jobs(prepared),settings(),tmp_path/'audit')
    assert count == fake.calls == 7
    assert all('value' in row for row in result.values())
    assert len(list((tmp_path/'audit').glob('*/outcome.json')))==7
    assert sum(json.loads(p.read_text())['status']=='FAILED' for p in (tmp_path/'audit').glob('*/outcome.json'))==3


def test_cross_job_evidence_rejected_even_when_global_alias_is_valid(prepared,tmp_path):
    fake = Fake(tmp_path/'calls','cross')
    result,count = bulk.call_batch(fake,jobs(prepared),settings(),tmp_path/'audit')
    assert count == 1 and any('error' in row for row in result.values())
    assert any('value' in row for row in result.values())


def test_invalid_envelope_never_records_success(prepared,tmp_path):
    fake = Fake(tmp_path/'calls','duplicate')
    result,count = bulk.call_batch(fake,jobs(prepared),settings(),tmp_path/'audit')
    assert count == 7 and all('error' in row for row in result.values())


def test_missing_or_repeated_job_alias_rejects_entire_envelope(prepared):
    value,schema,bindings,inverse = bulk.pack(jobs(prepared))
    item = {'job_key':'J1','identity':{'decision':'UNKNOWN','evidence_ids':[]},
            'relation_assessment':'UNKNOWN','relations':[],'rationale':'모의','missing_information':'미확정'}
    for rows in ([item],[item,item]):
        with pytest.raises(bulk.BatchJSONError,match='Missing, duplicate'):
            bulk.validate_response({'results':rows},schema,bindings,inverse)


def test_configuration_drift_and_read_only_status_do_not_overwrite(prepared):
    assert bulk.fork(prepared,settings(),create=False) is None
    context = bulk.fork(prepared,settings())
    with pytest.raises(ValueError,match='configuration/code changed'):
        bulk.fork(prepared,settings(workers=2))
    assert bulk.fork(prepared,settings(),create=False)==context


def test_transport_failure_not_split_and_failed_results_preserved(prepared,tmp_path):
    context = bulk.fork(prepared,settings())
    fake = Fake(tmp_path/'calls','transport')
    result = bulk.worker(context,settings(),provider=fake)
    assert fake.calls == 1 and result['review_status']=='PARTIAL'
    assert review.inspect(context['parent']/'review')['jobs']['failed']==4
    with sqlite3.connect(context['parent']/'review/review.sqlite') as db:
        assert 'scripted server outage' in db.execute("SELECT error FROM job LIMIT 1").fetchone()[0]


def test_outage_circuit_stops_before_draining_queue_and_preserves_original(prepared,tmp_path):
    context = bulk.fork(prepared,settings(batch_size=1,workers=1))
    original_sha = sha(prepared['parent']/'review/review.sqlite')
    rows = jobs(context)
    with sqlite3.connect(context['parent']/'review/review.sqlite') as db:
        for n in range(8):
            row = rows[0]
            db.execute('INSERT INTO job VALUES (?,?,?,?,?,?,?,?,?)',
                       (digest(['synthetic-repeat',n]), row['external_id'],row['target_id'],row['input_json'],
                        row['input_sha256'],'pending',None,None,None))
    fake = Fake(tmp_path/'calls','transport')
    with pytest.raises(KeyboardInterrupt,match='Three fully failed'):
        bulk.worker(context,settings(batch_size=1,workers=1),provider=fake)
    assert fake.calls == 3
    summary = review.inspect(context['parent']/'review')
    assert summary['jobs']['failed']==3 and summary['jobs']['pending']==9
    assert not (context['parent']/'review/completion.json').exists()
    assert sha(prepared['parent']/'review/review.sqlite')==original_sha


def test_handoff_compiles_exact_embedded_core_and_bulk_sources():
    path = ROOT/'08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt'
    text = path.read_text()
    code = text.split("<<'GENOS_BULK_PY'\n",1)[1].rsplit('\nGENOS_BULK_PY',1)[0]
    compile(code,str(path),'exec')
    core_line = next(line for line in code.splitlines() if line.startswith('CORE_SOURCE = '))
    import ast
    assert ast.literal_eval(core_line.split(' = ',1)[1]) == (ROOT/'06_TOOLS/OFFLINE/genos_meaning_variants.py').read_text()
    bulk_source = code.split('variants_module.__dict__)\n',1)[1]
    assert bulk_source == (ROOT/'06_TOOLS/OFFLINE/genos_meaning_bulk_v2.py').read_text()
    assert 'GENOS_VARIANTS_BATCH:-32' in text and 'GENOS_VARIANTS_WORKERS:-4' in text
    assert '.venv/bin/python' not in text
    assert 'python3 -u -' in text and '_atomic_json(Path(os.environ' in text
    subprocess.run(['bash','-n',str(path)],check=True)


def test_embedded_default_review_runs_through_publish_with_only_scripted_models(prepared,tmp_path,monkeypatch,reference_calls):
    path = ROOT/'08_DEPLOYMENT/GENOS/handoffs/financial_union_20260930_r4/GENOS_MEANING_VARIANTS_R2_BULK_UTF8.txt'
    code=path.read_text().split("<<'GENOS_BULK_PY'\n",1)[1].rsplit('\nGENOS_BULK_PY',1)[0]
    monkeypatch.setitem(sys.modules,'genos_meaning_variants',variants)
    monkeypatch.setenv('GENOS_VARIANTS_TOOL_PATH',str(path))
    fake=Fake(tmp_path/'calls')
    monkeypatch.setattr(review,'provider_for',lambda state:fake)
    namespace={'__name__':'scripted_bundle','__file__':str(path)}
    exec(compile(code,str(path),'exec'),namespace)
    shared=tmp_path/'shared'; shared.mkdir()
    assert namespace['main'](['review','--data-root',str(prepared['parent'].parents[1]),'--run-id','prepared',
                              '--shared-root',str(shared)])==0
    assert fake.calls==1 and len(reference_calls)==1
    selector=shared/'prepared-bulk-r2-meaning-on/rag-selection.json'
    assert selector.is_file() and json.loads(selector.read_text())['reference_llm']
    assert not (shared/'CURRENT.json').exists()
