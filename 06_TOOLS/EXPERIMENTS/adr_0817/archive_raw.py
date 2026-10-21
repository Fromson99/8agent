"""Lossless, hash-verified experiment storage; never touches MAIN data/code."""
from pathlib import Path
import hashlib,json,sys,tarfile
R=Path(__file__).resolve().parents[3];O=R/'04_EXPERIMENTS/ADR/ADR-0817-risk-main76-live-e2e/artifacts/run-001'
archive=O/'raw-runtime.tar.gz';index=O/'raw-archive.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if '--restore' in sys.argv:
    manifest=json.loads(index.read_text());assert sha(archive)==manifest['archive_sha256']
    with tarfile.open(archive,'r:gz') as tf:
        assert {m.name for m in tf.getmembers()}=={r['path'] for r in manifest['members']}
        for row in manifest['members']:
            target=O/row['path'];assert target.resolve().is_relative_to(O.resolve())
            if target.exists():assert sha(target)==row['sha256'];continue
            payload=tf.extractfile(row['path']).read();assert hashlib.sha256(payload).hexdigest()==row['sha256']
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    print('Restored all original files with exact SHA256 verification')
else:
    assert not archive.exists() and not index.exists()
    assert all(json.loads(p.read_text())['passed'] for p in O.glob('*/reopen-result.json'))
    assert len(list(O.glob('*/reopen-result.json')))==4
    roots=[p for cid in ('risk-027','risk-038','risk-104','known-liquidity') for p in (O/cid/'raw',O/cid/'runtime')]
    paths=sorted([p for root in roots for p in root.rglob('*') if p.is_file()]+list(O.glob('*-service.log'))+list(O.glob('*-reopen.log')))
    assert all(not p.is_symlink() for p in paths)
    members=[{'path':str(p.relative_to(O)),'sha256':sha(p),'bytes':p.stat().st_size} for p in paths]
    temp=O/'raw-runtime.tar.gz.partial'
    with tarfile.open(temp,'w:gz',compresslevel=6) as tf:
        for p in paths:tf.add(p,arcname=str(p.relative_to(O)),recursive=False)
    with tarfile.open(temp,'r:gz') as tf:
        assert {m.name for m in tf.getmembers()}=={r['path'] for r in members}
        for row in members:
            assert hashlib.sha256(tf.extractfile(row['path']).read()).hexdigest()==row['sha256']
    temp.rename(archive)
    value={'schema_version':'lossless-experiment-archive-v1','archive':archive.name,'archive_sha256':sha(archive),
           'original_bytes':sum(r['bytes'] for r in members),'compressed_bytes':archive.stat().st_size,'members':members,
           'restore_command':'.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0817/archive_raw.py --restore',
           'purpose':'Original provider wire JSON, immutable native journals (including WAL if present) and service logs. Verified before removing redundant uncompressed copies. Restore before rerunning post-run inspection.'}
    index.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    # Every byte remains in the verified archive; this is storage encoding, not history deletion.
    for p,row in zip(paths,members):assert sha(p)==row['sha256'];p.unlink()
    for root in roots:
        for p in sorted((p for p in root.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):p.rmdir()
        root.rmdir()
    print(json.dumps({k:value[k] for k in ('original_bytes','compressed_bytes','archive_sha256')},ensure_ascii=False))
