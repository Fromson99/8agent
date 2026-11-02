from common import *
excluded={'test-runtime','working-before-integration','working-before-integration-r2','new-files-during-refreeze',
 'failed-preview-r1','failed-freeze-rev010','nfs-main-entry'}
paths=[p for p in ART.rglob('*') if p.is_file() and not (set(p.relative_to(ART).parts)&excluded) and p!=ART/'manifest.json']
paths+=list(Path(__file__).parent.glob('*.py'))
value={'schema_version':'adr-artifacts-v1','adr_id':'ADR-1244','created_at':read(ADR/'실험/manifest.json')['reservation']['created_at'],
 'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
 'description':'Oracle 전체 기록 저장 기술검사·실패 보존·정확한 메인 결속',
 'contains_raw_prompts_and_outputs':False} for p in sorted(paths)]}
target=ART/'manifest.json'
if target.exists():
 old=target.read_text();history=ART/('manifest-before-'+sha(target)[:12]+'.json')
 if not history.exists():history.write_text(old)
 target.unlink()
put(target,value);print('Bound',len(paths),'artifacts and runner files')
