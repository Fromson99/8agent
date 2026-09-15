"""MAIN entry/consumer contracts with synthetic source and transport; no API calls."""
import copy,json,io,logging
from types import SimpleNamespace
import pytest
from lawrag.core import ingest,parse_adapter
from lawrag.core.structure import recipe_runtime as runtime
from lawrag.pipeline import genos_admission,genos_stages as stages
from .test_recipe_runtime import isolated_env,regional_document,regional_provider
from .test_genos_admission import payload
from .test_genos_build import setup,Fake
from .test_genos_four_stage import invoke, Terminal
from lawrag.pipeline.genos_progress import Progress


def test_actual_ingestion_uses_regions_and_viewer_output(tmp_path,monkeypatch):
    pdf,blocks=regional_document(tmp_path);seen=regional_provider(monkeypatch)
    parsed=parse_adapter.ParseResult(str(pdf),'synthetic','synthetic',True,elements=[parse_adapter.Element(b.idx,'text',b.text,page=b.page,bbox=b.bbox,bbox_origin=b.bbox_origin) for b in blocks])
    monkeypatch.setattr(ingest,'parse_cached',lambda *a:parsed)
    terminal=Terminal();progress=Progress(tmp_path/'logs',terminal)
    try:
        progress.document(1,1,'synthetic.pdf','구조화')
        with runtime.progress_events(progress.emit):
            data=ingest.interpret_doc(pdf,store=tmp_path/'store',doc_id='synthetic')
    finally:progress.close()
    visible=terminal.getvalue()
    assert '형식 구간 감지' in visible and '구조화 틀 생성' in visible and 'bbox 검수' in visible
    assert '검수 완료' in visible
    status=json.loads((tmp_path/'logs/current.json').read_text())
    assert status['vlm_run_id']==data['recipe_review']['run_id']
    assert 'artifact.saved' not in visible
    assert data['recipe_review']['process']=='region-templates'
    assert data['stats']['region_plan'] and data['stats']['region_ladders']
    assert all(b['rect'] for b in data['blocks'])
    assert [b['text'] for b in data['blocks']]==[b.text for b in blocks]
    assert any('visual_evidence' in d for d in seen)
    assert any('outline' in d for d in seen) and any('region_instances' in d for d in seen)


def test_unfinished_review_cannot_escape_ingestion(tmp_path,monkeypatch):
    pdf,_=regional_document(tmp_path)
    monkeypatch.setattr(ingest,'parse_cached',lambda *a:SimpleNamespace(elements=[]))
    monkeypatch.setattr(runtime,'revise_pdf',lambda *a,**k:(None,{'status':'needs_review'}))
    with pytest.raises(runtime.NeedsReview):ingest.interpret_doc(pdf,store=tmp_path/'store')


@pytest.mark.parametrize('status',['needs_review','failed','started'])
def test_failed_review_cannot_enter_semantic_authoring(payload,status):
    r={'status':status};payload['recipe_review']=r
    with pytest.raises(ValueError,match='recipe_review.status'):
        genos_admission.validate_structure('abc',{'doc_id':'abc','recipe_review':r},payload)


def test_review_receipts_must_match(payload):
    payload['recipe_review']={'status':'visual_approved','run_id':'one'}
    with pytest.raises(ValueError,match='recipe_review'):
        genos_admission.validate_structure('abc',{'doc_id':'abc','recipe_review':{'status':'visual_approved','run_id':'other'}},payload)


def test_late_structure_failure_blocks_both_following_stages(setup,monkeypatch):
    args,raw,out=setup;data=out.parent/'canonical';original=stages.structure
    def late_failure(*a,**k):
        folder,work=original(*a,**k)
        meta=folder/'structure'/work['files'][0]['document_id']/'meta.json'
        value=json.loads(meta.read_text());value['recipe_review']={'status':'needs_review'};meta.write_text(json.dumps(value))
        return folder,work
    monkeypatch.setattr(stages,'structure',late_failure)
    result=invoke(args,raw,data,'all')
    assert not result['ok'] and not Fake.instances
    assert all(d['structure']=='FAILED' for d in result['documents'].values())
    assert not list(data.glob('LLM/*/*/llm-result.json')) and not list(data.glob('VECTOR/*/*/result.json'))


def test_all_stages_deliver_ingestion_events_and_clear_context(setup,monkeypatch):
    from lawrag.pipeline import genos_build as build
    args,raw,out=setup;data=out.parent/'canonical';original=build.ingest_files
    def measured_ingest(*a,**k):
        journal=runtime.Journal(out.parent/'vlm-test','synthetic.xml')
        journal.event('recipe.review.start',revision=1,window_number=2,window_count=3,pages=[4,5],corrections=1)
        return original(*a,**k)
    monkeypatch.setattr(build,'ingest_files',measured_ingest)
    result=invoke(args,raw,data,'all')
    assert result['ok'],result
    assert 'bbox 검수 2/3창 · 4,5쪽 · 수정 1회' in (data/'LOGS/one/progress.log').read_text()
    assert '[STRUCTURE VLM]' in (data/'LOGS/one/detail.log').read_text()
    assert list(data.glob('VECTOR/*/*/result.json'))
    assert runtime.Journal(out.parent/'unbound','next').emit is None


def test_event_levels_private_fields_and_failure_delivery(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-secret-never-log')
    terminal=Terminal();progress=Progress(tmp_path/'logs',terminal);observed=[]
    try:
        progress.document(1,1,'synthetic.pdf','구조화')
        with runtime.progress_events(progress.emit):
            journal=runtime.Journal(tmp_path/'runs','synthetic.pdf')
        monkeypatch.setattr(journal.obs,'event',lambda *a,**k:observed.append(k['level']))
        journal.event('artifact.saved',artifact='example.json')
        journal.event('stage.wait',phase='review',seconds=10)
        journal.event('model.retry',next_attempt=2,delay_seconds=2)
        journal.event('run.needs_review',reason='synthetic-secret-never-log',error_type='ValueError')
    finally:progress.close()
    assert observed==[logging.DEBUG,logging.DEBUG,logging.WARNING,logging.ERROR]
    text=terminal.getvalue()
    assert '재시도 2' in text and '구조 검수 보류' in text
    assert 'artifact.saved' not in text and 'stage.wait' not in text
    assert 'synthetic-secret-never-log' not in text+(tmp_path/'logs/detail.log').read_text()
    rows=[json.loads(line) for line in (journal.directory/'events.jsonl').read_text().splitlines()]
    assert len(rows)==4 and rows[-1]['level']=='ERROR'


def test_real_review_hold_delivers_reason_and_run_id(tmp_path,monkeypatch):
    from lawrag.core.structure import pipeline
    pdf,blocks=regional_document(tmp_path);regional_provider(monkeypatch,'hold')
    terminal=Terminal();progress=Progress(tmp_path/'logs',terminal)
    try:
        progress.document(1,1,'held.pdf','구조화')
        with runtime.progress_events(progress.emit), pytest.raises(runtime.NeedsReview):
            runtime.revise_pdf(pipeline,blocks,pdf,store=tmp_path/'store',document='held')
    finally:progress.close()
    assert 'reviewer_hold' in terminal.getvalue()
    current=json.loads((tmp_path/'logs/current.json').read_text())
    assert current['vlm_run_id'] and '구조 검수 보류' in current['detail']
    assert not (tmp_path/'structure-recipes.json').exists()
