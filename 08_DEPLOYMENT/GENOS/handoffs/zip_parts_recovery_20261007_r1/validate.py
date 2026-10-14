"""Run the actual handoff against synthetic bytes, including 49MB+ originals."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
RUN=OUT/'JOIN_VERIFY_RECOVER_20261007_R1_RUN.txt'
sha=lambda raw: hashlib.sha256(raw).hexdigest()

def setup(base, total=270001, chunk=8192):
    source=base/'data.zip'
    with zipfile.ZipFile(source,'w',compression=zipfile.ZIP_STORED) as z:
        with z.open('mock.txt','w') as stream:
            while total:
                size=min(total,1024*1024);stream.write(b'A'*size);total-=size
    raw=source.read_bytes();parts=base/'data.zip.parts';parts.mkdir()
    rows=[]
    for i,start in enumerate(range(0,len(raw),chunk)):
        name=f'data.zip.part{i:06d}';data=raw[start:start+chunk]
        (parts/name).write_bytes(data);rows.append(sha(data)+'  ./'+name+'\n')
    (parts/'PARTS.sha256').write_text(''.join(rows))
    (parts/'ORIGINAL.sha256').write_text(sha(raw)+'  data.zip\n')
    return parts,raw

def run_case(base, label, mutate=None, expected=0, **setup_args):
    folder=base/label;folder.mkdir()
    parts,raw=setup(folder,**setup_args)
    if mutate:mutate(parts,folder)
    before={str(p.relative_to(folder)):p.read_bytes() for p in parts.iterdir() if p.is_file()}
    result=subprocess.run(['bash',str(RUN),str(parts)],capture_output=True,text=True,timeout=60)
    assert result.returncode==expected,(label,result.stdout[-2500:],result.stderr[-2500:])
    for name,data in before.items():assert (folder/name).read_bytes()==data,label
    output=folder/'data_verified.zip'
    if expected==0:
        assert output.read_bytes()==raw,label
        assert (folder/'data_verified.zip.sha256').read_text()==sha(raw)+'  data_verified.zip\n'
        spec=importlib.util.spec_from_file_location('_recovery_transfer_driver',ROOT/'06_TOOLS/COMMANDS/genos_transfer_data_list.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        assert mod.join_input(output,Path('/unused_joiner'))==output
    elif label!='output_conflict':assert not output.exists(),label
    return parts,folder,raw

def main():
    checks=[]
    with tempfile.TemporaryDirectory(prefix='join-recovery-contract-') as temporary:
        base=Path(temporary)
        run_case(base,'unchanged');checks.append('unchanged original joined and direct R3 ZIP input accepted')
        def append(parts,folder):
            path=parts/'data.zip.part000030';path.write_bytes(path.read_bytes()+b'\n')
        parts,folder,raw=run_case(base,'appended_one_byte',append)
        checks.append('part000030 appended byte recovered only through part+whole SHA; original part unchanged')
        again=subprocess.run(['bash',str(RUN),str(parts)],capture_output=True,text=True,timeout=60)
        assert again.returncode==0 and (folder/'data_verified.zip').read_bytes()==raw
        checks.append('same verified output reused without overwrite')
        def middle(parts,folder):
            path=parts/'data.zip.part000030';raw=path.read_bytes();path.write_bytes(raw[:100]+b'Z'+raw[100:])
        run_case(base,'inserted_middle',middle,expected=1);checks.append('inserted middle byte rejected')
        def altered(parts,folder):
            path=parts/'data.zip.part000030';raw=path.read_bytes();path.write_bytes(b'Z'+raw[1:])
        run_case(base,'altered_same_size',altered,expected=1);checks.append('same size content corruption rejected')
        def two(parts,folder):
            append(parts,folder)
            path=parts/'data.zip.part000029';path.write_bytes(path.read_bytes()+b'\n')
        run_case(base,'two_corrupt',two,expected=1);checks.append('multiple corrupt parts rejected')
        def wrong_original(parts,folder):
            append(parts,folder);(parts/'ORIGINAL.sha256').write_text('0'*64+'  data.zip\n')
        run_case(base,'wrong_original',wrong_original,expected=1);checks.append('part recovery cannot bypass original whole ZIP SHA')
        def missing(parts,folder):(parts/'data.zip.part000030').rename(folder/'preserved_part30')
        run_case(base,'missing',missing,expected=1);checks.append('missing inventory part rejected')
        def extra(parts,folder):(parts/'data.zip.part999999').write_bytes(b'extra')
        run_case(base,'extra',extra,expected=1);checks.append('extra part rejected')
        def link(parts,folder):
            path=parts/'data.zip.part000030';path.rename(folder/'real_part30');path.symlink_to(folder/'real_part30')
        run_case(base,'symlink',link,expected=1);checks.append('part symlink rejected')
        def conflict(parts,folder):(folder/'data_verified.zip').write_bytes(b'preserve conflicting output')
        _,folder,_=run_case(base,'output_conflict',conflict,expected=1)
        assert (folder/'data_verified.zip').read_bytes()==b'preserve conflicting output'
        checks.append('conflicting output preserved')
        run_case(base,'over49mb_valid',total=49000001,chunk=50000000)
        checks.append('valid >49,000,000 byte part allowed when original whole SHA matches')
    result={'passed':len(checks),'checks':checks,'runner_sha256':sha(RUN.read_bytes()),
            'synthetic_only':True,'operating_data_changed':False,'field_execution':False}
    (OUT/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
