"""Mock engine tests of the deployable wrapper; no internal/model calls."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import fitz
import pytest
import yaml
from docling_core.types.doc import DoclingDocument, DocItemLabel, Size, TableCell, TableData

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT/'08_DEPLOYMENT/GENOS/preprocessor'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def server_module(monkeypatch, tmp_path):
    doc = DoclingDocument(name='synthetic')
    doc.add_page(page_no=1, size=Size(width=595, height=842))
    doc.add_text(label=DocItemLabel.TEXT, text='Source before table')
    doc.add_table(data=TableData(num_rows=1, num_cols=2, table_cells=[
        TableCell(text='Merged source cell', start_row_offset_idx=0, end_row_offset_idx=1,
                  start_col_offset_idx=0, end_col_offset_idx=2, col_span=2)]))
    doc.add_text(label=DocItemLabel.TEXT, text='Source after table')
    state = {'document':doc.model_dump(mode='json'), 'calls':[]}
    class Base:
        def __init__(self, path): self.config = yaml.safe_load(Path(path).read_text())
        async def __call__(self, request, path, **kwargs):
            state['calls'].append(kwargs)
            return {'document':copy.deepcopy(state['document']), 'usage':{'pages':1}}
    for name in ('genon','genon.preprocessor','genon.preprocessor.facade'):
        mod = ModuleType(name); mod.__path__ = []
        monkeypatch.setitem(sys.modules,name,mod)
    base = ModuleType('genon.preprocessor.facade.parser_processor'); base.DocumentProcessor=Base
    monkeypatch.setitem(sys.modules,base.__name__,base)
    module = load('structured_wrapper_test', DEPLOY/'preprocessor.py')
    cfg = tmp_path/'parser.yaml'
    cfg.write_text('enrichment: []\noutput:\n  format: docling\n')
    source = tmp_path/'source.pdf'
    with fitz.open() as pdf:
        pdf.new_page(width=595,height=842); pdf.save(source)
    return module, state, cfg, source


def test_server_preserves_tree_cells_reading_order_and_source_hash(server_module):
    module, state, cfg, source = server_module
    output = asyncio.run(module.DocumentProcessor(str(cfg))(None,str(source),img_desc=1,doc_summary=1,toc=1))
    assert output['document'] == state['document']
    assert output['document']['tables'][0]['data']['table_cells'][0]['col_span'] == 2
    assert [r['text'] for r in output['reading_order']] == ['Source before table','Merged source cell','Source after table']
    for row in output['reading_order']:
        lo,hi=row['char_span']; assert output['full_text'][lo:hi]==row['text']
    assert output['provenance']['source_sha256'] == module.sha(source)
    assert output['usage'] == {'pages':1}
    assert state['calls'][0]['img_desc'] == state['calls'][0]['toc'] == 0
    # Actual client can consume the structured server document without coercion.
    restored = DoclingDocument.model_validate(output['document'])
    assert restored.tables[0].data.table_cells[0].col_span == 2


def test_server_refuses_enrichment_config_and_chunk_engine(server_module):
    module, state, cfg, source = server_module
    cfg.write_text('enrichment: [doc_summary]\noutput:\n  format: docling\n')
    with pytest.raises(ValueError,match='enrichment'):
        module.DocumentProcessor(str(cfg))
    assert not state['calls']
    cfg.write_text('enrichment: []\noutput:\n  format: docling\n')
    state['document']={}
    with pytest.raises(ValueError):
        asyncio.run(module.DocumentProcessor(str(cfg))(None,str(source)))


def test_config_preparation_preserves_models_and_never_overwrites(tmp_path):
    module=load('prepare_structured_config_test',DEPLOY/'prepare_config.py')
    source=tmp_path/'old.yaml'; output=tmp_path/'new.yaml'
    cfg={'layout':{'endpoint':'http://internal-layout'},'ocr':{'mode':'auto'},
         'pdf_pipeline':{'table_structure_mode':'accurate'},'enrichment':['doc_summary'],
         'output':{'format':'json'},'guardrail':{'enabled':True}}
    source.write_text(yaml.safe_dump(cfg)); original=source.read_bytes()
    module.prepare(source,output)
    new=yaml.safe_load(output.read_text())
    assert new['enrichment']==[] and new['output']['format']=='docling'
    for key in ('layout','ocr','pdf_pipeline','guardrail'):assert new[key]==cfg[key]
    assert source.read_bytes()==original and output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):module.prepare(source,output)
