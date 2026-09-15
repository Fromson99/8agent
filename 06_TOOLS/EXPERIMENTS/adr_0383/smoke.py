from runner import install,R
install()
import json,base64
from PIL import Image,ImageDraw
from lawrag.research.experiment_client import GeminiExperimentClient
A=R/'04_EXPERIMENTS/ADR/ADR-0383-gemini-experiment-default/artifacts'
client=GeminiExperimentClient(R,A/'smoke',max_calls=2,max_output_tokens=256)
text=client.generate('Return only the requested JSON.','Return ready=true.',{'type':'object','properties':{'ready':{'type':'boolean'}},'required':['ready'],'additionalProperties':False},phase='text')
im=Image.new('RGB',(320,120),'white');draw=ImageDraw.Draw(im)
for x in [30,130,230]:draw.rectangle((x,35,x+40,75),fill='black')
p=A/'smoke-three-squares.png';im.save(p)
vision=client.generate('Count visible black squares and return JSON.','How many black squares are shown?',{'type':'object','properties':{'count':{'type':'integer'}},'required':['count'],'additionalProperties':False},images=['data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()],phase='vision')
out={'text':text,'vision':vision,'passed':text=={'ready':True} and vision=={'count':3},'usage':client.usage};(A/'smoke-result.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
