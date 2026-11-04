"""Build the exact runnable handoff, with two embedded data pieces (no nested ZIP)."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PACKAGE = HERE/'package'
NAME = 'DATAIKU_GOLD_DEV_TEST_20261104_R1.zip'


def main():
    original = REPO/'09_ARTIFACTS/AUDITS/20261104-gold-r5-code-integration/fixture/upload/synthetic-gold.zip'
    raw = original.read_bytes()
    sample = PACKAGE/'sample'; sample.mkdir(exist_ok=True)
    split = (len(raw)+1)//2
    files = {}
    lines = []
    for i, block in enumerate((raw[:split], raw[split:])):
        name = 'gold-dev-sample.zip.part%06d'%i
        (sample/name).write_bytes(block)
        lines.append(hashlib.sha256(block).hexdigest()+'  '+name)
    (sample/'PARTS.sha256').write_text('\n'.join(lines)+'\n')
    (sample/'ORIGINAL.sha256').write_text(hashlib.sha256(raw).hexdigest()+'  gold-dev-sample.zip\n')
    for p in sorted(sample.iterdir()):
        if p.name!='manifest.json': files[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (sample/'manifest.json').write_text(json.dumps({'source':'existing synthetic contract fixture; no production corpus',
        'documents':2,'source_units':3,'source_blocks':3,'query_rows':112,'vector_units':3,
        'archive_bytes':len(raw),'archive_sha256':hashlib.sha256(raw).hexdigest(),'parts':2,'files':files},indent=2)+'\n')
    hashes = {p.relative_to(PACKAGE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(PACKAGE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
              and p.suffix!='.pyc' and p.name!='FLOW_MANIFEST.json'}
    assert not any(Path(n).suffix.lower() in {'.js','.jsx','.mjs','.cjs','.zip'} for n in hashes)
    (PACKAGE/'FLOW_MANIFEST.json').write_text(json.dumps({'version':'gold-dev-test-20261104-r1','files':hashes},indent=2)+'\n')
    with zipfile.ZipFile(HERE/NAME,'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*hashes,'FLOW_MANIFEST.json']):
            info = zipfile.ZipInfo(name, date_time=(2026,11,4,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16
            z.writestr(info,(PACKAGE/name).read_bytes())
    checksum = hashlib.sha256((HERE/NAME).read_bytes()).hexdigest()
    bootstrap = (HERE/'bootstrap_template.py').read_text().replace('DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip',NAME).replace('@@ZIP_SHA@@',checksum)
    # Refuse mixed packages in a reused notebook kernel; do not partially reset dependencies.
    bootstrap += '''
for _name in ("zip_config","zip_runtime","zip_pipeline","dev_guard","dev_install","dev_pipeline",
              "dev_watch","run_full","gold_io","fast_loader","vector_stage","jdbc_transport"):
    _loaded = sys.modules.get(_name)
    if _loaded is not None:
        _origin = Path(getattr(_loaded,"__file__","")).resolve()
        if FLOW_PACKAGE.resolve() not in _origin.parents:
            raise RuntimeError("RESTART_KERNEL_PACKAGE_CONFLICT:"+_name)
'''
    code = (HERE/'params_template.py').read_text()+'\n'+bootstrap
    code += '\nfrom dev_install import install\nFLOW_CONFIG = install(PARAMS, '+repr(bootstrap)+')\n'
    code += '\n# 별도 셀에서 관찰: from dev_watch import watch; watch(FLOW_CONFIG)\n'
    compile(code,'delivered-notebook','exec')
    (HERE/'DATAIKU_GOLD_DEV_TEST_RUN_R1.txt').write_text(code)
    (HERE/'DATAIKU_GOLD_DEV_TEST_WATCH_R1.txt').write_text(
        '# 설치한 같은 노트북의 새 셀에 붙여 넣으세요. Scenarios의 Run 후 실행합니다.\n'
        '# 관찰 중단은 작업을 중단하지 않습니다. 10분 뒤 필요하면 이 셀만 재실행하세요.\n'
        'from dev_watch import watch\nwatch(FLOW_CONFIG, seconds=600, interval=3)\n')
    print(json.dumps({'zip':NAME,'bytes':(HERE/NAME).stat().st_size,'sha256':checksum,
                      'members':len(hashes)+1,'sample_parts':2,'sample_bytes':len(raw)}))


if __name__=='__main__': main()
