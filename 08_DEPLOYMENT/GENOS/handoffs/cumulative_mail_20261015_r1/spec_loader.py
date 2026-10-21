"""Lossless recipe interning for the large sealed inventory table."""
import gzip,json
from pathlib import Path

def load(path=None):
    path=Path(path) if path else Path(__file__).with_name('BUNDLE_SPEC.json.gz')
    value=json.loads(gzip.decompress(path.read_bytes()))
    records=value.pop('patch_records')
    for state in value['signatures'].values():
        state['patches']={records[i][0]:{'before_sha256':records[i][1],'after_sha256':records[i][2]}
                          for i in state.pop('patch_refs')}
    return value
