"""Create a new parser config beside the existing one; retain model endpoints."""
import argparse
import os
from pathlib import Path
import yaml


def prepare(source, output):
    source, output = Path(source).resolve(strict=True), Path(output).absolute()
    if output.parent.resolve() != source.parent:
        raise ValueError('Keep output beside source to preserve relative resource paths')
    cfg = yaml.safe_load(source.read_text(encoding='utf-8'))
    if not isinstance(cfg, dict) or not isinstance(cfg.get('layout'), dict) or not isinstance(cfg.get('ocr'), dict):
        raise ValueError('Use a parser config with configured layout and OCR; attachment YAML is not interchangeable')
    cfg['enrichment'] = []
    cfg['output'] = {**(cfg.get('output') or {}), 'format': 'docling'}
    # Exclusive creation preserves the old configuration and any prior revision.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        yaml.safe_dump(cfg, stream, allow_unicode=True, sort_keys=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    prepare(args.source, args.output)
    print('Prepared new parser configuration; existing configuration preserved.')
