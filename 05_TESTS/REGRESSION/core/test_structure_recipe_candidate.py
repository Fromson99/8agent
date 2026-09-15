"""Synthetic contracts, no model requests or real-document efficacy claims."""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from lawrag.core.format_model import Format
from lawrag.core.parse_adapter import Element, ParseResult

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('recipe_runner', ROOT/'06_TOOLS/EXPERIMENTS/structure_recipe_probe.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
opt = runner.load_candidate()
SHA = 'a'*64


@pytest.fixture
def sample():
    fmt = Format(doc_type='test', regex_markers=[dict(id='article',pattern=r'^제(\d+)조',groups=['no'],level=0)])
    parsed = ParseResult(path='test.hwp', doc_id=SHA[:16], parser='fixture', born_digital=False,
        elements=[Element(0,'section_header','제1조'), Element(1,'text','첫 내용'),
                  Element(2,'section_header','제2조'), Element(3,'text','둘째 내용')])
    catalog = opt.marker_catalog([fmt])
    recipe = dict(tag='auto-001',version=1,catalog_sha256=opt.digest(catalog),
                  steps=[dict(component='test@1/article',level=0,parent=None)])
    return fmt, parsed, catalog, recipe


def test_compile_and_full_ownership(sample):
    _,parsed,catalog,recipe = sample
    result = opt.evaluate(parsed,SHA,opt.compile_recipe(recipe,catalog),recipe=recipe,attachments=[])
    assert result['status']=='candidate_pass', result
    assert result['structural_accuracy']=='not_independently_verified'


@pytest.mark.parametrize('change', ['pattern','unknown','parent','negative','catalog'])
def test_invalid_recipe_rejected(sample, change):
    _,_,catalog,recipe=sample
    if change=='pattern': recipe['steps'][0]['pattern']='.*'
    if change=='unknown': recipe['steps'][0]['component']='unknown'
    if change=='parent': recipe['steps'][0]['parent']='unknown'
    if change=='negative': recipe['steps'][0]['level']=-1
    if change=='catalog': recipe['catalog_sha256']='0'*64
    with pytest.raises(ValueError): opt.compile_recipe(recipe,catalog)


def test_tag_paths_versions_and_no_implicit_overwrite(sample):
    _,parsed,catalog,recipe=sample
    receipt=opt.evaluate(parsed,SHA,opt.compile_recipe(recipe,catalog),recipe=recipe,attachments=[])
    registry=dict(schema_version='document-recipe-tags-v1', documents={})
    updated=opt.propose_tag(registry,'외규/준칙.hwp',SHA,recipe,receipt)
    assert registry['documents']=={}
    assert opt.tag_record(updated,'외규/준칙.hwp',SHA)['status']=='candidate'
    assert opt.tag_record(updated,'내규/준칙.hwp',SHA) is None
    with pytest.raises(ValueError): opt.tag_record(updated,'외규/준칙.hwp','b'*64)
    with pytest.raises(ValueError): opt.propose_tag(updated,'외규/준칙.hwp',SHA,recipe,receipt)
    with pytest.raises(ValueError): opt.document_key('../준칙.hwp')


def test_existing_before_new_and_ambiguity(sample):
    fmt,parsed,catalog,_=sample
    def forbidden(): raise AssertionError('must not ask model')
    assert opt.choose(parsed,SHA,[(fmt,None)],catalog,proposer=forbidden,attachments=[])['status']=='existing_candidate'
    assert opt.choose(parsed,SHA,[(fmt,None),(fmt,None)],catalog,proposer=forbidden,attachments=[])['status']=='needs_review'


def test_one_generated_candidate(sample):
    _,parsed,catalog,recipe=sample
    calls=[]
    def propose(): calls.append(1); return recipe
    assert opt.choose(parsed,SHA,[],catalog,proposer=propose,attachments=[])['status']=='new_candidate'
    assert calls==[1]


@pytest.mark.parametrize('attachments', [None, [{'name':'별표1.hwp','state':'missing'}]])
def test_missing_annex_never_passes(sample, attachments):
    fmt,parsed,_,_=sample
    assert opt.evaluate(parsed,SHA,fmt,attachments=attachments)['status']=='needs_review'


def test_sampling_includes_tail_and_is_bounded(sample):
    _,parsed,catalog,_=sample
    parsed.elements=[Element(i,'text','내용') for i in range(1000)]
    parsed.elements[-1].text='별첨 1 별지 서식'
    packet=opt.request_packet(parsed,SHA,catalog)
    payload=json.loads(packet['user'])
    assert 999 in [e['index'] for e in payload['elements']]
    assert len(payload['elements'])<=140
    assert payload['omitted_elements']>0


def test_image_capability_provenance_and_bounds(sample):
    _,parsed,catalog,_=sample
    image=dict(page=1,source_sha256=SHA,render_kind='original_page',data_uri='data:image/png;base64,YQ==')
    with pytest.raises(ValueError): opt.request_packet(parsed,SHA,catalog,images=[image])
    assert opt.request_packet(parsed,SHA,catalog,images=[image],supports_images=True)['images']
    image['render_kind']='synthetic_page'
    with pytest.raises(ValueError): opt.request_packet(parsed,SHA,catalog,images=[image],supports_images=True)


def test_provider_authority_and_same_call_image_forwarding(sample):
    _,parsed,catalog,recipe=sample
    packet=opt.request_packet(parsed,SHA,catalog)
    calls=[]
    provider=SimpleNamespace(backend='genos',structured=lambda *a,**k:(calls.append((a,k)) or recipe))
    with pytest.raises(ValueError): opt.ask_recipe(provider,packet,catalog,model='internal-model',backend='genos')
    assert calls==[]
    assert opt.ask_recipe(provider,packet,catalog,model='internal-model',backend='genos',authorized=True)==recipe
    assert calls[0][1]['max_tokens']==2000


def test_offline_cli_report_and_no_overwrite(tmp_path):
    source=tmp_path/'문서.md'
    source.write_text('# 제1조\n본문\n# 제2조\n별첨 안내\n')
    output=tmp_path/'report'
    cmd=[sys.executable,str(ROOT/'06_TOOLS/EXPERIMENTS/structure_recipe_probe.py'),
         '--source',str(source),'--document-name','외규/문서.md','--output',str(output)]
    result=subprocess.run(cmd,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert json.loads((output/'report.json').read_text())['llm_calls']==0
    assert (output/'report.html').is_file()
    assert json.loads((output/'request.json').read_text())['images']==[]
    assert subprocess.run(cmd,text=True,capture_output=True).returncode!=0
