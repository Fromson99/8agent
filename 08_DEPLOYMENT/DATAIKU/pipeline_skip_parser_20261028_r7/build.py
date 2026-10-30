import ast,importlib.util,json,re,zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'pipeline_partial_20261028_r6'
SERVICE='GENOS_DATAIKU_COMPUTE_20261028_R7'
PACKAGE='DATAIKU_COMPUTE_RECIPES_20261028_R7.zip'
OLD_CODE='31a3d3dd1b2be7b4618e40153bd08e4df8f12c768e57cb1458e856d985ddf548'
spec=importlib.util.spec_from_file_location('r6build',BASE/'build.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
sha,edit,writezip=old.sha,old.edit,old.writezip


def main():
    with zipfile.ZipFile(BASE/'GENOS_DATAIKU_COMPUTE_20261028_R6.zip') as z:original={n.split('/',1)[1]:z.read(n) for n in z.namelist()}
    assert sha(original['CODE_PINS.json'])==OLD_CODE
    pins=json.loads(original['CODE_PINS.json']);assert all(sha(original[n])==h for n,h in pins['files'].items())
    payload=dict(original)
    s=original['worker.py'].decode().replace("'--structure-vlm', 'on', '--pdf-conversion', 'on'", "'--structure-vlm', 'off', '--pdf-conversion', 'off'")
    s=s.replace("env['STRUCTURE_RECIPE_VLM'] = 'on'", "env['STRUCTURE_RECIPE_VLM'] = 'off'")
    s=s.replace("'pipeline': 'native-existing-genos-review'", "'pipeline': 'native-only-preprocessor-bypassed'")
    payload['worker.py']=s.encode()
    # Keep purpose/auth/lifecycle contracts, but the old parser probe is disabled.
    s=original['service.py'].decode()
    s=edit(s,"probe_runtime.inspect(ROOT) if op=='PROBE_HEALTH' else parser_config.inspect(ROOT)", "{'ready':False,'errors':['DOCUMENT_PROBE_DISABLED_BY_USER']} if op=='PROBE_HEALTH' else parser_config.inspect(ROOT)")
    s=edit(s,"if purpose not in {'pipeline',sample_worker.PURPOSE}:raise ValueError('COMPUTE_PURPOSE')", "if purpose!='pipeline':raise ValueError('DOCUMENT_PROBE_DISABLED_BY_USER')")
    payload['service.py']=s.encode()
    name='02_BACKEND/lawrag/pipeline/genos_stages.py';s=original[name].decode()
    s=edit(s,"mode not in {'preprocessor', 'local'}", "mode not in {'preprocessor', 'local', 'skip'}")
    s=s.replace('GENOS_PDF_PARSER must be preprocessor or local','GENOS_PDF_PARSER must be preprocessor, local or skip')
    s=edit(s,"    if pdf_parser:\n        report['pdf_parser']", "    if mode=='skip':report.update(pdf_policy='SKIP_BEFORE_PARSING',preprocessor_model_calls=0)\n    if pdf_parser:\n        report['pdf_parser']")
    s=edit(s,"            if stage in {'all', 'structure'}:\n                folder, work", "            if stage in {'all','structure'} and mode=='skip' and Path(row['path']).suffix.lower()=='.pdf':\n                raise ValueError('PDF_PARSER_BYPASSED_BY_USER: 전처리기 사용 안 함; PDF 파싱을 건너뜁니다')\n            if stage in {'all', 'structure'}:\n                folder, work")
    payload[name]=s.encode()
    # Prevent any indirect route from falling back to local PDF parsing.
    name='02_BACKEND/lawrag/core/parse_adapter.py';s=original[name].decode()
    s=edit(s,'def pdf_parser_identity(path):\n', "def pdf_parser_identity(path):\n    if __import__('os').environ.get('GENOS_PDF_PARSER')=='skip':\n        raise ValueError('PDF_PARSER_BYPASSED_BY_USER: PDF parser disabled')\n")
    s=edit(s,'def parse_pdf(path: str | Path, *, recognize_grids=None) -> ParseResult:\n', "def parse_pdf(path: str | Path, *, recognize_grids=None) -> ParseResult:\n    if __import__('os').environ.get('GENOS_PDF_PARSER')=='skip':\n        raise ValueError('PDF_PARSER_BYPASSED_BY_USER: PDF parser disabled')\n")
    payload[name]=s.encode()
    name='02_BACKEND/lawrag/pipeline/genos_corpus.py';s=original[name].decode()
    s=edit(s,"ValueError('구형 DOC의 주 입력 PDF 없음: 같은 폴더에 같은 이름의 PDF를 반입하세요')", "ValueError('PDF_CONVERSION_BYPASSED_BY_USER: 전처리기 사용 안 함; 구형 DOC 변환을 건너뜁니다' if __import__('os').environ.get('GENOS_PDF_PARSER')=='skip' else '구형 DOC의 주 입력 PDF 없음: 같은 폴더에 같은 이름의 PDF를 반입하세요')")
    payload[name]=s.encode()
    name='02_BACKEND/lawrag/pipeline/raw_preprocess.py';s=original[name].decode()
    s=edit(s,"            if target.exists():\n                pdf_check(target)\n                item['status'] = 'EXISTING'\n                continue\n            if not pdf:\n                item['status'] = 'DISABLED'\n                continue", "            if not pdf:\n                item['status'] = 'DISABLED'\n                continue\n            if target.exists():\n                pdf_check(target)\n                item['status'] = 'EXISTING'\n                continue")
    payload[name]=s.encode()
    name='02_BACKEND/lawrag/pipeline/team_raw.py';s=original[name].decode()
    s=edit(s,"'error': 'DOC requires companion PDF'", "'error': ('PDF_CONVERSION_BYPASSED_BY_USER: 전처리기 사용 안 함; 구형 DOC 변환을 건너뜁니다' if __import__('os').environ.get('GENOS_PDF_PARSER')=='skip' else 'DOC requires companion PDF')")
    payload[name]=s.encode()
    name='02_BACKEND/lawrag/pipeline/genos_build.py';s=original[name].decode()
    s=edit(s,"    if suffix == '.pdf' and os.environ.get('GENOS_PDF_PARSER', 'preprocessor').strip() == 'preprocessor':", "    if suffix=='.pdf' and os.environ.get('GENOS_PDF_PARSER')=='skip':\n        return '사용자 요청으로 PDF 파싱 건너뜀: 전처리기 미사용'\n    if suffix == '.pdf' and os.environ.get('GENOS_PDF_PARSER', 'preprocessor').strip() == 'preprocessor':")
    payload[name]=s.encode()
    for n in ('partial_pipeline.py','pipeline_coverage.py','parser_config.py'):payload[n]=(HERE/n).read_bytes()
    payload['CODE_PINS.json']=(json.dumps({**pins,'files':{n:sha(b) for n,b in payload.items() if n!='CODE_PINS.json'}},sort_keys=True,indent=2)+'\n').encode()
    code=sha(payload['CODE_PINS.json']);writezip(HERE/(SERVICE+'.zip'),{SERVICE+'/'+n:b for n,b in payload.items()})
    for n in ('worker.py','service.py'):(HERE/n).write_bytes(payload[n])
    with zipfile.ZipFile(BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R6.zip') as z:client={n:z.read(n) for n in z.namelist()}
    client['pipeline_coverage.py']=payload['pipeline_coverage.py'];client['COMPUTE_CODE_SHA256.txt']=(code+'\n').encode()
    s=client['checkpoint_upgrade.py'].decode().replace('PREVIOUS_CODES = {',"PREVIOUS_CODES = {'"+OLD_CODE+"', ").replace("if previous_code in {", "if previous_code in {'"+OLD_CODE+"', ")
    client['checkpoint_upgrade.py']=s.replace('VERIFIED_SUCCESSFUL_DOCUMENTS_ONLY','PREPROCESSOR_BYPASSED_BY_USER').encode()
    client['updater.py']=client['updater.py'].replace(b'partial-pipeline-r6-before.json',b'skip-parser-r7-before.json')
    ref=json.loads(client['REFERENCE.json']);ref['prior_compute_bootstraps'].append((BASE/'bootstrap.txt').read_text());client['REFERENCE.json']=(json.dumps(ref)+'\n').encode()
    client['PACKAGE_FILES.json']=(json.dumps({n:sha(b) for n,b in client.items() if n!='PACKAGE_FILES.json'},sort_keys=True,indent=2)+'\n').encode();writezip(HERE/PACKAGE,client)
    oldboot=(BASE/'bootstrap.txt').read_text();boot=oldboot.replace('DATAIKU_COMPUTE_RECIPES_20261028_R6.zip',PACKAGE).replace(sha((BASE/'DATAIKU_COMPUTE_RECIPES_20261028_R6.zip').read_bytes()),sha((HERE/PACKAGE).read_bytes()))
    boot=re.sub(r'PACKAGE_BYTES = \d+','PACKAGE_BYTES = '+str((HERE/PACKAGE).stat().st_size),boot);(HERE/'bootstrap.txt').write_text(boot)
    for kind in ('INSTALL','CONTROL'):
        s=(BASE/f'DATAIKU_R6_{kind}.txt').read_text().replace(oldboot,boot).replace(repr(oldboot),repr(boot)).replace('pipeline_partial_r6_updater','pipeline_skip_r7_updater')
        s=s.replace('PARTIAL_R6_FLOW_READY: GENOS R6 리비전 적용 후 00 → 기존 02 → 기존 03 순서로 실행','SKIP_R7_FLOW_READY: 전처리기 설정 불필요. GENOS R7 적용 후 00 → 기존 02 → 기존 03')
        (HERE/f'DATAIKU_R7_{kind}.txt').write_text(s);ast.parse(s)
    for n,b in list(payload.items())+list(client.items()):
        if n.endswith('.py'):compile(b,n,'exec')
    (HERE/'BUILD.json').write_text(json.dumps({'baseline_code_sha256':OLD_CODE,'code_sha256':code,'service_files':len(payload),'unchanged_baseline_files':sum(payload.get(n)==b for n,b in original.items()),'changed_files':[n for n,b in payload.items() if original.get(n)!=b],'files':{n:{'sha256':sha((HERE/n).read_bytes()),'bytes':(HERE/n).stat().st_size} for n in (SERVICE+'.zip',PACKAGE)}},indent=2)+'\n')
    print('BUILT',code,len(payload))

if __name__=='__main__':main()
