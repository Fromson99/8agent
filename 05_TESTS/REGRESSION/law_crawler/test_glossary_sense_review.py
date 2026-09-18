"""MAIN authoring contracts with synthetic providers. No semantic accuracy claims."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[3]
base_tests = importlib.import_module('05_TESTS.REGRESSION.law_crawler.test_glossary_assembly')
assembly_inputs, setup = base_tests.assembly_inputs, base_tests.setup


@pytest.fixture
def modules():
    from lawrag.pipeline import glossary_senses, glossary_review
    return glossary_senses, glossary_review


def bundle(s, ident, text='명시적인 설명이다. 다만 예외를 함께 보존한다.', kind='SOURCE_DEFINITION', scope='SOURCE_ONLY'):
    return s.evidence_bundle({'id':ident,'label':ident,'scope':scope},
        [{'kind':kind,'text':text,'source_text_sha256':s.text_hash(text),'provenance':{'record_id':ident}}])


def pair(s, left=None, right=None):
    left = left or bundle(s,'left'); right = right or bundle(s,'right')
    context = s.pair_context(left[0][0], right[0][0], left, right)
    job = {'id':'job-1','input_sha256':s.digest(context)}
    return job, context


def response(job, context, identity='DIFFERENT', relation='COUNTERPART_OF'):
    evidence = sorted(set(context['left_sense']['evidence_ids']+context['right_sense']['evidence_ids']))
    return {'job_id':job['id'],'input_sha256':job['input_sha256'],
            'identity':{'decision':identity,'evidence_ids':evidence if identity!='UNKNOWN' else []},
            'relation_assessment':'IDENTIFIED' if relation else 'NOT_ESTABLISHED',
            'relations':[{'kind':relation,'evidence_ids':evidence}] if relation else [],
            'rationale':'합성 출력으로 계약만 확인한다.','missing_information':'정보 부족' if identity=='UNKNOWN' else ''}


class Fake:
    def __init__(self,change=None): self.calls=0; self.change=change
    def prepare(self):return {'backend':'synthetic','model':'fixture-v3'}
    def call(self,role,task,context,schema):
        self.calls+=1
        value=response({'id':context['job_id'],'input_sha256':context['input_sha256']},context)
        if self.change:self.change(value)
        assert 'quote' not in json.dumps(schema)
        return value,{'backend':'synthetic','model':'fixture-v3'}


def test_two_axes_hydrate_exact_quotes_and_keep_exception(modules):
    s,r=modules;job,context=pair(s);value=response(job,context)
    assert r.validate(value,job,context)==value
    hydrated=s.hydrate(value,context)
    assert value['identity']['decision']=='DIFFERENT' and value['relations'][0]['kind']=='COUNTERPART_OF'
    assert 'citations' not in value['identity']
    assert any('예외' in c['quote'] for c in hydrated['identity']['citations'])
    for c in hydrated['relations'][0]['citations']:
        assert c['quote']==context['sources'][c['source_id']]['text'][c['start']:c['end']]
        assert c['quote_sha256']==s.text_hash(c['quote'])


@pytest.mark.parametrize('fault',['foreign_id','one_side_identity','one_side_relation','quote','job','input','same_with_relation','relation_status','two_directions','duplicate_kind','no_reason','context_only'])
def test_rejects_invalid_assertions(modules,fault):
    s,r=modules;job,context=pair(s);v=response(job,context)
    if fault=='foreign_id':v['identity']['evidence_ids']=['not-supplied']
    elif fault=='one_side_identity':v['identity']['evidence_ids']=context['left_sense']['evidence_ids']
    elif fault=='one_side_relation':v['relations'][0]['evidence_ids']=context['right_sense']['evidence_ids']
    elif fault=='quote':v['identity']['quote']='invented'
    elif fault=='job':v['job_id']='other'
    elif fault=='input':v['input_sha256']='other'
    elif fault=='same_with_relation':v['identity']['decision']='SAME'
    elif fault=='relation_status':v['relation_assessment']='UNKNOWN';v['missing_information']='unknown'
    elif fault=='two_directions':v['relations']=[{'kind':k,'evidence_ids':v['identity']['evidence_ids']} for k in ['BROADER_THAN','NARROWER_THAN']]
    elif fault=='duplicate_kind':v['relations']*=2
    elif fault=='no_reason':v['identity']['decision']='UNKNOWN';v['relations']=[];v['relation_assessment']='UNKNOWN'
    else:v['identity']['evidence_ids']=[]
    with pytest.raises((ValueError,ValidationError)):r.validate(v,job,context)


def test_unknown_empty_is_valid_and_absent_enum_has_no_sentinel(modules):
    s,r=modules;job,ctx=pair(s);v=response(job,ctx,'UNKNOWN',None)
    v['relation_assessment']='UNKNOWN';r.validate(v,job,ctx)
    assert s.hydrate(v,ctx)['identity']['citations']==[]
    schema=s.response_schema({'evidence':[]})
    assert 'NONE' not in json.dumps(schema)
    assert schema['properties']['identity']['properties']['evidence_ids']['maxItems']==0


@pytest.mark.parametrize('fault',['offset','text','source_hash','sense_id','scope'])
def test_detects_source_or_binding_tampering(modules,fault):
    s,r=modules;job,ctx=pair(s);v=response(job,ctx)
    if fault=='offset':ctx['evidence'][0]['start']+=1
    elif fault=='text':ctx['evidence'][0]['text']='tampered'
    elif fault=='source_hash':next(iter(ctx['sources'].values()))['sha256']='0'*64
    elif fault=='sense_id':ctx['left_sense']['id']='fake'
    else:ctx['left_sense']['scope']='different-version'
    # Even if the caller recomputes the outer job binding, inner source identities fail.
    job['input_sha256']=s.digest(ctx);v['input_sha256']=job['input_sha256']
    with pytest.raises(ValueError):r.validate(v,job,ctx)


def test_notes_only_can_distinguish_homonyms(modules):
    s,r=modules;job,ctx=pair(s,bundle(s,'food',kind='SOURCE_SENSE_NOTE'),bundle(s,'stock',kind='SOURCE_SENSE_NOTE'))
    r.validate(response(job,ctx,'DIFFERENT',None),job,ctx)
    for identity,rel in [('SAME',None),('DIFFERENT','RELATED_TO')]:
        with pytest.raises(ValueError,match='note'):r.validate(response(job,ctx,identity,rel),job,ctx)


def test_definitions_split_candidates_without_splitting_prose(modules):
    s,r=modules;entry={'id':'polysemous','label':'주식'}
    items=[{'kind':'SOURCE_DEFINITION','text':t,'source_text_sha256':s.text_hash(t)} for t in ['증권이라는 뜻.','음식이라는 뜻.']]
    candidates,sources,ev=s.evidence_bundle(entry,items)
    assert len(candidates)==2 and len({c['id'] for c in candidates})==2
    assert all(c['sense_partition']=='SOURCE_DEFINITION_UNIT_UNREVIEWED' for c in candidates)
    assert len(s.evidence_bundle(entry,[{**items[0],'truncated':True}])[0])==0
    assert len(s.evidence_bundle(entry,[])[0])==0


def test_reverse_normalization_and_scope_identity(modules):
    s,r=modules;a,b=bundle(s,'A'),bundle(s,'B')
    job,ctx=pair(s,a,b);other,rev=pair(s,b,a);other['id']='job-2'
    v=response(job,ctx,relation='BROADER_THAN');w=response(other,rev,relation='NARROWER_THAN')
    with sqlite3.connect(':memory:') as db:
        s.create_tables(db);s.store(db,v,ctx);s.store(db,w,rev)
        rows=db.execute("SELECT source,target,value FROM sense_assertion WHERE axis='RELATION'").fetchall()
        assert rows[0]==rows[1] and rows[0][2]=='BROADER_THAN'
        assert db.execute('SELECT count(*) FROM sense_candidate').fetchone()[0]==2
        assert s.detect_conflicts(db)==0
    assert bundle(s,'A',scope='other-law-version')[0][0]['id']!=a[0][0]['id']


@pytest.mark.parametrize('kind',['identity','cycle'])
def test_transitive_conflicts_are_preserved_without_canonical_merge(modules,kind):
    s,r=modules;bundles={k:bundle(s,k) for k in 'ABC'}
    with sqlite3.connect(':memory:') as db:
        s.create_tables(db)
        for n,(a,b) in enumerate([('A','B'),('B','C'),('C','A')]):
            job,ctx=pair(s,bundles[a],bundles[b]);job['id']=str(n)
            v=response(job,ctx,'SAME' if n<2 else 'DIFFERENT',None) if kind=='identity' else response(job,ctx,relation='BROADER_THAN')
            s.store(db,v,ctx)
        assert s.detect_conflicts(db)>=1
        assert db.execute("SELECT count(*) FROM sense_assertion WHERE status='CONFLICT_REVIEW_REQUIRED'").fetchone()[0]==3
        count=db.execute('SELECT count(*) FROM sense_assertion').fetchone()[0]
        s.detect_conflicts(db)
        assert db.execute('SELECT count(*) FROM sense_assertion').fetchone()[0]==count
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='membership'").fetchone()


@pytest.fixture
def prepared(modules,assembly_inputs,tmp_path):
    s,r=modules;base_tests.a.build(*assembly_inputs,emit=lambda *a,**k:None)
    state=tmp_path/'review';r.prepare(assembly_inputs[-1],state)
    return assembly_inputs[-1],state,tmp_path/'compiled'


def test_prepare_run_resume_compile_uses_existing_path(modules,prepared):
    s,r=modules;glossary,state,output=prepared;original=base_tests.a.inspect(glossary)['dictionary_sha256']
    before=r.inspect(state);assert before['attempts']==0 and before['deferred']['NEEDS_SOURCE_EVIDENCE']>0
    fake=Fake();r.run(state,max_jobs=1,provider=fake);r.run(state,max_jobs=100,provider=fake)
    calls=fake.calls;r.run(state,max_jobs=100,provider=fake);assert fake.calls==calls
    result=r.compile_proposals(state,output)
    assert result['counts']['membership']==result['counts']['meaning']==0
    assert result['sense_review']['assertions']>0 and result['sense_review']['conflicts']==0
    assert result['canonical_approval'] is False
    assert base_tests.a.inspect(glossary)['dictionary_sha256']==original
    with sqlite3.connect(output/'dictionary.sqlite') as db:
        assert db.execute('SELECT count(*) FROM llm_review_v3').fetchone()[0]==calls
        assert db.execute('SELECT code FROM official_relation').fetchone()[0]=='140303'
        hydrated=json.loads(db.execute('SELECT result_json FROM llm_review_v3 LIMIT 1').fetchone()[0])
        assert hydrated['identity']['citations']
    with pytest.raises(ValueError):r.compile_proposals(state,output)


def test_failure_retry_preserves_raw_invalid_attempt(modules,prepared):
    s,r=modules;_,state,output=prepared
    with pytest.raises(RuntimeError):r.run(state,max_jobs=1,provider=Fake(lambda v:v['identity'].update(evidence_ids=['NONE'])))
    with sqlite3.connect(state/'review.sqlite') as db:
        raw=json.loads(db.execute("SELECT result_json FROM attempt WHERE status='failed'").fetchone()[0]);assert raw['identity']['evidence_ids']==['NONE']
    r.run(state,max_jobs=100,retry_failed=True,provider=Fake())
    r.compile_proposals(state,output)
    assert 'failed' not in r.inspect(state)['jobs']


def test_compile_revalidates_and_refuses_modified_result(modules,prepared):
    s,r=modules;_,state,output=prepared;r.run(state,max_jobs=100,provider=Fake())
    with sqlite3.connect(state/'review.sqlite') as db:
        ident,raw=db.execute('SELECT id,result_json FROM job LIMIT 1').fetchone();v=json.loads(raw);v['identity']['evidence_ids']=['invented']
        db.execute('UPDATE job SET result_json=? WHERE id=?',(json.dumps(v),ident))
    with pytest.raises(ValidationError):r.compile_proposals(state,output)
    assert not output.exists()


def configure_selection(tmp_path, glossary, state):
    root=tmp_path/'workspace';(root/'00_SYSTEM').mkdir(parents=True,exist_ok=True)
    settings={'current_draft':{'root_id':'data','path':str(glossary.relative_to(tmp_path))},
              'llm_review':{'current_review_state':{'root_id':'data','path':str(state.relative_to(tmp_path))}}}
    (root/'00_SYSTEM/GLOSSARY_PIPELINE.json').write_text(json.dumps(settings))
    return root


def test_completion_budget_then_new_draft_selected_by_main(modules,prepared,tmp_path):
    from lawrag.pipeline import glossary_linking as linking
    s,r=modules;glossary,state,output=prepared;root=configure_selection(tmp_path,glossary,state)
    assert linking.configured(root,tmp_path)==glossary
    fake=Fake();first=r.complete(glossary,state,output,max_jobs=1,provider=fake)
    assert first['completed'] is False and not output.exists()
    assert linking.configured(root,tmp_path)==glossary
    done=r.complete(glossary,state,output,max_jobs=100,provider=fake)
    assert done['completed'] and done['canonical_approval'] is False
    assert linking.configured(root,tmp_path)==output
    calls=fake.calls
    assert r.complete(glossary,state,output,provider=fake)['cached'] is True
    assert fake.calls==calls
    assert base_tests.a.inspect(output,'신탁')['sense_review']['assertions']
    with sqlite3.connect(output/'dictionary.sqlite') as db:
        assert db.execute('SELECT count(*) FROM membership').fetchone()[0]==0


def test_complete_keeps_failed_outputs_and_publishes_partial_draft(modules,prepared):
    s,r=modules;glossary,state,output=prepared;count=0
    def bad_first(v):
        nonlocal count
        count+=1
        if count==1:v['identity']['evidence_ids']=['NONE']
    result=r.complete(glossary,state,output,max_jobs=100,provider=Fake(bad_first))
    assert result['completed'] and result['review_status']=='PARTIAL'
    assert result['review']['jobs']['failed']==1 and result['review']['jobs']['complete']>0
    assert output.exists() and result['sense_review']['assertions']>0
    with pytest.raises(ValueError,match='new output'):
        r.complete(glossary,state,output,retry_failed=True,provider=Fake())


@pytest.mark.parametrize('fault',['changed_output','changed_base','escape','receipt'])
def test_downstream_refuses_stale_or_invalid_completion(modules,prepared,tmp_path,fault):
    from lawrag.pipeline import glossary_linking as linking
    s,r=modules;glossary,state,output=prepared
    r.complete(glossary,state,output,max_jobs=100,provider=Fake());root=configure_selection(tmp_path,glossary,state)
    receipt=json.loads((state/'completion.json').read_text())
    if fault=='changed_output':
        with (output/'dictionary.sqlite').open('ab') as f:f.write(b'changed')
    elif fault=='changed_base':
        with (glossary/'dictionary.sqlite').open('ab') as f:f.write(b'changed')
    elif fault=='escape':receipt['output_relative_to_state']='../../../../outside'
    else:receipt['dictionary_sha256']='0'*64
    (state/'completion.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError):linking.configured(root,tmp_path)


def test_schema_profile_registered_without_changing_serving_contract(modules):
    from semantic_runtime.contracts import Contracts
    from lawrag.platform.paths import repository_root
    root=repository_root();s,r=modules
    registry=json.loads((root/'00_SYSTEM/GLOSSARY_SCHEMA.json').read_text())
    assert registry['authoring_contracts']['GLOSSARY_REVIEW']['sha256']==r.v1.sha(s.SCHEMA_PATH)
    assert set(Contracts(root).schemas)=={'urn:8-agent:term-runtime-v1'}


def test_main_cli_dispatches_existing_review_workflow(modules,prepared,monkeypatch,capsys):
    import runpy
    from lawrag.platform.paths import repository_root
    s,r=modules;glossary,state,output=prepared
    monkeypatch.setattr(r,'provider_for',lambda state:Fake())
    monkeypatch.setattr(sys,'argv',['pipeline.py','glossary','review','complete','--glossary',str(glossary),
        '--state',str(state),'--output',str(output),'--max-jobs','100'])
    with pytest.raises(SystemExit) as end:runpy.run_path(str(repository_root()/'06_TOOLS/pipeline.py'),run_name='__main__')
    assert end.value.code==0
    result=json.loads(capsys.readouterr().out)
    assert result['completed'] and output.exists()


def test_complete_cli_defaults_use_main_selection(modules,prepared,monkeypatch,capsys):
    s,r=modules;glossary,state,output=prepared
    monkeypatch.setattr(r,'configured_paths',lambda:{'glossary':glossary,'state':state,'output':output})
    monkeypatch.setattr(r,'provider_for',lambda state:Fake())
    assert r.main(['complete','--max-jobs','1'])==3
    assert json.loads(capsys.readouterr().out)['completed'] is False
    assert r.main(['complete','--max-jobs','100'])==0
    assert json.loads(capsys.readouterr().out)['completed'] is True


def test_complete_no_definitions_makes_no_model_call(modules,assembly_inputs,tmp_path):
    s,r=modules;base_tests.a.build(*assembly_inputs,emit=lambda *a,**k:None)
    glossary=assembly_inputs[-1]
    with sqlite3.connect(glossary/'dictionary.sqlite') as db:
        db.execute("UPDATE entry SET definition='' ")
        db.execute('DELETE FROM definition_candidate')
    report=json.loads((glossary/'report.json').read_text());report['dictionary_sha256']=r.v1.sha(glossary/'dictionary.sqlite')
    (glossary/'report.json').write_text(json.dumps(report))
    fake=Fake();result=r.complete(glossary,tmp_path/'empty-state',tmp_path/'empty-output',provider=fake)
    assert fake.calls==0 and result['review']['attempts']==0
    assert result['review_status']=='PARTIAL' and result['sense_review']['assertions']==0


def test_completed_draft_can_be_relocated_as_one_data_tree(modules,prepared,tmp_path):
    import shutil
    from lawrag.pipeline import glossary_linking as linking
    s,r=modules;glossary,state,output=prepared
    r.complete(glossary,state,output,max_jobs=100,provider=Fake())
    relocated=tmp_path/'relocated';relocated.mkdir()
    for folder in (glossary,state,output):shutil.copytree(folder,relocated/folder.name)
    root=configure_selection(relocated,relocated/glossary.name,relocated/state.name)
    assert linking.configured(root,relocated)==relocated/output.name


def test_completion_recovers_after_output_published_without_receipt(modules,prepared):
    s,r=modules;glossary,state,output=prepared
    r.run(state,max_jobs=100,provider=Fake());r.compile_proposals(state,output)
    assert not (state/'completion.json').exists()
    fake=Fake();result=r.complete(glossary,state,output,provider=fake)
    assert result['recovered'] and fake.calls==0 and (state/'completion.json').exists()


def test_legacy_status_reports_its_original_contract(modules,prepared):
    s,r=modules;_,state,_=prepared
    with sqlite3.connect(state/'review.sqlite') as db:
        identity=json.loads(db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0])
        identity['version']='glossary-llm-review-v2'
        db.execute("UPDATE meta SET value=? WHERE key='identity'",(json.dumps(identity),))
        db.execute("UPDATE job SET status='complete',result_json=?",(json.dumps({'decision':'RELATED_ONLY'}),))
    result=r.inspect(state)
    assert result['schema_version']=='glossary-llm-review-v2' and result['decisions']['RELATED_ONLY']>0
    with pytest.raises(ValueError,match='implementation changed'):r.run(state,provider=Fake())
