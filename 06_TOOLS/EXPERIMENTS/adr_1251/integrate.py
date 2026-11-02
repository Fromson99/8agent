"""Integrate only reviewed paths; preserve concurrently edited ontology files."""
from common import *
import shutil,ast
f=read(DES/'freeze.json');C=ROOT/f['code_root'];before=read(DES/'working-before.json');iso=read(DES/'isolation.json');changes={};back=ART/'working-backup';back.mkdir(exist_ok=False)
own=iso['own_product_paths']
for n in own:assert sha(ROOT/n)==before[n], 'Concurrent modification of owned path: '+n
for n in own:
 p=ROOT/n;old=sha(p);dst=back/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dst);shutil.copyfile(C/n,p);ast.parse(p.read_text());changes[n]={'before':old,'after':sha(p)}
# Update only owned product pins; unrelated work and its metadata stay intact.
replacements={}
for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p);s=p.read_text();old=sha(p)
 for n in own:
  if n in v.get('files',{}):v['files'][n]=sha(ROOT/n)
 new=json.dumps(v,ensure_ascii=False,indent=2)+'\n'
 if json.loads(s)!=v:
  dest=back/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(s);p.write_text(new);replacements[old]=sha(p);changes[str(p.relative_to(ROOT))]={'before':old,'after':sha(p)}
p=ROOT/'00_SYSTEM/PIPELINE.json';old=sha(p);s=p.read_text();new=s
for a,b in replacements.items():new=new.replace(a,b)
if new!=s:
 dest=back/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(s);p.write_text(new);changes[str(p.relative_to(ROOT))]={'before':old,'after':sha(p)}
# Durable regression tests use the normal contracts suite import paths.
T=Path(__file__).parent;target=ROOT/'05_TESTS/CONTRACTS'
mapping={'native_scope_builder.py':'scope_review_fixture.py','test_need_continuity_v2.py':'test_need_continuity.py','general_scope_native_fixture.py':'need_continuity_fixture.py','test_scope_review.py':'test_scope_review.py','test_native_scope.py':'test_scope_review_api.py'}
for src,dst in mapping.items():
 p=target/dst;old=sha(p) if p.exists() else None
 if p.exists():q=back/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
 s=(T/src).read_text().replace('from native_scope_builder import','from scope_review_fixture import').replace('from general_scope_native_fixture import','from need_continuity_fixture import').replace('Path(__file__).resolve().parents[3]','Path(__file__).resolve().parents[2]')
 if src=='native_scope_builder.py':s=s.replace('    rows=[]','    if ctx.get("need_continuity",{}).get("version") != "declared-need-continuity-v2": return\n    rows=[]',1)
 p.write_text(s);ast.parse(s);changes[str(p.relative_to(ROOT))]={'before':old,'after':sha(p)}
put(ART/'working-integration.json',{'files':changes,'product_paths':own,'product_candidate_equal':all(sha(ROOT/n)==sha(C/n) for n in own),'other_working_changes_preserved':{n:sha(ROOT/n) for n in iso['concurrent_paths']},'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],'main_promoted':False,'oracle_access':False})
print('Integrated',len(own),'product files;',len(changes),'total including pins and regression fixtures')
