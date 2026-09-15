"""Office process mocked; real PDF validation/rendering tested without network."""
import importlib.util
import json
from pathlib import Path
import shutil

import fitz
import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('visual_runner',ROOT/'06_TOOLS/EXPERIMENTS/annex_visual_probe.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
visual=runner.load_candidate()


def make_pdf(path):
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((70,70),'Section 1: source evidence')
        doc.save(path)


@pytest.mark.parametrize('suffix',['.docx','.hwp','.hwpx'])
def test_converter_unavailable_is_not_pass(tmp_path,monkeypatch,suffix):
    source=tmp_path/('source'+suffix);source.write_bytes(b'original bytes')
    monkeypatch.setattr(visual.shutil,'which',lambda _:None)
    report=visual.office_pdf(source,tmp_path/'out')
    assert report['status']=='converter_unavailable'
    assert source.read_bytes()==b'original bytes'
    assert not (tmp_path/'out/rendered.pdf').exists()
    assert json.loads((tmp_path/'out/conversion.json').read_text())['status']=='converter_unavailable'


@pytest.mark.parametrize('suffix',['.docx','.hwp','.hwpx'])
def test_office_command_and_receipt_with_fake_converter(tmp_path,monkeypatch,suffix):
    source=tmp_path/('원본'+suffix);source.write_bytes(b'preserve')
    monkeypatch.setattr(visual.shutil,'which',lambda _: '/usr/bin/true')
    class Process:
        def __init__(self,command,**kwargs):
            assert kwargs['start_new_session'] is True
            assert '--headless' in command
            assert 'pdf:writer_pdf_Export' in command
            assert str(source) not in command
            work=Path(command[command.index('--outdir')+1])
            assert (work/('source'+suffix)).read_bytes()==b'preserve'
            assert 'MacroSecurityLevel' in (work/'profile/user/registrymodifications.xcu').read_text()
            make_pdf(work/'source.pdf')
        def wait(self,timeout=None):return 0
    monkeypatch.setattr(visual.subprocess,'Popen',Process)
    report=visual.office_pdf(source,tmp_path/'out')
    assert report['status']=='rendered_unverified'
    assert report['layout_fidelity']=='unverified'
    assert report['source_sha256']==visual.sha(source)
    assert report['pdf_sha256']==visual.sha(tmp_path/'out/rendered.pdf')
    assert source.read_bytes()==b'preserve'


def test_failed_importer_not_synthetic_fallback(tmp_path,monkeypatch):
    source=tmp_path/'bad.hwp';source.write_bytes(b'invalid')
    monkeypatch.setattr(visual.shutil,'which',lambda _: '/usr/bin/true')
    class Process:
        def __init__(self,*a,**k):pass
        def wait(self,timeout=None):return 1
    monkeypatch.setattr(visual.subprocess,'Popen',Process)
    assert visual.office_pdf(source,tmp_path/'out')['status']=='conversion_failed'


def test_original_pdf_to_image_packet(tmp_path):
    source=tmp_path/'original.pdf';make_pdf(source)
    receipt=visual.office_pdf(source,tmp_path/'out')
    packet=runner.packet_from_render(receipt,[1])
    assert packet['images'][0].startswith('data:image/png;base64,')
    assert packet['conversion_provenance']['source_sha256']==visual.sha(source)
    assert 'not guaranteed original Office pagination' in packet['system']
    with pytest.raises(ValueError):runner.packet_from_render(receipt,[2])
    with pytest.raises(FileExistsError):visual.office_pdf(source,tmp_path/'out')


def test_changed_pdf_rejected(tmp_path):
    source=tmp_path/'original.pdf';make_pdf(source)
    receipt=visual.office_pdf(source,tmp_path/'out')
    Path(receipt['pdf_path']).write_bytes(b'changed')
    with pytest.raises(ValueError):runner.packet_from_render(receipt,[1])


def test_annex_availability_is_not_semantic_pass(tmp_path):
    (tmp_path/'body.xml').write_text('<법령><별표><별표단위><별표번호>0001</별표번호><별표내용/></별표단위></별표></법령>')
    attachment=tmp_path/'annex.hwp';attachment.write_bytes(b'actual')
    (tmp_path/'manifest.json').write_text(json.dumps({'items':[{'name':'test','body_file':'body.xml','attachments':[
        {'title':'[별표] no number','file':'annex.hwp','sha256':visual.sha(attachment)},
        {'title':'[별표 2]','file':'missing.hwp','sha256':'0'*64}]}]}))
    result=visual.audit_annexes(tmp_path)
    assert result['summary']==dict(attachments=2,missing_or_changed=1,no_md=2,legacy_title_unmatched=1,xml_annexes=1,xml_empty=1)
    assert result['attachments'][0]['state']=='file_available_extraction_unverified'


def test_path_escape_rejected(tmp_path):
    with pytest.raises(ValueError):visual.confined(tmp_path,'../escape')
    with pytest.raises(ValueError):visual.confined(tmp_path,'/etc/passwd')
