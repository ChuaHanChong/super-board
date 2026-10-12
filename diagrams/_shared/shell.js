/* Shared page behaviour: theme (nav button), search + filter dimming, full screen, dialog open/close. Page JS sets SMPAGE = {model(id), label(id), afterFilter?(visible)} and window.SMDATA = {search:{id:text}, filt:{id:[values]}}. */
(function(){
 var root=document.documentElement,$=function(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))};
 try{var th=localStorage.getItem('sb-theme');if(th)root.setAttribute('data-theme',th)}catch(e){}
 document.getElementById('sbtt').onclick=function(){var d=root.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'),n=d==='dark'?'light':'dark';root.setAttribute('data-theme',n);try{localStorage.setItem('sb-theme',n)}catch(e){}};
 var hero=document.getElementById('hero'),dlg=document.getElementById('pop'),P=SMPAGE,DATA=window.SMDATA||{search:{},filt:{}};
 var nodes=function(){return $('#hero svg [data-id]')},st={q:'',f:'all'},FKEY='sm-filter:'+location.pathname,cur=null,last=null;
 function apply(){var vis={};nodes().forEach(function(g){var id=g.dataset.id,t=DATA.search[id];if(t==null)return;
  var fv=DATA.filt[id],ok=(st.f==='all'||!fv||fv.indexOf(st.f)>=0)&&(!st.q||t.toLowerCase().indexOf(st.q)>=0);vis[id]=ok;g.classList.toggle('dim',!ok)});
  if(P.afterFilter)P.afterFilter(vis);
  var pill=document.getElementById('fpill');if(pill){if(st.f==='all'){pill.hidden=true}else{var ids={};nodes().forEach(function(g){var fv=DATA.filt[g.dataset.id];if(fv&&fv.indexOf(st.f)<0)ids[g.dataset.id]=1});
   var lbl=($('.seg button').filter(function(b){return b.dataset.f===st.f})[0]||{}).title||st.f;pill.textContent='';pill.appendChild(document.createTextNode('Showing '+lbl+' skills · '+Object.keys(ids).length+' greyed out · '));var a=document.createElement('button');a.type='button';a.textContent='Show all';a.onclick=function(){setF('all')};pill.appendChild(a);pill.hidden=false}}
  try{localStorage.setItem(FKEY,st.f)}catch(e){}}
 function setF(f){st.f=f;$('.seg button').forEach(function(x){x.setAttribute('aria-pressed',String(x.dataset.f===f))});apply()}
 try{var f0=localStorage.getItem(FKEY);if(f0&&$('.seg button').some(function(b){return b.dataset.f===f0}))setF(f0)}catch(e){}
 document.getElementById('q').addEventListener('input',function(e){st.q=e.target.value.trim().toLowerCase();apply()});
 $('.seg button').forEach(function(b){b.addEventListener('click',function(){st.f=b.dataset.f;$('.seg button').forEach(function(x){x.setAttribute('aria-pressed',String(x===b))});apply()})});
 var D=SM.Dialog(dlg,{label:P.label,onGo:function(id){open(id)},onClose:function(){nodes().forEach(function(x){x.classList.remove('sel')});cur=null;if(last)try{last.focus({preventScroll:true})}catch(e){}}});
var CMP=window.SMCOMPARE||null;
 function cmpBlock(id){var gs=CMP.groups[id],PK=CMP.packs;return {label:'Compare with similar skills',key:'cmp',type:'node',open:true,peek:gs.length>1?gs.length+' comparisons':'vs '+gs[0].members.filter(function(x){return !(x.pack===CMP.pack&&x.skill===id)}).map(function(x){return PK[x.pack].name}).join(', '),v:function(body,self){
  gs.forEach(function(g){var el=self.el;body.appendChild(el('p','cmpt',g.topic));var w=el('div','cmpw'),t=el('table','cmp'),h=el('tr');h.appendChild(el('th','cmpc',''));
   g.members.forEach(function(m){var cur=m.pack===CMP.pack&&m.skill===id,th=el('th',cur?'cur':'');var im=el('img','cmpl');im.src=PK[m.pack].logo;im.alt='';im.width=18;im.height=18;th.appendChild(im);
    var href=cur?null:(m.pack!==CMP.pack&&PK[m.pack].path&&m.onMap?PK[m.pack].path+'#skill-'+m.skill:m.url),a=href?el('a',null,m.name):el('span',null,m.name);if(href){a.href=href;if(!/^\.\./.test(href)){a.target='_blank';a.rel='noopener'}}
    th.appendChild(a);th.appendChild(el('small',null,PK[m.pack].name+(cur?' (this)':'')));h.appendChild(th)});t.appendChild(h);
   g.rows.forEach(function(r){var tr=el('tr');tr.appendChild(el('th','cmpc',r.aspect));g.members.forEach(function(m){var td=el('td',m.pack===CMP.pack&&m.skill===id?'cur':'');if(r.aspect==='Strictness'&&m.strict){var dt=el('span','dots','●'.repeat(m.strict)+'○'.repeat(3-m.strict));dt.title='Strictness '+m.strict+' of 3';td.appendChild(dt);td.appendChild(document.createTextNode(' '))}self.md(td,r.values[m.pack]||'—');tr.appendChild(td)});t.appendChild(tr)});
   w.appendChild(t);body.appendChild(w);
   var u=el('div','cmpick');g.members.forEach(function(m){var cur=m.pack===CMP.pack&&m.skill===id,c=el('span','pc'+(cur?' cur':'')),b=el('b',null,PK[m.pack].name);c.appendChild(b);c.appendChild(document.createTextNode(' '+(g.pick[m.pack]||'')));u.appendChild(c)});body.appendChild(u);
   if(g.sources&&g.sources.length){var sp=el('p','cmps');sp.appendChild(document.createTextNode('Sources: '));g.sources.forEach(function(s,i){if(i)sp.appendChild(document.createTextNode(' · '));var a=el('a',null,s.label);a.href=s.url;a.target='_blank';a.rel='noopener';sp.appendChild(a)});body.appendChild(sp)}})}}}
 function M(id){var m=P.model(id);if(!m||!CMP||!CMP.groups[id])return m;var i=-1;m.blocks.forEach(function(b,k){if(b.key==='is'&&i<0)i=k});m.blocks.splice(i<0?m.blocks.length:i+1,0,cmpBlock(id));return m}
 /* compare badge on nodes */
 if(CMP)nodes().forEach(function(g){if(!CMP.groups[g.dataset.id])return;var r=g.querySelector('rect');if(!r)return;var x=+r.getAttribute('x'),y=+r.getAttribute('y'),b=document.createElementNS('http://www.w3.org/2000/svg','g');b.setAttribute('class','cmpb');
  b.innerHTML='<title>Has a comparison with similar skills</title><circle cx="'+(x+3)+'" cy="'+(y+3)+'" r="8"/><text x="'+(x+3)+'" y="'+(y+7)+'" text-anchor="middle">≈</text>';g.appendChild(b)});
 function open(id){var g=nodes().filter(function(x){return x.dataset.id===id})[0];if(!g||!M(id))return;if(!dlg.open)last=g;
  D.render(M(id));cur=id;nodes().forEach(function(x){x.classList.toggle('sel',x===g)});D.open()}
 window.SMopen=open;
 var sc=document.getElementById('sc');
 sc.addEventListener('click',function(e){var n=e.target.closest('[data-id]');if(n&&!(window.SMcanvas&&window.SMcanvas.moved))open(n.dataset.id)});
 sc.addEventListener('keydown',function(e){var n=e.target.closest&&e.target.closest('[data-id]');if(n&&(e.key==='Enter'||e.key===' ')){e.preventDefault();open(n.dataset.id)}});
 var fsb=document.getElementById('fsb'),fst=document.getElementById('fst'),exp=false;
 function fsOn(){return document.fullscreenElement===hero}
 function sync(){var on=exp||fsOn();fst.textContent=on?'Exit':'Full screen';fsb.setAttribute('aria-label',on?'Exit full screen':'Full screen')}
 function expand(on){exp=on;hero.classList.toggle('exp',on);root.classList.toggle('lock',on);sync()}
 function exitAll(){if(fsOn()){try{document.exitFullscreen()}catch(e){}}if(exp)expand(false)}
 fsb.addEventListener('click',function(){if(exp||fsOn()){exitAll();return}var p;try{p=hero.requestFullscreen?hero.requestFullscreen():null}catch(x){p=null}
  if(p&&p.then){p.then(sync,function(){expand(true)})}else if(!p){expand(true)}});
 document.addEventListener('fullscreenchange',sync);
 document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!dlg.open&&exp)expand(false)});
 apply();
 function fromHash(){var h=location.hash.slice(1);if(!/^[A-Za-z0-9._-]+$/.test(h))return;var id=h.replace(/^skill-/,'');if(M(id)&&nodes().some(function(x){return x.dataset.id===id}))open(id)}
 window.addEventListener('hashchange',fromHash);setTimeout(fromHash,0);
})();
