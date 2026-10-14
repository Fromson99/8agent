"""Losslessly preserve closed probe SQLite bytes with restore receipts."""
from pathlib import Path
import gzip, hashlib, json

ROOT = Path(__file__).resolve().parents[3]
ADR = ROOT / '04_EXPERIMENTS/ADR/ADR-0684-venture-option-tax-navigation-local-probe'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
receipts = []
for run in ('run-001', 'run-002'):
    directory = ADR / 'artifacts' / run
    assert (directory / 'result.json').is_file(), 'Archive only finished probe processes'
    for p in sorted((directory / 'runtime').rglob('*')):
        if not p.is_file() or '.sqlite' not in p.name or p.name.endswith('.gz'):
            continue
        target = p.with_name(p.name + '.gz')
        assert not target.exists()
        raw = p.read_bytes()
        expected = hashlib.sha256(raw).hexdigest()
        with gzip.open(target, 'wb', compresslevel=9) as stream:
            stream.write(raw)
        assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest() == expected
        receipts.append({'path': str(p.relative_to(ROOT)), 'raw_sha256': expected,
            'raw_bytes': len(raw), 'archive_path': str(target.relative_to(ROOT)),
            'archive_sha256': sha(target), 'archive_bytes': target.stat().st_size,
            'verified_lossless': True,
            'restore': 'Decompress each database and its archived -wal/-shm sidecars to the recorded original filenames before opening SQLite. Do not restore into the serving runtime.'})
        p.unlink()
(ADR / 'artifacts/runtime-archives.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + '\n')
print('Archived', len(receipts), 'SQLite files;', sum(x['raw_bytes'] for x in receipts),
      'bytes ->', sum(x['archive_bytes'] for x in receipts), 'verified lossless bytes')
