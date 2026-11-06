"""Re-freeze runner hashes before any model call; earlier freeze kept as superseded."""
from common import *
tag=sys.argv[1];reason=sys.argv[2]
assert not (ART/'public-live').exists(),'refreeze is allowed only before any live cell'
f=DES/'freeze-live.json';v=read(f);assert v['model_calls_before_freeze']==0
(DES/('freeze-live-'+tag+'-superseded.json')).write_bytes(f.read_bytes())
v['files']={n:sha(ROOT/n) for n in sorted(set(v['files'])|{str(p.relative_to(ROOT)) for p in Path(__file__).parent.glob('*.py')})}
v.setdefault('supersessions',[]).append({'tag':tag,'reason':reason})
f.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
issues=read(ART/'preparation-issues.json');issues.append({'phase':'preflight before any model call','error':reason,'correction':'runner fixed and re-frozen ('+tag+'); criteria/cases/arms unchanged; model0'});put(ART/'preparation-issues.json',issues)
print('refrozen',tag,len(v['files']))
