"""Zero-based legacy SHA parts through Dataiku streams, never modifying uploads."""
import hashlib
import os
from pathlib import Path
import re
import time
import uuid
import zipfile
from . import oracle_query_package as transport
from .oracle_transfer_progress import tracking, report, check
from semantic_runtime import oracle_dp_io as io


def _text(raw):
    return raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')


def _rows(raw):
    result=[]
    for line in _text(raw).splitlines():
        if not line.strip():continue
        m=re.fullmatch(r'([0-9a-fA-F]{64}) [ *](?:\./)?([^\r\n]+)',line)
        if not m:raise io.DPError('CHECKSUM_FORMAT: GNU sha256sum lines required')
        sha,name=m.groups()
        if '/' in name or '\\' in name or name.startswith('.') or '\x00' in name:raise io.DPError('CHECKSUM_PATH')
        result.append((name,sha.lower()))
    if not result or len({r[0] for r in result})!=len(result):raise io.DPError('CHECKSUM_DUPLICATE_OR_EMPTY')
    return dict(sorted(result))


def inspect_parts(open_stream,names,*,original_file='',parts_file=''):
    # Normalize API's root prefix; nested files require moving to this input root.
    names=[n[1:] if n.startswith('/') else n for n in names]
    if len(set(names))!=len(names):raise io.DPError('DUPLICATE_UPLOAD_PATH')
    present=set(names)
    def metadata(stem,explicit):
        candidates=[explicit] if explicit else sorted(n for n in present if re.fullmatch(stem+r'(?: \([0-9]+\))?\.sha256',n))
        if not candidates or any(n not in present for n in candidates):raise io.DPError('MISSING_CHECKSUM: '+stem+'.sha256')
        values=[]
        for name in candidates:
            if '/' in name or '\\' in name:raise io.DPError('CHECKSUM_PATH')
            with open_stream('/'+name) as src:
                raw=bytearray()
                while len(raw)<=4*1024**2:
                    b=src.read(min(65536,4*1024**2+1-len(raw)))
                    if not b:break
                    raw.extend(b)
                if len(raw)>4*1024**2:raise io.DPError('METADATA_SIZE')
            values.append(_rows(bytes(raw)))
        if any(v!=values[0] for v in values):raise io.DPError('AMBIGUOUS_CHECKSUM: '+', '.join(candidates)+'; select exact *_SHA_FILE')
        return values[0],candidates
    original,original_names=metadata('ORIGINAL',original_file)
    parts,parts_names=metadata('PARTS',parts_file)
    if len(original)!=1:raise io.DPError('ORIGINAL_CHECKSUM: exactly one ZIP required')
    archive,sha=next(iter(original.items()))
    if not archive.lower().endswith('.zip'):raise io.DPError('ORIGINAL_NAME')
    expected=[archive+f'.part{i:06d}' for i in range(len(parts))]
    if not 1<=len(parts)<=100000 or list(parts)!=expected:raise io.DPError('PART_SEQUENCE: require consecutive part000000 onwards')
    missing=sorted(set(parts)-present);extra=sorted(n for n in present if n.startswith(archive+'.part') and n not in parts)
    if missing or extra:raise io.DPError('PART_FILES: missing='+str(missing)+' extra='+str(extra))
    return {'status':'LEGACY_PARTS_READY','archive_name':archive,'archive_sha256':sha,
            'parts':[{'name':n,'sha256':parts[n]} for n in expected],
            'part_count':len(parts),'original_checksum_files':original_names,'parts_checksum_files':parts_names,
            'content_verified':False,'oracle_written':False}


def join_parts(open_stream,names,output,*,original_file='',parts_file='',binding='',seconds=21600):
    if not 1<=seconds<=21600:raise io.DPError('BUDGET: seconds1..21600')
    info=inspect_parts(open_stream,names,original_file=original_file,parts_file=parts_file)
    with transport.job(output) as folder,tracking(output,lambda s,**kw:transport.event(output,s,**kw)) as progress:
        path=folder/'legacy-join-state.json'
        identity={'binding':binding,'archive_sha256':info['archive_sha256'],'parts':info['parts'],'code':io.file_sha(__file__)}
        state=transport.bounded_json(path) if path.exists() else {'identity':identity,'deadline':time.time()+7*86400}
        if state['identity']!=identity:raise io.DPError('JOIN_BINDING: folder/metadata/code changed')
        progress.deadline=min(time.time()+seconds,state['deadline'])
        target=folder/'legacy-verified.zip'
        try:
            check();state['status']='JOINING';io.atomic_json(path,state)
            def digest_file(file):
                h=hashlib.sha256();count=0
                with file.open('rb') as src:
                    while b:=src.read(1024**2):check();h.update(b);count+=len(b);report(bytes_done=count)
                return h.hexdigest()
            if target.exists() or target.is_symlink():
                report('EXISTING_ZIP_VERIFY',file=target.name)
                if target.is_symlink() or digest_file(target)!=info['archive_sha256']:raise io.DPError('ZIP_CONFLICT: preserve existing output')
                state.update(status='VERIFIED_ZIP_READY',zip=str(target));io.atomic_json(path,state);return str(target)
            temp=folder/('legacy-verified.zip.partial-'+uuid.uuid4().hex)
            state.update(partial_output=str(temp),verified_parts=[],tail_recovery=None);io.atomic_json(path,state)
            recovered=False
            with temp.open('xb') as dst:
                for index,item in enumerate(info['parts']):
                    report('JOIN_LEGACY_PART',file=item['name'],part_number=index+1,part_total=len(info['parts']))
                    check();start=dst.tell();h=hashlib.sha256();less=hashlib.sha256();tail=b'';count=0
                    with open_stream('/'+item['name']) as src:
                        while b:=src.read(1024**2):
                            check();count+=len(b)
                            if count>50_000_001:raise io.DPError('PART_SIZE: exceeds supported 50MB plus one byte')
                            h.update(b);combined=tail+b;less.update(combined[:-1]);tail=combined[-1:]
                            dst.write(b);report(bytes_done=count)
                    selected=count
                    if h.hexdigest()!=item['sha256']:
                        if recovered or count<2 or less.hexdigest()!=item['sha256']:
                            raise io.DPError('PART_HASH: re-upload '+item['name'])
                        selected-=1;dst.truncate(start+selected);dst.seek(start+selected);recovered=True
                        state['tail_recovery']={'part':item['name'],'input_bytes':count,'selected_bytes':selected,'part_sha_verified':True}
                        transport.event(folder,'TAIL_BYTE_CANDIDATE',**state['tail_recovery'])
                    state['verified_parts'].append({'name':item['name'],'bytes':selected,'sha256':item['sha256']})
                    dst.flush();os.fsync(dst.fileno());io.atomic_json(path,state)
                    transport.event(folder,'PART_VERIFIED',part=index+1,total=len(info['parts']),file=item['name'])
                dst.flush();os.fsync(dst.fileno())
            report('WHOLE_ZIP_VERIFY',file=temp.name)
            if digest_file(temp)!=info['archive_sha256']:raise io.DPError('WHOLE_ZIP_HASH: no completed ZIP published')
            if not zipfile.is_zipfile(temp):raise io.DPError('NOT_A_ZIP')
            os.link(temp,target);temp.unlink()  # Verified temporary hard link only; uploads untouched.
            state.update(status='VERIFIED_ZIP_READY',zip=str(target),whole_sha256_verified=True)
            io.atomic_json(path,state);transport.event(folder,'VERIFIED_ZIP_READY',zip=str(target),recovered_tail_byte=recovered)
            return str(target)
        except BaseException as exc:
            state.update(status='PAUSED' if isinstance(exc,io.BudgetPause) else 'FAILED',error=str(exc) if isinstance(exc,io.DPError) else type(exc).__name__)
            io.atomic_json(path,state);raise
