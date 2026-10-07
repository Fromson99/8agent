"""Standalone minimum-unit FTS + verification on a completed R8 navigation; no activation."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import re


def locate_baseline(dev, data, run_id, *, explicit=None, roots=None):
    """Choose only this explicit run, never the newest or a different run."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',run_id):raise ValueError('Invalid run ID')
    roots=roots if roots is not None else [Path(data),Path(dev)/'01_DATA',Path('/workspace/01_DATA')]
    roots=list(dict.fromkeys(Path(p).resolve() for p in roots))
    def complete(path):
        if not path.is_dir():return False
        required=('result.json','generation/manifest.json','generation/store.sqlite','generation/navigation/manifest.json','generation/navigation/navigation.sqlite','links/report.json','audit/navigation/manifest.json','audit/navigation/navigation.sqlite')
        if not all((path/name).is_file() for name in required):return False
        try:
            value=json.loads((path/'result.json').read_text())
            return value.get('schema_version')=='term-generation-build-v1' and value.get('generation')=='generation'
        except (ValueError,OSError):return False
    if explicit:
        path=Path(explicit).resolve()
        if path.name!='baseline' or path.parent.name!='reindex' or not complete(path):
            raise ValueError('Explicit GENOS_FT_BASELINE has no completed baseline: '+str(path))
        print('BASELINE SELECTED explicit='+str(path),flush=True);return path
    candidates=[]
    for root in roots:
        path=root/'TERM_RELEASES'/run_id/'reindex/baseline'
        print('BASELINE CHECK '+str(path)+' completed='+str(complete(path)),flush=True)
        if complete(path):candidates.append(path.resolve())
    candidates=list(dict.fromkeys(candidates))
    if len(candidates)==1:
        print('BASELINE SELECTED run='+run_id+' path='+str(candidates[0]),flush=True);return candidates[0]
    if len(candidates)>1:
        raise ValueError('Multiple completed baselines for selected run; set GENOS_FT_BASELINE to one exact path: '+', '.join(map(str,candidates)))
    # Bounded directory metadata only, for troubleshooting a mistyped run. Never auto-select these.
    for root in roots:
        release=root/'TERM_RELEASES'
        if not release.is_dir():continue
        shown=0
        for child in sorted(release.iterdir()):
            if child.is_dir() and complete(child/'reindex/baseline'):
                print('AVAILABLE BASELINE (not selected) run='+child.name+' path='+str(child/'reindex/baseline'),flush=True);shown+=1
                if shown>=20:break
    raise ValueError('No completed baseline for GENOS_FT_RUN='+run_id+'. Check the available run IDs or set GENOS_FT_BASELINE to the original R8 completed baseline path. No directory or navigation was created.')


def selected_helper(path):
    name='semantic_runtime.genos_selected_unit_fulltext'
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def mount_info(path):
    """Report actual local mount metadata; do not infer NFS publication from a path."""
    found=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before,after=line.split(' - ',1);fields=before.split();info=after.split()
        mount=Path(fields[4].replace('\\040',' '))
        if path.is_relative_to(mount):found.append((len(str(mount)),{'mount':str(mount),'filesystem':info[0],'source':info[1]}))
    return max(found,key=lambda x:x[0])[1] if found else {'filesystem':'unknown'}


@contextmanager
def exclusive(reindex):
    if not (reindex/'baseline/result.json').is_file():
        raise ValueError('Completed baseline/result.json missing: '+str(reindex/'baseline/result.json'))
    with (reindex/'.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Existing R8/reindex worker still holds the lock. Stop it with Ctrl+C in its own terminal first.')
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def run(baseline,output,helper,log,workers=2):
    from semantic_runtime.contracts import sha
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    from semantic_runtime import fulltext,navigation_storage
    from genos_reindex_logging import atomic
    baseline,output=Path(baseline).resolve(),Path(output).resolve()
    if output.parent!=baseline.parent or output==baseline:
        raise ValueError('Output must be a separate sibling of baseline')
    if workers<1:raise ValueError('workers must be positive')
    generation=baseline/'generation'
    receipt_path=output/'continuation.json'
    with exclusive(baseline.parent):
        with log.phase('completed-navigation-verification'):
            result=json.loads((baseline/'result.json').read_text())
            if result.get('schema_version')!='term-generation-build-v1' or result.get('generation')!='generation':
                raise ValueError('Completed baseline result missing or incompatible')
            if sha(generation/'manifest.json')!=result['manifest_sha256']:raise ValueError('Baseline manifest mismatch')
            with closing(Store(generation)) as store:
                binding=store.manifest['navigation'];nav=(generation/binding['path']).resolve();nav.relative_to(generation)
                if sha(nav/'manifest.json')!=binding['manifest_sha256']:raise ValueError('Navigation manifest mismatch')
                index=TermIndex(nav,store);nm=index.manifest;sm=store.manifest
            pins={str(p):sha(p) for p in (baseline/'result.json',generation/'manifest.json',generation/'store.sqlite',nav/'manifest.json',nav/'navigation.sqlite',baseline/'links/report.json')}
            report=json.loads((baseline/'links/report.json').read_text())
            # Generation identity is already bound to this connection report by native builder.
            if 'links' in result['identity'] and result['identity']['links']!=report.get('identity'):
                raise ValueError('Connection identity mismatch')
            audit=result.get('navigation_audit')
            if not audit or audit.get('path')!='audit/navigation' or nm.get('storage',{}).get('audit_manifest_sha256')!=audit['manifest_sha256']:
                raise ValueError('Completed audit binding missing')
            pins[str(baseline/'audit/navigation/manifest.json')]=audit['manifest_sha256']
            # Exact installed code used for checks/tokenization is recorded and rechecked.
            code_pins={str(Path(m.__file__).resolve()):sha(m.__file__) for m in (fulltext,navigation_storage,sys.modules[Store.__module__],sys.modules[TermIndex.__module__])}
            identity={'baseline':str(baseline),'pins':pins,'code_pins':code_pins,'builder_sha256':sha(helper.__file__),'runner_sha256':sha(__file__),
                      'tokenizer_version':fulltext.tokenizer_version(),'granularity':'stored-own-block-owner'}
            log.emit('storage','SELECTED',baseline=str(baseline),output=str(output),mount=mount_info(output.parent),document_count=nm['document_count'],shared_publication=False)
        old=json.loads(receipt_path.read_text()) if receipt_path.is_file() else None
        if old and old['identity']!=identity:raise ValueError('Continuation input/code changed; use a new GENOS_FT_NAME')
        target=output/'fulltext-units'
        if not old:
            if output.exists():
                if output.is_symlink():raise ValueError('Output symlink rejected')
                retained=output.with_name(output.name+'.incomplete-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+str(os.getpid()))
                output.rename(retained);log.emit('preserve-incomplete','DONE',path=str(retained),restart_scope='fulltext-only')
            output.mkdir()
            previous=getattr(fulltext,'_BUILD_PROGRESS',None)
            fulltext._BUILD_PROGRESS=log.progress
            try:
                with log.phase('minimum-unit-fulltext-build',workers=workers):helper.build(generation,nav,target,workers=workers)
            finally:
                if previous is None:delattr(fulltext,'_BUILD_PROGRESS')
                else:fulltext._BUILD_PROGRESS=previous
        with log.phase('minimum-unit-fulltext-verification'):
            idx=helper.UnitFulltextIndex(target,nm);manifest=idx.manifest
            if (manifest['source_manifest_sha256']!=pins[str(generation/'manifest.json')] or manifest['navigation_manifest_sha256']!=pins[str(nav/'manifest.json')] or manifest['builder_sha256']!=identity['builder_sha256'] or manifest['tokenizer_code_sha256']!=code_pins[str(Path(fulltext.__file__).resolve())]):
                raise ValueError('Unit fulltext provenance mismatch')
            if manifest['scope']['document_version_ids']!=sm['scope']['document_version_ids'] or manifest['counts']['covered_blocks']!=sm['counts']['source_block'] or manifest['counts']['covered_blocks']!=manifest['counts']['navigation_blocks']:
                raise ValueError('Unit fulltext source block/document coverage mismatch')
            if old and sha(target/'manifest.json')!=old['fulltext_manifest_sha256']:raise ValueError('Completed fulltext manifest changed')
            with closing(idx.connect()) as db:
                for table in ('unit','unit_fts'):
                    if db.execute('SELECT count(*) FROM '+table).fetchone()[0]!=manifest['counts']['unit']:raise ValueError('Fulltext row coverage mismatch')
                sample=db.execute("SELECT u.key,u.source_id,f.body FROM unit u JOIN unit_fts f ON f.key=u.key WHERE length(f.body)>0 LIMIT 1").fetchone()
                if sample:
                    token=sample[2].split()[0]
                    hits=idx.rank_units(db,[token],{sample[1]})
                    if sample[0] not in {h['key'] for h in hits}:raise ValueError('Minimum unit search smoke failed')
        # Full audit SHA is required, but streaming progress makes the 25GB read visible.
        with log.phase('audit-byte-verification',path=str(baseline/'audit/navigation/navigation.sqlite')):
            previous_sha=navigation_storage.sha
            def metered_sha(path):
                path=Path(path);total=path.stat().st_size;done=0;digest=hashlib.sha256()
                log.progress(task='sha256:'+path.name,completed=0,total=total,unit='bytes')
                with path.open('rb') as stream:
                    while chunk:=stream.read(8*1024*1024):
                        digest.update(chunk);done+=len(chunk);log.progress(task='sha256:'+path.name,completed=done,total=total,unit='bytes')
                return digest.hexdigest()
            navigation_storage.sha=metered_sha
            try:navigation_storage.verify_audit(baseline/audit['path'],expected_manifest_sha256=audit['manifest_sha256'],expected_index_sha256=nm['index_sha256'])
            finally:navigation_storage.sha=previous_sha
        with log.phase('final-input-binding-verification'):
            for name,expected in {**pins,**code_pins}.items():
                if sha(name)!=expected:raise ValueError('Pinned input/code changed: '+name)
            if sha(helper.__file__)!=identity['builder_sha256']:raise ValueError('Selected unit builder changed')
            receipt={'schema_version':'genos-unit-fulltext-continuation-v1','identity':identity,'completed':True,
                     'counts':manifest['counts'],'fulltext_path':str(target),'fulltext_manifest_sha256':sha(target/'manifest.json'),
                     'navigation_rebuilt':False,'structure_rebuilt':False,'glossary_rebuilt':False,'model_calls':0,
                     'activated':False,'serving_verified':False,'shared_published':False,
                     'runtime':{'executable':sys.executable,'python':sys.version},'mount':mount_info(output)}
            atomic(receipt_path,receipt)
        log.emit('continuation','VERIFIED',path=str(receipt_path),counts=manifest['counts'],activated=False)
        return receipt


def publish_shared(baseline, output, shared_root, helper, log):
    """Copy one verified generation and its audit to a new shared directory; no pointers."""
    from semantic_runtime.contracts import sha
    from semantic_runtime.storage import Store
    from semantic_runtime.term_index import TermIndex
    from genos_reindex_logging import atomic
    baseline,output,shared_root=map(lambda p:Path(p).resolve(),(baseline,output,shared_root))
    if not shared_root.is_dir():raise ValueError('Existing shared NFS root required')
    if shared_root.is_relative_to(baseline.parent) or baseline.parent.is_relative_to(shared_root):raise ValueError('Shared root must be separate from workspace build')
    local=json.loads((output/'continuation.json').read_text())
    if not local.get('completed'):raise ValueError('Local verification incomplete')
    run_id=baseline.parent.parent.name
    final=shared_root/run_id/output.name
    log.emit('shared-storage','SELECTED',root=str(shared_root),mount=mount_info(shared_root),generation_path=str(final/'generation'))
    with exclusive(baseline.parent):
        if final.exists():
            previous=json.loads((final/'publication.json').read_text())
            if previous['continuation_sha256']!=sha(output/'continuation.json'):raise ValueError('Shared publication differs; use a new output name')
            inventory=previous['files'];tmp=final
        else:
            final.parent.mkdir(parents=True,exist_ok=True)
            tmp=Path(tempfile.mkdtemp(prefix='.'+final.name+'-',dir=final.parent))
            inventory={};entries=[]
            for source_root,prefix in ((baseline/'generation','generation'),(baseline/'links','links'),(baseline/'audit','audit'),(output/'fulltext-units','generation/fulltext-units')):
                for source in source_root.rglob('*'):
                    if source.is_symlink():raise ValueError('Shared publication symlink rejected')
                    if source.is_file():entries.append((source,Path(prefix)/source.relative_to(source_root)))
            entries.extend([(baseline/'result.json',Path('baseline-result.json')),(output/'continuation.json',Path('continuation.json')),
                            (Path(helper.__file__),Path('selected-code/unit_fulltext_selected.py'))])
            total=sum(p.stat().st_size for p,_ in entries);done=0
            with log.phase('shared-copy',target=str(tmp),bytes=total):
                for source,relative in entries:
                    destination=tmp/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                    digest=hashlib.sha256()
                    with source.open('rb') as inp,destination.open('xb') as out:
                        while chunk:=inp.read(8*1024*1024):
                            out.write(chunk);digest.update(chunk);done+=len(chunk)
                            log.progress(task='nfs-copy',completed=done,total=total,unit='bytes')
                        out.flush();os.fsync(out.fileno())
                    inventory[str(relative)]={'sha256':digest.hexdigest(),'bytes':destination.stat().st_size}
                    expected=local['identity']['pins'].get(str(source))
                    if source==baseline/'audit/navigation/navigation.sqlite':
                        expected=json.loads((baseline/'audit/navigation/manifest.json').read_text())['audit_sha256']
                    if source==output/'fulltext-units/units.sqlite':
                        expected=json.loads((output/'fulltext-units/manifest.json').read_text())['index_sha256']
                    if source==Path(helper.__file__):expected=local['identity']['builder_sha256']
                    if expected and digest.hexdigest()!=expected:raise ValueError('Pinned source changed during NFS copy')
                m=json.loads((tmp/'generation/manifest.json').read_text())
                fm=json.loads((tmp/'generation/fulltext-units/manifest.json').read_text())
                m['fulltext']={'path':'fulltext-units','manifest_sha256':sha(tmp/'generation/fulltext-units/manifest.json'),'navigation_index_sha256':fm['navigation_index_sha256']}
                atomic(tmp/'generation/manifest.json',m)
                inventory['generation/manifest.json']={'sha256':sha(tmp/'generation/manifest.json'),'bytes':(tmp/'generation/manifest.json').stat().st_size}
        total=sum(v['bytes'] for v in inventory.values());done=0
        with log.phase('shared-copy-byte-verification',target=str(tmp),bytes=total):
            if any(p.is_symlink() for p in tmp.rglob('*')):raise ValueError('Shared publication symlink rejected')
            actual_files={str(p.relative_to(tmp)) for p in tmp.rglob('*') if p.is_file() and p.name!='publication.json'}
            if actual_files!=set(inventory):raise ValueError('Shared inventory mismatch')
            for relative,value in inventory.items():
                rel=Path(relative)
                if rel.is_absolute() or '..' in rel.parts:raise ValueError('Shared inventory unsafe path')
                p=tmp/rel
                if p.is_symlink() or p.stat().st_size!=value['bytes']:raise ValueError('Shared file size/type changed')
                digest=hashlib.sha256()
                with p.open('rb') as inp:
                    while chunk:=inp.read(8*1024*1024):
                        digest.update(chunk);done+=len(chunk);log.progress(task='nfs-verify',completed=done,total=total,unit='bytes')
                if digest.hexdigest()!=value['sha256']:raise ValueError('Shared file hash changed: '+relative)
        with log.phase('shared-generation-binding-verification'):
            for name,expected in {**local['identity']['pins'],**local['identity']['code_pins']}.items():
                if sha(name)!=expected:raise ValueError('Local input/code changed during shared publication')
            with closing(Store(tmp/'generation')) as store:
                nav=tmp/'generation'/store.manifest['navigation']['path'];TermIndex(nav,store)
                idx=helper.UnitFulltextIndex(tmp/'generation/fulltext-units',json.loads((nav/'manifest.json').read_text()))
                if idx.manifest['index_sha256']!=json.loads((output/'fulltext-units/manifest.json').read_text())['index_sha256']:raise ValueError('Shared unit index drift')
        record={'schema_version':'genos-unit-fulltext-shared-publication-v1','completed':True,'generation_path':str(final/'generation'),
                'continuation_sha256':sha(output/'continuation.json'),'parent_manifest_sha256':local['identity']['pins'][str(baseline/'generation/manifest.json')],
                'files':inventory,'mount':mount_info(shared_root),'activated':False,'serving_verified':False,'code_serving_revision':None}
        if tmp!=final:
            atomic(tmp/'publication.json',record)
            if final.exists():raise ValueError('Shared destination appeared; preserved incomplete copy')
            os.rename(tmp,final)
        log.emit('shared-publication','VERIFIED',path=str(final),generation_path=str(final/'generation'),activated=False)
        return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dev',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--log-dir',type=Path,required=True);p.add_argument('--workers',type=int,default=2)
    p.add_argument('--shared-root',type=Path,required=True)
    p.add_argument('--run-id');p.add_argument('--data-root',type=Path);p.add_argument('--baseline-override',type=Path)
    a=p.parse_args();sys.path.insert(0,str(a.dev.resolve()/'02_BACKEND'))
    from genos_reindex_logging import BuildLog
    log=BuildLog(a.log_dir);status=1
    try:
        helper=selected_helper(Path(__file__).with_name('unit_fulltext_selected.py'))
        log.emit('run','START',dev=str(a.dev.resolve()),baseline=str(a.baseline.resolve()),workers=a.workers)
        with log.phase('locate-completed-baseline'):
            if a.run_id:
                baseline=locate_baseline(a.dev,a.data_root or a.dev/'01_DATA',a.run_id,explicit=a.baseline_override)
                if a.output.parent.resolve()==a.baseline.parent.resolve():a.output=baseline.parent/a.output.name
                a.baseline=baseline
            elif not (a.baseline/'result.json').is_file():raise ValueError('Completed baseline/result.json missing: '+str(a.baseline/'result.json'))
        if not a.shared_root.is_dir():
            if a.shared_root.name=='term-releases' and a.shared_root.parent.is_dir():a.shared_root.mkdir()
            else:raise ValueError('Existing shared NFS root required: '+str(a.shared_root))
        # Check permissions before spending time on fulltext. A missing mount gets no local fallback.
        with tempfile.TemporaryDirectory(prefix='.fulltext-write-check-',dir=a.shared_root):pass
        run(a.baseline,a.output,helper,log,a.workers)
        publish_shared(a.baseline,a.output,a.shared_root,helper,log);status=0
    finally:log.close(status)

if __name__=='__main__':main()
