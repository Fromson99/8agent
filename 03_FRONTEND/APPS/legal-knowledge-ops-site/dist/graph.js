'use strict';
/* Small, local-only 3D projection. No WebGL, CDN, model, or remote data dependency. */
class KnowledgeGraph {
 constructor(canvas,data,groups,options={}){
  this.canvas=canvas;this.ctx=canvas.getContext('2d');this.data=data;this.groups=groups;this.options=options;
  this.mode=options.mode||'3d';this.off=new Set(options.off);this.selected=options.selected;
  this.query=options.search||'';this.yaw=.12;this.pitch=.18;this.scale=1;this.drag=null;this.points=[];
  this.abort=new AbortController();const opts={signal:this.abort.signal};
  canvas.addEventListener('pointerdown',e=>{this.drag={x:e.clientX,y:e.clientY,originX:e.clientX,originY:e.clientY,moved:false};canvas.setPointerCapture(e.pointerId);},opts);
  canvas.addEventListener('pointermove',e=>{if(this.drag){const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;if(Math.hypot(e.clientX-this.drag.originX,e.clientY-this.drag.originY)>5)this.drag.moved=true;if(this.mode==='3d'){this.yaw+=dx*.006;this.pitch=Math.max(-1,Math.min(1,this.pitch+dy*.006));this.draw();}this.drag.x=e.clientX;this.drag.y=e.clientY;}else{canvas.style.cursor=this.hit(e)?'pointer':'grab';}},opts);
  canvas.addEventListener('pointerup',e=>{if(this.drag&&!this.drag.moved){const p=this.hit(e);if(p)this.options.onSelect?.(p.node.id);}this.drag=null;},opts);
  canvas.addEventListener('pointercancel',()=>{this.drag=null;},opts);
  canvas.addEventListener('wheel',e=>{e.preventDefault();this.zoom(e.deltaY>0?.92:1.08);},{...opts,passive:false});
  canvas.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){this.zoom(1.15);e.preventDefault();}if(e.key==='-'){this.zoom(.85);e.preventDefault();}if(e.key==='0'){this.fit();e.preventDefault();}if(e.key.startsWith('Arrow')){this.yaw+=e.key==='ArrowLeft'?-.12:e.key==='ArrowRight'?.12:0;this.pitch+=e.key==='ArrowUp'?-.08:e.key==='ArrowDown'?.08:0;this.draw();e.preventDefault();}},opts);
  this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(canvas);this.resize();
 }
 resize(){const rect=this.canvas.getBoundingClientRect();this.w=rect.width;this.h=rect.height;const dpr=Math.min(window.devicePixelRatio||1,2);this.canvas.width=Math.round(this.w*dpr);this.canvas.height=Math.round(this.h*dpr);this.ctx.setTransform(dpr,0,0,dpr,0,0);this.draw();}
 project(node){let [x,y,z]=node.pos;if(this.mode==='3d'){const nx=x*Math.cos(this.yaw)+z*Math.sin(this.yaw),nz=-x*Math.sin(this.yaw)+z*Math.cos(this.yaw);x=nx;z=nz;const ny=y*Math.cos(this.pitch)-z*Math.sin(this.pitch);z=y*Math.sin(this.pitch)+z*Math.cos(this.pitch);y=ny;}else z=0;const f=650/(650+z);const fit=Math.min((this.w-80)/540,(this.h-190)/390);return {node,x:this.w/2+(x+15)*fit*f*this.scale,y:this.h/2-10+y*fit*f*this.scale,z,r:(node.id==='concept'?13:node.group==='rule'||node.group==='exception'?8:6)*Math.max(.8,fit)*f*Math.sqrt(this.scale)};}
 hit(event){const r=this.canvas.getBoundingClientRect(),x=event.clientX-r.left,y=event.clientY-r.top;return [...this.points].reverse().find(p=>Math.hypot(p.x-x,p.y-y)<p.r+12);}
 draw(){
  if(!this.ctx||!this.w)return;
  const ctx=this.ctx;ctx.clearRect(0,0,this.w,this.h);
  // A subdued spatial grid keeps orientation readable while rotating.
  ctx.fillStyle='#1e3547';for(let x=20;x<this.w;x+=30)for(let y=65;y<this.h-110;y+=30){ctx.beginPath();ctx.arc(x,y,.7,0,Math.PI*2);ctx.fill();}
  this.points=this.data.nodes.filter(n=>!this.off.has(n.group)).map(n=>this.project(n)).sort((a,b)=>b.z-a.z);
  const byId=Object.fromEntries(this.points.map(p=>[p.node.id,p]));
  const links=this.data.links.filter(l=>byId[l[0]]&&byId[l[1]]);
  const neighbors=new Set(this.data.links.filter(l=>l[0]===this.selected||l[1]===this.selected).flatMap(l=>[l[0],l[1]]));
  for(const [a,b,label] of links){const p=byId[a],q=byId[b],active=a===this.selected||b===this.selected,color=this.groups[q.node.group].color;const dx=q.x-p.x,dy=q.y-p.y,dist=Math.hypot(dx,dy);if(dist<1)continue;const ux=dx/dist,uy=dy/dist,tx=q.x-ux*(q.r+5),ty=q.y-uy*(q.r+5);
   ctx.globalAlpha=active?.6:.22;ctx.strokeStyle=active?color:'#7e9eaf';ctx.lineWidth=active?1.3:.8;ctx.beginPath();ctx.moveTo(p.x+ux*p.r,p.y+uy*p.r);ctx.lineTo(tx,ty);ctx.stroke();ctx.beginPath();ctx.moveTo(tx,ty);ctx.lineTo(tx-ux*6+uy*3,ty-uy*6-ux*3);ctx.lineTo(tx-ux*6-uy*3,ty-uy*6+ux*3);ctx.closePath();ctx.fillStyle=color;ctx.fill();
   if(active&&this.w>450){ctx.globalAlpha=.75;ctx.font='9px "Malgun Gothic",sans-serif';ctx.textAlign='center';ctx.fillStyle='#91aebb';const mx=(p.x+q.x)/2,my=(p.y+q.y)/2;ctx.fillText(label,mx,my-6);}
  }
  for(const p of this.points){const n=p.node,g=this.groups[n.group],selected=n.id===this.selected,matches=!this.query||n.label.toLowerCase().includes(this.query.toLowerCase()),near=neighbors.has(n.id);
   ctx.globalAlpha=matches?(selected||near?1:.75):.2;
   if(selected){const gradient=ctx.createRadialGradient(p.x,p.y,2,p.x,p.y,48);gradient.addColorStop(0,g.color+'28');gradient.addColorStop(1,g.color+'00');ctx.fillStyle=gradient;ctx.beginPath();ctx.arc(p.x,p.y,48,0,Math.PI*2);ctx.fill();}
   if(selected||n.group==='rule'||n.group==='exception'){ctx.beginPath();ctx.arc(p.x,p.y,p.r+5,0,Math.PI*2);ctx.strokeStyle=g.color;ctx.lineWidth=selected?1.4:.6;ctx.stroke();}
   const grad=ctx.createRadialGradient(p.x-p.r*.4,p.y-p.r*.4,1,p.x,p.y,p.r);grad.addColorStop(0,g.color);grad.addColorStop(1,g.color+'66');ctx.fillStyle=grad;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill();
   ctx.font=`${selected?'600 ':''}${this.w<450?10:11}px "Malgun Gothic","Apple SD Gothic Neo",sans-serif`;ctx.textAlign='center';const label=n.label.length>17?n.label.slice(0,16)+'…':n.label,width=ctx.measureText(label).width;ctx.fillStyle='#111e2bdd';ctx.fillRect(p.x-width/2-5,p.y+p.r+8,width+10,17);ctx.fillStyle=selected?'#ecfcff':g.color;ctx.fillText(label,p.x,p.y+p.r+20);
  }
  ctx.globalAlpha=1;this.options.onCount?.(this.points.length,links.length);
  if(!this.points.length){ctx.textAlign='center';ctx.fillStyle='#93acba';ctx.font='12px sans-serif';ctx.fillText('유형 필터를 켜면 연결을 볼 수 있습니다.',this.w/2,this.h/2);}
 }
 select(id){this.selected=id;this.draw();}
 setFilter(off){this.off=new Set(off);this.draw();}
 setMode(mode){this.mode=mode;this.draw();}
 search(query){this.query=query;this.draw();}
 zoom(factor){this.scale=Math.min(2.4,Math.max(.5,this.scale*factor));this.draw();}
 fit(){this.scale=1;this.yaw=.12;this.pitch=.18;this.draw();}
 destroy(){this.abort.abort();this.observer.disconnect();}
}
