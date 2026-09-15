"""LLM glossary wiring with synthetic providers only; no semantic quality claims."""
from contextlib import closing
import json
import sqlite3
from pathlib import Path
import pytest
from .test_glossary_assembly import assembly_inputs,setup
from lawrag.pipeline import glossary_assembly as a,glossary_review as r,glossary_enrichment as e
from .test_glossary_scope import Fake as Collector


@pytest.fixture
def review_inputs(assembly_inputs,tmp_path):
    a.build(*assembly_inputs,emit=lambda *a,**k:None)
    state=tmp_path/'review'
    r.prepare(assembly_inputs[-1],state)
    return assembly_inputs[-1],state,tmp_path/'reviewed'


class Fake:
    def __init__(self,change=None):self.calls=0;self.change=change
    def prepare(self):return {'backend':'synthetic','model':'fixture','endpoint':'no-network'}
    def call(self,role,task,context,schema):
        self.calls+=1
        evidence=context['left_sense']['evidence_ids']+context['right_sense']['evidence_ids']
        result={'job_id':context['job_id'],'input_sha256':context['input_sha256'],
                'identity':{'decision':'DIFFERENT','evidence_ids':evidence},
                'relation_assessment':'IDENTIFIED','relations':[{'kind':'RELATED_TO','evidence_ids':evidence}],
                'rationale':'합성 응답으로 연결 계약만 검사함','missing_information':''}
        if self.change:self.change(result)
        return result,{'backend':'synthetic','model':'fixture','usage':{'input_tokens':1,'output_tokens':1}}


def test_prepare_skips_pending_collection_and_never_calls_provider(review_inputs):
    glossary,state,_=review_inputs
    report=r.inspect(state)
    assert report['attempts']==0 and report['total_jobs']>0
    assert report['deferred']['WAITING_FOR_RELATIONS']==1
    assert report['deferred']['NEEDS_SOURCE_EVIDENCE']>0
    assert report['job_types']=={'MEANING_CHECK':report['total_jobs']}
    assert a.inspect(glossary)['llm_calls']==0
    with pytest.raises(ValueError,match='exists'):r.prepare(glossary,state)


def test_budget_resume_and_compile_draft_preserve_official_relations(review_inputs):
    glossary,state,output=review_inputs
    original=a.inspect(glossary)['dictionary_sha256'];fake=Fake()
    first=r.run(state,max_jobs=1,provider=fake)
    assert fake.calls==first['attempts']==1
    r.run(state,max_jobs=100,provider=fake)
    calls=fake.calls
    r.run(state,max_jobs=100,provider=fake)
    assert fake.calls==calls
    report=r.compile_proposals(state,output)
    assert report['canonical_approval'] is False and report['counts']['meaning']==0
    assert report['llm_calls']==calls
    assert a.inspect(glossary)['dictionary_sha256']==original
    with sqlite3.connect(output/'dictionary.sqlite') as db:
        assert db.execute('SELECT count(*) FROM llm_review_v3').fetchone()[0]==calls
        context=json.loads(db.execute('SELECT input_json FROM llm_review_v3 LIMIT 1').fetchone()[0])
        assert context['left_sense']['evidence_ids'] and context['right_sense']['evidence_ids']
        assert db.execute("SELECT count(*) FROM external_candidate WHERE status IN ('MODEL_REVIEWED_PROPOSALS','MODEL_REVIEW_PARTIAL')").fetchone()[0]>0
        assert db.execute('SELECT code FROM official_relation').fetchone()[0]=='140303'
    assert a.inspect(output,'신탁')['entries']
    with pytest.raises(ValueError,match='exists'):r.compile_proposals(state,output)


@pytest.mark.parametrize('bad',['job','quote','side','extra','insufficient'])
def test_rejects_invalid_outputs_and_requires_explicit_retry(review_inputs,bad):
    _,state,_=review_inputs
    def change(value):
        if bad=='job':value['job_id']='invented'
        elif bad=='quote':value['identity']['quote']='없는 원문을 지어냄'
        elif bad=='side':value['identity']['evidence_ids']=[]
        elif bad=='extra':value['new_legal_term']='창작한 법률용어'
        else:value['identity'].update(decision='UNKNOWN')
    with pytest.raises(RuntimeError,match='stopped'):r.run(state,max_jobs=1,provider=Fake(change))
    assert r.inspect(state)['jobs']['failed']==1
    with closing(r.ledger(state/'review.sqlite')) as db:
        failed=db.execute("SELECT id FROM job WHERE status='failed'").fetchone()[0]
    good=Fake();r.run(state,max_jobs=100,provider=good)
    assert r.inspect(state)['jobs']['failed']==1
    r.run(state,max_jobs=100,retry_failed=True,provider=good)
    assert 'failed' not in r.inspect(state)['jobs']
    with closing(r.ledger(state/'review.sqlite')) as db:
        assert db.execute('SELECT count(*) FROM attempt WHERE job_id=?',(failed,)).fetchone()[0]==2


def test_insufficient_evidence_is_not_approval(review_inputs):
    _,state,output=review_inputs
    def unknown(v):
        v['identity']={'decision':'UNKNOWN','evidence_ids':[]}
        v.update(relations=[],relation_assessment='UNKNOWN',missing_information='같은 표기의 적용 범위를 확인할 자료 부족')
    fake=Fake(unknown)
    r.run(state,max_jobs=100,provider=fake)
    result=r.compile_proposals(state,output)
    assert result['llm_review']['decisions']['UNKNOWN']>0
    assert result['counts']['membership']==0


def test_input_and_result_hash_binding(review_inputs):
    _,state,output=review_inputs
    r.run(state,max_jobs=100,provider=Fake())
    with closing(r.ledger(state/'review.sqlite')) as db:
        row=db.execute("SELECT id,result_json FROM job LIMIT 1").fetchone();value=json.loads(row['result_json']);value['input_sha256']='bad'
        db.execute('UPDATE job SET result_json=? WHERE id=?',(json.dumps(value),row['id']));db.commit()
    with pytest.raises(ValueError,match='another job'):r.compile_proposals(state,output)
    assert not output.exists()


def test_description_mentions_never_create_candidates_even_after_collection_completion(assembly_inputs,tmp_path):
    collection,external,corpus,output=assembly_inputs
    file=external/'econedu/entries.jsonl'
    rows=[json.loads(line) for line in file.open()]
    next(x for x in rows if x['id']=='econedu:gap')['definition']='신탁의 구조를 이용하는 합성 금융 표현'
    file.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
    with closing(e.connect(collection)) as db:e.collect(db,Collector(),emit=lambda *a,**k:None)
    a.build(*assembly_inputs,emit=lambda *a,**k:None)
    state=tmp_path/'gap-review';plan=r.prepare(output,state)
    assert 'GAP_PROPOSAL' not in plan['job_types']
    assert plan['deferred']['NO_EXPLICIT_LINK']==1
    assert 'WAITING_FOR_RELATIONS' not in plan['deferred']
    r.run(state,max_jobs=100,provider=Fake())
    target=tmp_path/'gap-output';r.compile_proposals(state,target)
    with sqlite3.connect(target/'dictionary.sqlite') as db:
        assert db.execute("SELECT count(*) FROM external_candidate WHERE basis='DEFINITION_MENTION_LLM_PROPOSAL'").fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM meaning').fetchone()[0]==0


def test_real_genos_adapter_uses_only_llm_transport_with_fake_http(review_inputs,monkeypatch):
    from semantic_runtime import genos
    _,state,_=review_inputs
    calls=[]
    def from_env(kind):
        calls.append(kind)
        return genos.endpoint('https://unit.invalid',token='synthetic'), 'fixture-qwen'
    monkeypatch.setattr(genos,'from_env',from_env)
    monkeypatch.setattr(genos,'advertised_model',lambda target,configured:configured)
    def request(target,path,payload):
        assert path=='/chat/completions' and payload['model']=='fixture-qwen'
        context=json.loads(payload['messages'][1]['content'])['context']
        value,_=Fake().call('role','task',context,r.SCHEMA)
        return {'model':'fixture-qwen','choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}],
                'usage':{'prompt_tokens':5,'completion_tokens':5}}
    monkeypatch.setattr(genos,'request_json',request)
    r.run(state,max_jobs=1)
    assert calls==['llm']
    assert r.inspect(state)['jobs']['complete']==1
    assert list((state/'calls').glob('*/receipt.json'))



def test_genos_compile_accepts_relocated_identical_glossary(review_inputs,tmp_path):
    import shutil
    glossary,state,output=review_inputs
    r.run(state,max_jobs=100,provider=Fake())
    relocated=tmp_path/'genos-copy'
    shutil.copytree(glossary,relocated)
    result=r.compile_proposals(state,output,glossary=relocated)
    assert result['llm_review']['source_glossary_sha256']==a.inspect(glossary)['dictionary_sha256']
    with (relocated/'dictionary.sqlite').open('ab') as f:f.write(b'tampered')
    with pytest.raises(ValueError,match='hash mismatch'):
        r.compile_proposals(state,tmp_path/'bad-output',glossary=relocated)


def test_transport_subset_retains_full_local_validation(review_inputs):
    from jsonschema.exceptions import ValidationError
    schema=r.transport_schema()
    assert 'maxItems' not in json.dumps(schema)
    assert 'minLength' not in json.dumps(schema)
    assert schema['properties']['identity']['properties']['decision']['enum']==r.SCHEMA['properties']['identity']['properties']['decision']['enum']
    _,state,_=review_inputs
    with closing(r.ledger(state/'review.sqlite')) as db:
        job=dict(db.execute('SELECT * FROM job LIMIT 1').fetchone())
    context=json.loads(job['input_json'])
    value,_=Fake().call('role','task',{'job_id':job['id'],'input_sha256':job['input_sha256'],**context},schema)
    value['identity']['evidence_ids']=value['identity']['evidence_ids']*30
    with pytest.raises(ValidationError):r.validate(value,job,context)
