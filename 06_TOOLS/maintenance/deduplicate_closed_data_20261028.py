"""One-off, bounded deduplication of closed immutable data; preserves every path.

Only independent historical SQLite files from the recorded inventory qualify.
Mutable caches, drafts, active MAIN data, sidecars and open files are excluded.
Full SHA256 is required. Shared outputs are made read-only. No DB row changes.
"""
from pathlib import Path
import collections, hashlib, json, os, stat, sys, time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '09_ARTIFACTS/AUDITS/20261028-storage-cleanup'
PLAN = OUT / 'dedup-plan.json'

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def meta(path):
    s = path.lstat()
    return dict(dev=s.st_dev, ino=s.st_ino, size=s.st_size, blocks=s.st_blocks,
                mode=stat.S_IMODE(s.st_mode), mtime_ns=s.st_mtime_ns,
                uid=s.st_uid, gid=s.st_gid, nlink=s.st_nlink)

def opened():
    ids = set()
    denied = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or proc.name == str(os.getpid()): continue
        try:
            if proc.stat().st_uid != os.getuid(): continue
            for fd in (proc / 'fd').iterdir():
                try:
                    s = fd.stat(); ids.add((s.st_dev, s.st_ino))
                except FileNotFoundError: pass
            for line in (proc / 'maps').read_text().splitlines():
                fields = line.split(None, 5)
                if len(fields) == 6 and fields[5].startswith(str(ROOT / '01_DATA') + '/'):
                    p = Path(fields[5])
                    if p.exists():
                        s = p.stat(); ids.add((s.st_dev, s.st_ino))
        except (FileNotFoundError, ProcessLookupError): pass
        except PermissionError:
            name = (proc / 'comm').read_text().strip()
            if name not in ('systemd', '(sd-pam)'): denied.append([proc.name, name])
    if denied: raise RuntimeError('Cannot inspect same-user processes: ' + repr(denied))
    return ids

def active():
    pointer = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    release = json.loads((ROOT / json.loads(pointer.read_text())['manifest_path']).read_text())
    folder = ROOT / release['data_path']
    ids = set()
    for base, dirs, files in os.walk(folder, followlinks=True):
        for name in files:
            p = Path(base) / name
            s = p.stat(); ids.add((s.st_dev, s.st_ino))
    return digest(pointer), ids

def eligible(path, m, excluded):
    rel = str(path.relative_to(ROOT))
    return (rel.startswith('01_DATA/') and path.resolve() == path and path.suffix == '.sqlite'
            and not any(x in rel for x in ('/cache/', '/glossary-draft/', '/domain_graph/', '/links/'))
            and m['nlink'] == 1 and m['uid'] == os.getuid()
            and (m['dev'], m['ino']) not in excluded
            and time.time_ns() - m['mtime_ns'] > 48 * 3600 * 10**9
            and not any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')))

def plan():
    assert not PLAN.exists(), 'Existing plan must be preserved'
    pointer, active_ids = active()
    excluded = active_ids | opened()
    groups = []
    for group in json.loads(Path('/tmp/storage-sample-groups.json').read_text()):
        candidates = []
        for rel in group['paths']:
            p = ROOT / rel; m = meta(p)
            if eligible(p, m, excluded): candidates.append((p, m))
        if len(candidates) < 2: continue
        hashes = collections.defaultdict(list)
        for p, m in candidates:
            h = digest(p)
            assert meta(p) == m, 'Changed during hash: ' + str(p)
            hashes[h].append(dict(path=str(p.relative_to(ROOT)), before=m))
            print('HASH', p.relative_to(ROOT), flush=True)
        for h, rows in hashes.items():
            if len(rows) > 1:
                groups.append(dict(sha256=h, files=rows))
    save(PLAN, dict(pointer_sha256=pointer, groups=groups,
                   expected_reclaimed_bytes=sum(row['before']['blocks'] * 512 for g in groups for row in g['files'][1:])))
    print('PLAN', len(groups), 'groups', flush=True)

def apply():
    data = json.loads(PLAN.read_text())
    result_path = OUT / 'dedup-result.json'
    assert not result_path.exists(), 'Preserve previous operation receipt'
    pointer, active_ids = active()
    assert pointer == data['pointer_sha256']
    result = dict(status='RUNNING', pointer_sha256=pointer, files=[], reclaimed_bytes=0)
    save(result_path, result)
    for group in data['groups']:
        excluded = active_ids | opened()
        for row in group['files']:
            p = ROOT / row['path']
            assert meta(p) == row['before'] and eligible(p, row['before'], excluded), row['path']
            assert digest(p) == group['sha256'], row['path']
        source_row = group['files'][0]
        source = ROOT / source_row['path']
        os.chmod(source, source_row['before']['mode'] & ~0o222)
        save(OUT / ('group-' + group['sha256'] + '.json'), group)
        for row in group['files'][1:]:
            p = ROOT / row['path']
            assert meta(p) == row['before']
            assert (row['before']['dev'], row['before']['ino']) not in opened()
            temp = p.with_name('.' + p.name + '.dedup-20261028')
            assert not temp.exists()
            os.link(source, temp)
            assert os.path.samefile(source, temp)
            os.replace(temp, p)
            fd = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
            assert os.path.samefile(source, p)
            result['files'].append(dict(path=row['path'], source=source_row['path'], sha256=group['sha256'],
                                        before=row['before'], after=meta(p)))
            result['reclaimed_bytes'] += row['before']['blocks'] * 512
            save(result_path, result)
            print('SHARED', row['path'], flush=True)
        assert digest(source) == group['sha256']
    assert active()[0] == pointer
    result['status'] = 'COMPLETE'
    result['all_paths_preserved'] = True
    result['shared_files_readonly'] = True
    save(result_path, result)
    print('COMPLETE_GIB', result['reclaimed_bytes'] / 2**30, flush=True)

if __name__ == '__main__':
    {'plan': plan, 'apply': apply}[sys.argv[1]]()
