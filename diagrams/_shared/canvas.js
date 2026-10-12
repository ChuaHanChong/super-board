/* Shared canvas mode + collapsible groups. SVG contract: g[data-region=gid] (group box), [data-grp=gid] (members), [data-head] (title element, also a node),
   path/line [data-edge="fromGid toGid"], path [data-trunk=gid] (shared trunk, hidden once its group moves). Layout state is saved per page. */
(function(){
 var hero=document.getElementById('hero'),sc=document.getElementById('sc'),svg=sc.querySelector('svg');if(!svg)return;
 var NS='http://www.w3.org/2000/svg',KEY='sm-canvas:'+location.pathname.replace(/index\.html$/,''),THR=5;
 var st={on:false,off:{},col:{},cam:null};try{var s0=JSON.parse(localStorage.getItem(KEY)||'null');if(s0){st.on=!!s0.on;st.off=s0.off||{};st.col=s0.col||{};st.cam=s0.cam||null}}catch(e){}
 function save(){try{localStorage.setItem(KEY,JSON.stringify(st))}catch(e){}}
 var $a=function(s,r){return Array.prototype.slice.call((r||svg).querySelectorAll(s))};
 var vb0=svg.getAttribute('viewBox').split(/[ ,]+/).map(Number);
 /* groups */
 var G={};
 $a('[data-region]').forEach(function(r){var id=r.dataset.region;G[id]={id:id,region:r,rect:r.querySelector('rect'),members:[],head:null,x:0,y:0}});
 $a('[data-grp]').forEach(function(n){var id=n.dataset.grp;if(!G[id])G[id]={id:id,region:null,rect:null,members:[],head:null};if(n.hasAttribute('data-head'))G[id].head=n;else G[id].members.push(n)});
 Object.keys(G).forEach(function(id){var g=G[id];g.h0=g.rect?+g.rect.getAttribute('height'):0;
  if(g.rect&&g.members.length){var rx=+g.rect.getAttribute('x'),ry=+g.rect.getAttribute('y'),w=+g.rect.getAttribute('width');g.cx=rx+w-18;g.cy=ry+18;
   var c=document.createElementNS(NS,'g');c.setAttribute('class','gchev');c.setAttribute('role','button');c.setAttribute('tabindex','0');c.dataset.chev=id;
   c.innerHTML='<circle r="11"/><path d=""/>';c.setAttribute('transform','translate('+g.cx+' '+g.cy+')');g.chev=c;
   var t=document.createElementNS(NS,'text');t.setAttribute('class','gcount');t.setAttribute('text-anchor','end');t.setAttribute('x',g.cx);t.setAttribute('y',g.cy+30);t.style.display='none';g.count=t;
   var cl=(g.region.getAttribute('class')||'').split(' ').filter(function(x){return /^(c-|g-)/.test(x)});c.setAttribute('class','gchev '+cl.join(' '));t.setAttribute('class','gcount '+cl.join(' '));
   g.region.parentNode.appendChild(t);g.region.parentNode.appendChild(c)}});
 var edges=$a('[data-edge]').map(function(p){var a=p.dataset.edge.split(' ');return {el:p,a:a[0],b:a[1],d0:p.getAttribute('d')||null,line:p.tagName==='line'?{x1:p.getAttribute('x1'),y1:p.getAttribute('y1'),x2:p.getAttribute('x2'),y2:p.getAttribute('y2')}:null}});
 var trunks=$a('[data-trunk]');
 function ownTr(el){return el.__off||{x:0,y:0}}
 function setT(el,x,y){el.__tx=x;el.__ty=y;if(x||y)el.setAttribute('transform','translate('+x+' '+y+')');else el.removeAttribute('transform')}
 function goff(id){var o=st.on?st.off[id]:null;return o||{x:0,y:0}}
 function noff(el){var o=st.on?st.off['n:'+el.dataset.id]:null;return o||{x:0,y:0}}
 function layout(){
  Object.keys(G).forEach(function(id){var g=G[id],o=goff(id),col=!!st.col[id]&&g.members.length;
   var els=[g.region,g.head,g.chev,g.count].filter(Boolean);els.forEach(function(el){setT(el,o.x,o.y)});
   if(g.chev){g.chev.setAttribute('transform','translate('+(g.cx+o.x)+' '+(g.cy+o.y)+')')}
   if(g.count){g.count.setAttribute('transform','translate('+o.x+' '+o.y+')');g.count.style.display=col?'':'none';g.count.textContent=g.members.length+' items'}
   g.members.forEach(function(n){var m=noff(n);setT(n,o.x+m.x,o.y+m.y);n.style.display=col?'none':''});
   if(g.rect){var h=g.h0;if(col){var hb=g.head?g.head.getBBox():null,top=+g.rect.getAttribute('y');h=hb?(hb.y+hb.height+22-top):40}g.rect.setAttribute('height',h);if(g.count){g.count.setAttribute('x',+g.rect.getAttribute('x')+(+g.rect.getAttribute('width'))-14);g.count.setAttribute('y',+g.rect.getAttribute('y')+h-7)}}
   if(g.chev){g.chev.querySelector('path').setAttribute('d',col?'M-3 -4 L3 0 L-3 4':'M-4 -3 L0 3 L4 -3');g.chev.setAttribute('aria-label',(col?'Expand ':'Collapse ')+id)}});
  box();
  var dirtyG={};Object.keys(G).forEach(function(id){var o=goff(id);if(o.x||o.y||st.col[id])dirtyG[id]=1});
  edges.forEach(function(e){var A=G[e.a],B=G[e.b];if(!A||!B)return;var dirty=dirtyG[e.a]||dirtyG[e.b];
   if(!dirty){if(e.d0)e.el.setAttribute('d',e.d0);else if(e.line){for(var k in e.line)e.el.setAttribute(k,e.line[k])}e.el.style.display='';return}
   var a=gb(A),b=gb(B),d;
   if(b.l>=a.r-4){var y1=a.t+(A.head?hh(A):a.h/2),y2=b.t+(B.head?hh(B):b.h/2),xm=(a.r+b.l)/2;d='M'+a.r+' '+y1+' H'+xm+' V'+y2+' H'+b.l}
   else if(b.r<=a.l+4){var y1b=a.t+a.h/2,y2b=b.t+b.h/2,xm2=(a.l+b.r)/2;d='M'+a.l+' '+y1b+' H'+xm2+' V'+y2b+' H'+b.r}
   else if(b.t>=a.b){var x1=a.l+a.w/2,x2=b.l+b.w/2,ym=(a.b+b.t)/2;d='M'+x1+' '+a.b+' V'+ym+' H'+x2+' V'+b.t}
   else{var x1c=a.l+a.w/2,x2c=b.l+b.w/2,ym2=(a.t+b.b)/2;d='M'+x1c+' '+a.t+' V'+ym2+' H'+x2c+' V'+b.b}
   if(e.line){var ln=document.createElementNS(NS,'path');for(var i=0;i<e.el.attributes.length;i++){var at=e.el.attributes[i];if(!/^(x1|y1|x2|y2)$/.test(at.name))ln.setAttribute(at.name,at.value)}e.el.parentNode.replaceChild(ln,e.el);e.el=ln;e.line=null}
   e.el.setAttribute('d',d)});
  var anyR=Object.keys(dirtyG).length&&edges.some(function(e){return e.a==='router'&&(dirtyG[e.b]||dirtyG.router)});
  trunks.forEach(function(t){t.style.display=anyR?'none':''});
 }
 function hh(g){if(!g.rect)return 25;var hb=g.head.getBBox();return hb.y+hb.height/2-(+g.rect.getAttribute('y')||hb.y)}
 function gb(g){var o=goff(g.id);if(g.rect){var x=+g.rect.getAttribute('x')+o.x,y=+g.rect.getAttribute('y')+o.y,w=+g.rect.getAttribute('width'),h=+g.rect.getAttribute('height');return {l:x,t:y,w:w,h:h,r:x+w,b:y+h}}
  var bb=g.head.getBBox();return {l:bb.x+o.x,t:bb.y+o.y,w:bb.width,h:bb.height,r:bb.x+bb.width+o.x,b:bb.y+bb.height+o.y}}
 function hh2(){}
 function box(){}
 /* camera */
 var cam={cx:0,cy:0,k:1};
 function size(){return [sc.clientWidth||800,sc.clientHeight||500]}
 function contentBox(){var bb=svg.getBBox();return {x:bb.x,y:bb.y,w:bb.width,h:bb.height}}
 function apply(){var s=size(),W=s[0],H=s[1];svg.setAttribute('viewBox',(cam.cx-W/(2*cam.k))+' '+(cam.cy-H/(2*cam.k))+' '+(W/cam.k)+' '+(H/cam.k))}
 function fit(){var s=size(),b=contentBox(),k=Math.min((s[0]-24)/b.w,(s[1]-24)/b.h);cam={k:k,cx:b.x+b.w/2,cy:b.y+b.h/2};apply();persist()}
 function zoomAt(f,sx,sy){var s=size();if(sx==null){sx=s[0]/2;sy=s[1]/2}var wx=cam.cx+(sx-s[0]/2)/cam.k,wy=cam.cy+(sy-s[1]/2)/cam.k,k=Math.min(4,Math.max(.15,cam.k*f));cam={k:k,cx:wx-(sx-s[0]/2)/k,cy:wy-(sy-s[1]/2)/k};apply();persist()}
 function persist(){st.cam=cam;save()}
 /* gestures */
 var ptrs={},g0=null,pinch0=0,pinchCam=null;window.SMcanvas={moved:false};
 function toWorld(cx,cy){var r=sc.getBoundingClientRect(),s=size();return [cam.cx+(cx-r.left-s[0]/2)/cam.k,cam.cy+(cy-r.top-s[1]/2)/cam.k]}
 sc.addEventListener('pointerdown',function(e){if(!st.on)return;if(e.pointerType==='mouse'&&e.button!==0)return;if(e.target.closest('[data-chev]'))return;
  ptrs[e.pointerId]=[e.clientX,e.clientY];SMcanvas.moved=false;
  var n=e.target.closest('[data-id]'),r=e.target.closest('[data-region]'),what=null;
  if(n){what=n.hasAttribute('data-head')?{g:n.dataset.grp}:(n.dataset.grp?{n:n.dataset.id,gid:n.dataset.grp}:null)}else if(r&&G[r.dataset.region]){what={g:r.dataset.region}}
  if(Object.keys(ptrs).length>1){g0=null;pinch0=pd();pinchCam={k:cam.k,cx:cam.cx,cy:cam.cy};return}
  g0={x:e.clientX,y:e.clientY,what:what,cam:{k:cam.k,cx:cam.cx,cy:cam.cy},o:what?(what.g?JSON.parse(JSON.stringify(goff(what.g))):JSON.parse(JSON.stringify(st.off['n:'+what.n]||{x:0,y:0}))):null,drag:false}});
 function pd(){var p=Object.keys(ptrs).map(function(k){return ptrs[k]});return p.length>1?Math.hypot(p[0][0]-p[1][0],p[0][1]-p[1][1]):0}
 window.addEventListener('pointermove',function(e){if(!ptrs[e.pointerId])return;ptrs[e.pointerId]=[e.clientX,e.clientY];
  if(Object.keys(ptrs).length>1&&pinch0){var d=pd(),p=Object.keys(ptrs).map(function(k){return ptrs[k]}),r=sc.getBoundingClientRect();cam={k:pinchCam.k,cx:pinchCam.cx,cy:pinchCam.cy};zoomAt(d/pinch0,(p[0][0]+p[1][0])/2-r.left,(p[0][1]+p[1][1])/2-r.top);SMcanvas.moved=true;return}
  if(!g0)return;var dx=e.clientX-g0.x,dy=e.clientY-g0.y;if(!g0.drag&&Math.hypot(dx,dy)<THR)return;
  if(!g0.drag){g0.drag=true;SMcanvas.moved=true;hero.classList.add('grabbing')}
  if(g0.what){var k=cam.k,nx=g0.o.x+dx/k,ny=g0.o.y+dy/k;if(g0.what.g)st.off[g0.what.g]={x:nx,y:ny};else st.off['n:'+g0.what.n]={x:nx,y:ny};layout()}
  else{cam={k:g0.cam.k,cx:g0.cam.cx-dx/g0.cam.k,cy:g0.cam.cy-dy/g0.cam.k};apply()}});
 function up(e){if(!ptrs[e.pointerId])return;delete ptrs[e.pointerId];if(Object.keys(ptrs).length<2)pinch0=0;
  if(!Object.keys(ptrs).length){hero.classList.remove('grabbing');if(g0&&g0.drag){if(g0.what)save();else persist()}g0=null}}
 window.addEventListener('pointerup',up);window.addEventListener('pointercancel',up);
 sc.addEventListener('wheel',function(e){if(!st.on)return;e.preventDefault();var r=sc.getBoundingClientRect(),dy=e.deltaMode===1?e.deltaY*16:e.deltaY,dx=e.deltaMode===1?e.deltaX*16:e.deltaX,pinch=e.ctrlKey||e.metaKey;
  if(!pinch&&e.deltaMode===0&&(Math.abs(dx)>0||(Math.abs(dy)<40&&!Number.isInteger(dy)))){cam.cx+=dx/cam.k;cam.cy+=dy/cam.k;apply();persist();return}
  zoomAt(Math.exp(-dy*(pinch?.012:.0022)),e.clientX-r.left,e.clientY-r.top)},{passive:false});
 /* collapse */
 function toggle(id){st.col[id]=!st.col[id];if(!st.col[id])delete st.col[id];layout();sync();save()}
 sc.addEventListener('click',function(e){var c=e.target.closest('[data-chev]');if(c){e.stopPropagation();toggle(c.dataset.chev)}},true);
 sc.addEventListener('keydown',function(e){var c=e.target.closest&&e.target.closest('[data-chev]');if(c&&(e.key==='Enter'||e.key===' ')){e.preventDefault();toggle(c.dataset.chev)}});
 var ids=Object.keys(G).filter(function(i){return G[i].members.length&&G[i].chev});
 var bcol=document.getElementById('cv-col');
 function allCol(){return ids.every(function(i){return st.col[i]})}
 function sync(){var a=allCol();bcol.textContent=a?'Expand all':'Collapse all';bcol.setAttribute('aria-label',a?'Expand all groups':'Collapse all groups')}
 bcol.onclick=function(){var a=allCol();ids.forEach(function(i){if(a)delete st.col[i];else st.col[i]=true});layout();sync();save()};
 /* mode */
 var bon=document.getElementById('cv-on'),cvc=document.getElementById('cvc');
 function mode(on,fitNow){st.on=on;hero.classList.toggle('cv',on);bon.setAttribute('aria-pressed',String(on));cvc.hidden=!on;
  if(on){if(st.cam&&!fitNow){cam={k:st.cam.k,cx:st.cam.cx,cy:st.cam.cy};apply()}else{fit()}}else{svg.setAttribute('viewBox',vb0.join(' '))}
  layout();save()}
 bon.onclick=function(){mode(!st.on,!st.cam)};
 document.getElementById('cv-in').onclick=function(){zoomAt(1.25)};document.getElementById('cv-out').onclick=function(){zoomAt(0.8)};
 document.getElementById('cv-fit').onclick=fit;
 document.getElementById('cv-reset').onclick=function(){st.off={};st.col={};st.cam=null;layout();sync();fit()};
 window.addEventListener('resize',function(){if(st.on)apply()});
 document.addEventListener('fullscreenchange',function(){if(st.on)setTimeout(fit,50)});
 hero.addEventListener('transitionend',function(){});
 var wasExp=false;new MutationObserver(function(){var x=hero.classList.contains('exp');if(x!==wasExp){wasExp=x;if(st.on)setTimeout(fit,30)}}).observe(hero,{attributes:true,attributeFilter:['class']});
 mode(st.on,false);sync();
})();
