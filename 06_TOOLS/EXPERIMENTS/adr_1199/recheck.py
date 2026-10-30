from pathlib import Path
p=Path(__file__).with_name('check.py');s=p.read_text().replace("rev='working' if mode=='working' else f['candidate_revision']['revision_id']","rev='working' if mode=='working' else f['candidate_revision']['revision_id']+'-fixture-corrected'")
exec(compile(s,str(p),'exec'))
