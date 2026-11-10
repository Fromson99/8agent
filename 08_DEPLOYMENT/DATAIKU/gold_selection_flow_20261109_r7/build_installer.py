import hashlib
from pathlib import Path
here = Path(__file__).resolve().parent
code = (here/'recipe_gold_selection_fix_r7.py').read_text()
text = (here/'installer_template.py').read_text()
text = text.replace("'__RECIPE_SHA256__'", repr(hashlib.sha256(code.encode()).hexdigest()))
text = text.replace('__RECIPE_CODE__', repr(code))
(here/'DATAIKU_CREATE_GOLD_FIX_FLOW_R7.txt').write_text(text)
print(hashlib.sha256(text.encode()).hexdigest())
