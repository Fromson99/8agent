"""Build the installer-only correction from the immutable, shipped R1 payload."""
import base64,gzip,hashlib,json,subprocess,zipfile,zlib
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
PARENT=OUT.with_name('ad_request_logs_20261013_r1')
NAME='GENOS_AD_REQUEST_LOGS_20261013_R2'
sha=lambda b:hashlib.sha256(b).hexdigest()
encoded=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()


def build():
    assert not (OUT/(NAME+'.zip')).exists(),'Preserve sealed handoff'
    archive=PARENT/'GENOS_AD_REQUEST_LOGS_20261013_R1.zip'
    expected=json.loads((PARENT/'EMAIL_SENT.json').read_text())['attachments'][0]['sha256']
    assert sha(archive.read_bytes())==expected
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        for row in manifest['files']:assert sha(z.read(row['path']))==row['sha256']
        prior_spec=z.read('PATCH_SPEC.json.gz')
        spec=json.loads(gzip.decompress(prior_spec))
        spec['revision']=NAME
        (OUT/'PATCH_SPEC.json.gz').write_bytes(gzip.compress(encoded(spec),mtime=0))
        binding=json.loads(z.read('SOURCE_BINDING.json'))
        binding.update(prior_delivery=str(PARENT.relative_to(ROOT)),runtime_implementation_changed_from_r1=False,
            installer_fix='Exact approved investigation budget overlay is normalized for comparison and restored in output.',
            verified_prior_zip_sha256=expected)
        (OUT/'SOURCE_BINDING.json').write_bytes(encoded(binding))
        for n in ('WORKING_INTEGRATION.json','BASELINE_NOTES.json'):
            (OUT/n).write_bytes(z.read(n))
        for n in z.namelist():
            if n.startswith('payload/'):
                path=OUT/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(n))
    bundle=encoded({'code':base64.b64encode((OUT/'apply_patch.py').read_bytes()).decode(),'spec':spec})
    packed=base64.b64encode(zlib.compress(bundle,9)).decode()
    py=('import base64,hashlib,json,os,sys,types,zlib\n'+f'raw=zlib.decompress(base64.b64decode({packed!r}))\nassert hashlib.sha256(raw).hexdigest()=={sha(bundle)!r}\n'+
        "bundle=json.loads(raw);module=types.ModuleType('ad_request_installer')\nexec(compile(base64.b64decode(bundle['code']),'apply_patch.py','exec'),module.__dict__)\nraise SystemExit(module.main(bundle['spec'],['--root',os.environ['GENOS_PATCH_DEV'],*sys.argv[1:]]))\n")
    old=(PARENT/'GENOS_AD_REQUEST_LOGS_20261013_R1_RUN.txt').read_text()
    header=old[:old.index('python3 - "$@"')].replace('ad-request-logs-r1','ad-request-logs-r2')
    (OUT/(NAME+'_RUN.txt')).write_text(header+'python3 - "$@" <<\'AD_REQUEST_LOGS_PY\'\n'+py+'AD_REQUEST_LOGS_PY\n')
    subprocess.run(['bash','-n',str(OUT/(NAME+'_RUN.txt'))],check=True)
    (OUT/'R1_SOURCE_RECORD.json').write_bytes(encoded({'prior_zip_sha256':expected,
        'prior_spec_sha256':sha(prior_spec),'new_spec_sha256':sha((OUT/'PATCH_SPEC.json.gz').read_bytes()),
        'implementation_blobs_identical':True,'known_base_inventories':len(spec['signatures']),
        'expanded_budget_states':len(spec['signatures'])*2}))
    print(json.dumps({'known_base_inventories':len(spec['signatures']),'run_bytes':(OUT/(NAME+'_RUN.txt')).stat().st_size}))


if __name__=='__main__':build()
