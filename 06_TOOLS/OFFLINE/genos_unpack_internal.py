#!/usr/bin/env python3
"""Onsite ZIP merge and duplicate audit. Standard library only; never delete RAW.

Default is a dry run. Archive directory/file names are retained (CP949 supported).
Existing equal files are reused; differing destination contents block ALL writes.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
import zipfile


def digest_file(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def plain(p):
    p=Path(p).absolute()
    if any(x.is_symlink() for x in (p,*p.parents)):raise ValueError('symlink path: '+str(p))
    return p

def member_path(info, encoding):
    name=info.filename
    if not info.flag_bits & 0x800:
        try:name=name.encode('cp437').decode(encoding)
        except (UnicodeError,LookupError):
            # ASCII works for every supported encoding; undecodable legacy names
            # require an explicit encoding instead of silently corrupting names.
            if not name.isascii():raise ValueError('ZIP filename decoding failed; use --encoding: '+repr(name))
    name=name.replace('\\','/')
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or any(':' in x or any(ord(c)<32 for c in x) for x in p.parts):
        raise ValueError('unsafe ZIP path: '+repr(name))
    mode=info.external_attr >> 16
    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
        raise ValueError('ZIP link/special member: '+name)
    if info.flag_bits & 1:raise ValueError('encrypted ZIP: '+name)
    return p

def scan(root):
    rows=[]
    for p in sorted(root.rglob('*')):
        plain(p)
        if p.is_file() and p.suffix.lower() in {'.doc','.docx','.hwp','.hwpx','.pdf','.xml','.html','.htm'}:
            rows.append({'relative_path':p.relative_to(root).as_posix(),'sha256':digest_file(p),
                         'bytes':p.stat().st_size,'format':p.suffix.lower()})
    return rows

def audit_rows(rows):
    hashes=defaultdict(list);names=defaultdict(list)
    for r in rows:
        hashes[r['sha256']].append(r['relative_path'])
        p=PurePosixPath(r['relative_path']);base=re.sub(r'\s*\([1-9]\d{0,2}\)$','',unicodedata.normalize('NFC',p.stem))
        names[(str(p.parent),base,p.suffix.lower())].append(r)
    return {'exact_duplicates':[{'sha256':h,'paths':ps} for h,ps in hashes.items() if len(ps)>1],
            'similar_names_different_contents':[[{'path':r['relative_path'],'sha256':r['sha256']} for r in group]
                for group in names.values() if len({r['sha256'] for r in group})>1]}

def run(args):
    root=plain(args.root);root.mkdir(parents=True,exist_ok=True)
    report=plain(args.report)
    if root==report or root in report.parents:raise ValueError('report must be outside the original document folder')
    if report.exists():raise ValueError('report already exists; choose a new report path')
    archives=[plain(p) for p in (args.zip or sorted(root.glob('*.zip')))]
    planned={};directories=set();sources=[];conflicts=[];total=0;skipped=[]
    for archive in archives:
        identity=digest_file(archive);sources.append({'path':str(archive),'sha256':identity})
        with zipfile.ZipFile(archive) as z:
            if len(z.infolist()) > 100000:raise ValueError('ZIP member count limit exceeded')
            entries=[(i,member_path(i,args.encoding)) for i in z.infolist()]
            files=[(i,p) for i,p in entries if not i.is_dir()]
            nested=bool(files) and all(len(p.parts)>1 and unicodedata.normalize('NFC',p.parts[0])==unicodedata.normalize('NFC',archive.stem) for _,p in files)
            base=root if args.layout=='root' or (args.layout=='auto' and nested) else root/archive.stem
            for info,rel in entries:
                if info.is_dir():directories.add(plain(base/Path(*rel.parts)))
            for info,rel in files:
                if rel.parts[0]=='__MACOSX' or rel.name in {'Thumbs.db','desktop.ini','.DS_Store'}:
                    skipped.append(str(rel));continue
                total+=info.file_size
                if total>args.max_bytes:raise ValueError('expanded ZIP byte limit exceeded')
                target=plain(base/Path(*rel.parts));target.relative_to(root)
                with z.open(info) as f:h=hashlib.file_digest(f,'sha256').hexdigest()
                row={'zip':str(archive),'zip_sha256':identity,'member':info.filename,'member_name':str(rel),
                     'target':str(target),'relative_path':target.relative_to(root).as_posix(),'sha256':h,'bytes':info.file_size}
                if target.exists():
                    if not target.is_file() or digest_file(target)!=h:conflicts.append(row)
                    row['action']='REUSE' if not conflicts or conflicts[-1] is not row else 'CONFLICT'
                else:row['action']='COPY'
                old=planned.get(str(target))
                if old and old['sha256']!=h:conflicts.extend([old,row])
                else:planned.setdefault(str(target),row)
        if digest_file(archive)!=identity:raise ValueError('ZIP changed during inspection')
    # Detect ancestor-file collisions before publishing even the first file.
    for target in [*(Path(p) for p in planned), *directories]:
        for parent in target.parents:
            if parent == root:break
            if (parent.exists() and not parent.is_dir()) or str(parent) in planned:
                conflicts.append({'target':str(target),'reason':'ancestor_is_file','ancestor':str(parent)})
        if target in directories and ((target.exists() and not target.is_dir()) or str(target) in planned):
            conflicts.append({'target':str(target),'reason':'directory_is_file'})
    before=scan(root)
    virtual={r['relative_path']:r for r in before}
    for row in planned.values():virtual.setdefault(row['relative_path'],{**row,'format':Path(row['target']).suffix.lower()})
    result={'schema_version':'internal-zip-merge-v1','root':str(root),'applied':False,'originals_deleted':False,
            'archives':sources,'files':list(planned.values()),'conflicts':conflicts,'skipped':skipped,
            'directories':[str(p.relative_to(root)) for p in sorted(directories)],
            'nested_archives_not_expanded':[r['relative_path'] for r in planned.values() if Path(r['target']).suffix.lower()=='.zip'],
            'before':audit_rows(before),'after_planned':audit_rows(list(virtual.values())),'pipeline_selection':'structured-primary-pdf-reference-v2'}
    if args.apply and not conflicts:
        for source in sources:
            if digest_file(source['path'])!=source['sha256']:raise ValueError('ZIP changed before apply')
        for directory in sorted(directories):directory.mkdir(parents=True,exist_ok=True)
        # A same-directory exclusive hard-link publish prevents overwriting even
        # if another process creates the destination after the preflight.
        for row in planned.values():
            target=plain(row['target'])
            if target.exists():
                if digest_file(target)!=row['sha256']:raise ValueError('destination changed during apply')
                continue
            target.parent.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(prefix='.zip-merge-',dir=target.parent)
            try:
                with os.fdopen(fd,'wb') as out,zipfile.ZipFile(row['zip']) as z,z.open(row['member']) as inp:
                    while chunk:=inp.read(1024*1024):out.write(chunk)
                    out.flush();os.fsync(out.fileno())
                if digest_file(tmp)!=row['sha256']:raise ValueError('extracted checksum mismatch')
                os.link(tmp,target)
            finally:Path(tmp).unlink(missing_ok=True)
        result['applied']=True;result['after']=audit_rows(scan(root))
    report.parent.mkdir(parents=True,exist_ok=True)
    with report.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'applied':result['applied'],'archives':len(sources),'planned_files':len(planned),'conflicts':len(conflicts),'exact_duplicate_groups':len(result['after_planned']['exact_duplicates']),'report':str(report)},ensure_ascii=False))
    return 2 if conflicts else 0

def main(argv=None):
    repo=Path(__file__).resolve().parents[2]
    layout=json.loads((repo/'00_SYSTEM/WORKSPACE.json').read_text())
    data=repo/next(r['canonical_path'] for r in layout['roots'] if r['id']=='data')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=data/'RAW/internal')
    p.add_argument('--zip',action='append',type=Path)
    p.add_argument('--layout',choices=['auto','root','named'],default='auto')
    p.add_argument('--encoding',default='cp949')
    p.add_argument('--max-bytes',type=int,default=4*1024**3)
    p.add_argument('--apply',action='store_true')
    p.add_argument('--report',type=Path,default=data/'LOGS'/('internal-zip-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json'))
    args=p.parse_args(argv)
    # Same lock as the maintained builder; do not merge into RAW during a build.
    data.mkdir(parents=True,exist_ok=True)
    with (data/'.raw-migration.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return run(args)

if __name__=='__main__':raise SystemExit(main())
