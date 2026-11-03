from common import *
import shutil,os,zipfile
c=read(ART/'loader-final-candidate.json');assert read(ART/'loader-rowid-final/result.json')['failed']==0
P=ROOT/c['package'];base='08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_seek_20261103_r7/package';before=c['working_before']
assert all(sha(ROOT/n)==h for n,h in before.items())
backup=ART/'loader-before';backup.mkdir(exist_ok=False)
rows=[]
for n,h in before.items():
 source=P/Path(n).relative_to(base);expected=sha(source)
 if h!=expected:
  dst=backup/Path(n).name;shutil.copy2(ROOT/n,dst)
  tmp=(ROOT/n).with_name('.'+Path(n).name+'.adr1308');shutil.copy2(source,tmp);os.replace(tmp,ROOT/n);rows.append(n)
assert len(rows)==2
files={n:sha(P/Path(n).relative_to(base)) for n in before};assert all(sha(ROOT/n)==h for n,h in files.items())
put(ART/'loader-integration.json',{'files':files,'changed':rows,'candidate':c['candidate'],'main_unchanged':True,'checks':bind(ART/'loader-rowid-final/result.json')})
folder=(ROOT/base).parent;archive=folder.parent/'gold_fresh_1_jdbc_seek_20261103_r7_verified.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in sorted(folder.rglob('*')):
  if p.is_file() and '__pycache__' not in str(p):z.write(p,p.relative_to(folder.parent))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None;count=len(z.namelist())
put(ART/'r7-verified-package.json',{'path':str(archive.relative_to(ROOT)),'sha256':sha(archive),'bytes':archive.stat().st_size,'files':count,'initial_package':bind(ART/'r7-package.json'),'negative_and_zero_rowids_preserved':True,'field_executed':False})
p=Path(__file__).parent/'finalize.py';s=p.read_text()
s=s.replace("assert all(sha(ROOT/n)==sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items())", "loader=read(ART/'loader-integration.json')\nassert all(sha(ROOT/n)==sha(ROOT/f['code_root']/n)==h for n,h in f['files'].items() if n not in loader['files'])\nassert all(sha(ROOT/n)==h for n,h in loader['files'].items())")
s=s.replace("'candidate':f['candidate_revision'],'candidate_files':", "'candidate':f['candidate_revision'],'loader_candidate':loader['candidate'],'loader_contracts_passed':read(ART/'loader-rowid-final/result.json')['passed'],'candidate_files':")
s=s.replace("ART/'r7-package.json'","ART/'r7-verified-package.json'")
s=s.replace('최종 scope-fixed/rev-001 후보664파일·작업 코드 동일', '최종 scope-fixed/rev-001 런타임591파일+후속 로더73파일·작업 코드 동일')
s=s.replace('R7 ZIP74파일/283234bytes', "R7 검증 ZIP74파일/{read(ART/'r7-verified-package.json')['bytes']}bytes")
s=s.replace('최종 후보664/서빙517 정확 결속.', '최종 런타임591+후속로더73/서빙517 정확 결속.')
s=s.replace('후보scope-fixed rev001/작업664일치', '런타임591+후속로더73/작업664일치')
s=s.replace('후보를 작업에 반영한 뒤', '로더 후속검사에서 words content 첫 조회와 rowid=0 재개가 음수/0행을 건너뛸 수 있음을 수정했고, 음수·0을 포함한 모든 행 경계 재개10검사가 통과했다. 초기 ZIP은 보존하고 _verified.zip만 최종본으로 표시했다.\n후보를 작업에 반영한 뒤')
p.write_text(s)
print('Final R7 package integrated; 2 loader files, MAIN unchanged,',count,'archive files')
