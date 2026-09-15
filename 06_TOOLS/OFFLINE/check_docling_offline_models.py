#!/usr/bin/env python3
"""Check portable Docling weights, then optionally parse a synthetic PDF offline."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(bundle):
    manifest = json.loads((bundle / 'MODEL_MANIFEST.json').read_text())
    for row in manifest['files']:
        name = PurePosixPath(row['path'])
        if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != 'models':
            raise ValueError('Invalid model manifest path')
        path = bundle / str(name)
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Model path contains a symlink: ' + str(name))
        if not path.is_file() or path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('Missing or changed model file: ' + str(name))
    print('MODEL HASHES OK:', len(manifest['files']), 'files', flush=True)
    return manifest


def smoke(bundle, expected_version):
    import importlib.metadata
    import socket
    import tempfile
    from io import BytesIO
    import fitz
    installed = importlib.metadata.version('docling-slim')
    print('docling-slim:', installed, flush=True)
    print('docling-ibm-models:', importlib.metadata.version('docling-ibm-models'), flush=True)
    if installed != expected_version:
        raise ValueError('This bundle was checked against Docling ' + expected_version + '; inspect the installed version before proceeding')
    os.environ['DOCLING_ARTIFACTS_PATH'] = str(bundle / 'models')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ.setdefault('OMP_NUM_THREADS', '2')
    os.environ.setdefault('DOCLING_NUM_THREADS', '2')
    # This process is a synthetic smoke test only. No internal PDF is opened.
    def blocked(*args, **kwargs):
        raise RuntimeError('Network access attempted during offline model check')
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    from docling.datamodel.base_models import InputFormat, DocumentStream
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
    from docling.document_converter import DocumentConverter, PdfFormatOption
    document = fitz.open()
    page = document.new_page()
    page.insert_text((60, 60), 'Synthetic offline PDF model check', fontsize=16)
    for n in range(1, 8):
        page.insert_text((60, 90 + n * 18), 'This is synthetic text for checking offline layout and table model loading.')
    raw = document.tobytes()
    document.close()
    opts = PdfPipelineOptions(artifacts_path=bundle / 'models', do_ocr=False, do_table_structure=True,
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=2))
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    result = converter.convert(DocumentStream(name='synthetic-check.pdf', stream=BytesIO(raw)))
    if 'Synthetic offline PDF model check' not in result.document.export_to_markdown():
        raise ValueError('Synthetic PDF text did not survive parsing')
    print('OFFLINE PDF OK: layout/table models loaded; OCR and GENOS VLM were not tested', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--smoke-test', action='store_true')
    args = p.parse_args()
    bundle = Path(__file__).resolve().parent
    try:
        manifest = verify(bundle)
        if args.smoke_test:
            smoke(bundle, manifest['target_docling_version'])
    except Exception as exc:
        p.exit(2, 'STOP: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
