"""Lossless archival of explicitly inventoried, inactive experiment records.

Never edits historical JSON, experiment status, manifests or model outputs.
Large originals are replaced by .gz plus a durable restoration receipt, after
streaming verification. Historical consumers must restore plain files first.
"""
from pathlib import Path
import argparse, gzip, hashlib, json, os, shutil, stat, time

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261028-experiment-storage-cleanup'
PLAN = AUDIT / 'archive-plan.json'
CHUNK = 4 * 1024**2

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + path.name + '.writing')
    with temp.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)
    sync_dir(path.parent)

def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def metadata(path):
    s = path.lstat()
    return dict(size=s.st_size, blocks=s.st_blocks, ino=s.st_ino, dev=s.st_dev,
                mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid,
                nlink=s.st_nlink, mtime_ns=s.st_mtime_ns)

def stream_hash(stream):
    h = hashlib.sha256(); size = 0
    while data := stream.read(CHUNK): h.update(data); size += len(data)
    return h.hexdigest(), size

def file_hash(path):
    with path.open('rb') as f: return stream_hash(f)[0]

def path_in_root(rel):
    p = ROOT / rel
    assert not Path(rel).is_absolute() and '..' not in Path(rel).parts
    assert p.resolve() == p and p.is_relative_to(ROOT / '04_EXPERIMENTS'), rel
    return p

def active_handles():
    ids = set(); commands = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or proc.name == str(os.getpid()): continue
        try:
            if proc.stat().st_uid != os.getuid(): continue
            commands.append((proc / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace'))
            for fd in (proc / 'fd').iterdir():
                try:
                    s = fd.stat(); ids.add((s.st_dev, s.st_ino))
                except FileNotFoundError: pass
            for line in (proc / 'maps').read_text().splitlines():
                fields = line.split(None, 5)
                if len(fields) == 6 and fields[5].startswith(str(ROOT / '04_EXPERIMENTS') + '/'):
                    p = Path(fields[5])
                    if p.exists():
                        s = p.stat(); ids.add((s.st_dev, s.st_ino))
        except (FileNotFoundError, ProcessLookupError): pass
        except PermissionError:
            name = (proc / 'comm').read_text().strip()
            if name not in ('systemd', '(sd-pam)'):
                raise RuntimeError('Cannot inspect same-user process ' + proc.name)
    return ids, commands

def inactive(p, before):
    ids, commands = active_handles()
    adr = p.relative_to(ROOT).parts[2]
    number = adr.split('-')[1]
    assert (before['dev'], before['ino']) not in ids, 'Open file: ' + str(p)
    assert not any(adr in c or '/adr_' + number + '/' in c for c in commands), 'Active ADR: ' + adr
    assert metadata(p) == before, 'Source changed: ' + str(p)

def make_plan():
    assert not PLAN.exists(), 'Preserve existing plan'
    inv = json.loads((AUDIT / 'inventory.json').read_text())
    ids, commands = active_handles(); rows = []; skipped = []
    for row in inv['rows']:
        p = path_in_root(row['path']); m = metadata(p)
        if ('/artifacts/' not in row['path'] or p.suffix not in ('.json', '.jsonl', '.md')
                or m['nlink'] != 1 or m['uid'] != os.getuid()
                or time.time_ns() - m['mtime_ns'] < 7 * 86400 * 10**9): continue
        adr = p.relative_to(ROOT).parts[2]; number = adr.split('-')[1]
        if (m['dev'], m['ino']) in ids or any(adr in c or '/adr_' + number + '/' in c for c in commands):
            skipped.append(row['path']); continue
        archive = Path(str(p) + '.gz')
        receipt = Path(str(archive) + '.archive-receipt.json')
        if archive.exists() or receipt.exists():
            skipped.append(row['path']); continue
        rows.append(dict(path=row['path'], before=m, archive=str(archive.relative_to(ROOT)),
                         receipt=str(receipt.relative_to(ROOT))))
    pointer = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    save(PLAN, dict(schema='experiment-record-archive-v1', files=rows, skipped=skipped,
                   original_bytes=sum(x['before']['size'] for x in rows),
                   active_pointer_sha256=file_hash(pointer),
                   note='Inactive >=7 days; includes partial/failed/unfinalized history without changing status.'))
    print('PLAN', len(rows), 'files', sum(x['before']['size'] for x in rows) / 2**30, 'GiB', flush=True)

def archive_one(row):
    p = path_in_root(row['path']); archive = path_in_root(row['archive']); receipt = path_in_root(row['receipt'])
    if receipt.exists():
        record = json.loads(receipt.read_text())
        if record['status'] == 'ARCHIVED' and not p.exists(): return record
        if record['status'] == 'VERIFIED' and p.exists():
            assert file_hash(archive) == record['archive_sha256']
            with gzip.open(archive, 'rb') as f: restored = stream_hash(f)
            assert restored == (record['original_sha256'], row['before']['size'])
            inactive(p, row['before']); assert file_hash(p) == record['original_sha256']
            p.unlink(); sync_dir(p.parent)
            record['status'] = 'ARCHIVED'; save(receipt, record); return record
        if record['status'] == 'VERIFIED' and not p.exists():
            assert file_hash(archive) == record['archive_sha256']
            with gzip.open(archive, 'rb') as f: assert stream_hash(f) == (record['original_sha256'], row['before']['size'])
            record['status'] = 'ARCHIVED'; save(receipt, record); return record
        raise RuntimeError('Unexpected receipt/source state: ' + str(p))
    inactive(p, row['before'])
    assert not archive.exists()
    temp = archive.with_name('.' + archive.name + '.compressing')
    assert not temp.exists(), 'Partial archive preserved; inspect before retry'
    free = min(shutil.disk_usage(ROOT).free, shutil.disk_usage('/mnt/c').free)
    assert free > 3 * 2**30, 'Insufficient headroom; originals unchanged'
    h = hashlib.sha256(); size = 0
    with p.open('rb') as src, temp.open('xb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', compresslevel=1, mtime=0) as dst:
            while block := src.read(CHUNK):
                h.update(block); size += len(block); dst.write(block)
                if size % (64 * 2**20) == 0:
                    assert min(shutil.disk_usage(ROOT).free, shutil.disk_usage('/mnt/c').free) > 2 * 2**30, 'Disk headroom exhausted'
        raw.flush(); os.fsync(raw.fileno())
    assert metadata(p) == row['before'] and size == row['before']['size']
    with gzip.open(temp, 'rb') as f: restored = stream_hash(f)
    assert restored == (h.hexdigest(), size), 'Lossless verification failed'
    assert temp.stat().st_size < size, 'Compression did not save space; source preserved'
    record = dict(**row, status='VERIFIED', original_sha256=h.hexdigest(),
                  archive_sha256=file_hash(temp), compressed_bytes=temp.stat().st_size,
                  saved_allocated_bytes=row['before']['blocks'] * 512 - temp.stat().st_blocks * 512,
                  verified_lossless=True, compression='gzip-level-1',
                  restore_command=' .venv/bin/python 06_TOOLS/maintenance/experiment_record_archive.py restore --path ' + row['path'])
    os.chmod(temp, row['before']['mode'] & ~0o222)
    os.replace(temp, archive); sync_dir(archive.parent)
    save(receipt, record)  # Recovery information is durable BEFORE removal.
    inactive(p, row['before'])
    assert file_hash(p) == record['original_sha256'], 'Source changed before removal'
    p.unlink(); sync_dir(p.parent)
    record['status'] = 'ARCHIVED'; save(receipt, record)
    return record

def run(limit):
    plan = json.loads(PLAN.read_text()); done = []; new = 0
    for row in plan['files']:
        receipt = path_in_root(row['receipt'])
        if receipt.exists() and not path_in_root(row['path']).exists():
            record = json.loads(receipt.read_text())
            if record['status'] == 'ARCHIVED': done.append(record); continue
        if limit is not None and new >= limit: break
        record = archive_one(row); done.append(record); new += 1
        print('ARCHIVED', len(done), row['path'], 'savedGiB', round(record['saved_allocated_bytes'] / 2**30, 3), flush=True)
        save(AUDIT / 'archive-progress.json', dict(archived_files=len(done), planned_files=len(plan['files']),
            original_bytes=sum(x['before']['size'] for x in done), compressed_bytes=sum(x['compressed_bytes'] for x in done),
            saved_allocated_bytes=sum(x['saved_allocated_bytes'] for x in done)))
    assert file_hash(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == plan['active_pointer_sha256']
    print('DONE', len(done), '/', len(plan['files']), flush=True)

def verify():
    plan = json.loads(PLAN.read_text()); result = []
    for row in plan['files']:
        receipt = path_in_root(row['receipt'])
        if not receipt.exists(): continue
        r = json.loads(receipt.read_text()); archive = path_in_root(row['archive'])
        assert file_hash(archive) == r['archive_sha256']
        with gzip.open(archive, 'rb') as f: assert stream_hash(f) == (r['original_sha256'], row['before']['size'])
        assert r['status'] in ('ARCHIVED', 'RESTORED')
        if r['status'] == 'ARCHIVED': assert not path_in_root(row['path']).exists()
        else: assert file_hash(path_in_root(row['path'])) == r['original_sha256']
        result.append(dict(path=row['path'], sha256=r['original_sha256'], status=r['status']))
    assert file_hash(ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json') == plan['active_pointer_sha256']
    save(AUDIT / 'archive-verification.json', dict(status='PASS', planned_files=len(plan['files']), verified_files=len(result), records=result))
    print('VERIFIED', len(result), flush=True)

def restore(path=None, adr=None):
    assert bool(path) != bool(adr), 'Choose --path or --adr'
    plan = json.loads(PLAN.read_text())
    rows = [r for r in plan['files'] if r['path'] == path or (adr and Path(r['path']).parts[2].split('-')[:2] == adr.split('-'))]
    assert rows, 'No matching archived records'
    for row in rows:
        p = path_in_root(row['path']); receipt = path_in_root(row['receipt']); archive = path_in_root(row['archive'])
        r = json.loads(receipt.read_text())
        if p.exists():
            assert file_hash(p) == r['original_sha256']; continue
        assert min(shutil.disk_usage(ROOT).free, shutil.disk_usage('/mnt/c').free) > row['before']['size'] + 2 * 2**30
        assert file_hash(archive) == r['archive_sha256']
        temp = p.with_name('.' + p.name + '.restoring')
        with gzip.open(archive, 'rb') as src, temp.open('xb') as dst:
            shutil.copyfileobj(src, dst, CHUNK); dst.flush(); os.fsync(dst.fileno())
        assert file_hash(temp) == r['original_sha256'] and temp.stat().st_size == row['before']['size']
        os.chmod(temp, row['before']['mode']); os.utime(temp, ns=(row['before']['mtime_ns'], row['before']['mtime_ns']))
        os.link(temp, p); temp.unlink(); sync_dir(p.parent)
        r['status'] = 'RESTORED'; save(receipt, r)
        print('RESTORED', row['path'], flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('plan'); a = sub.add_parser('archive'); a.add_argument('--limit', type=int)
    sub.add_parser('verify'); r = sub.add_parser('restore'); r.add_argument('--path'); r.add_argument('--adr')
    args = parser.parse_args()
    if args.command == 'plan': make_plan()
    elif args.command == 'archive': run(args.limit)
    elif args.command == 'verify': verify()
    else: restore(args.path, args.adr)

if __name__ == '__main__': main()
