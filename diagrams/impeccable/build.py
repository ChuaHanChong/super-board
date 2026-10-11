# usage: python3 gen.py && python3 build.py index.html   (stdlib only; no Archify needed)
import html, json, sys
from pathlib import Path
from data import *
out = sys.argv[1]; e = html.escape
root = Path(__file__).resolve().parent
svg = (root / "diagram.svg").read_text(encoding="utf-8")
commands = {c[0]: c for c in C}
INFO = {}
for cid, c in commands.items():
    INFO[cid] = {"name": "/impeccable" if cid == "menu" else c[1], "g": c[2], "what": ONE[cid], "when": TRIG[cid],
                 "how": HOW[cid], "get": GET[cid], "next": NEXT[cid]}
for group, title, subtitle, ids in STAGES:
    INFO["stage_" + group] = {"name": title, "g": group, "what": subtitle.capitalize() + ".", "when": None,
                              "how": [commands[i][1] + ": " + ONE[i] for i in ids], "howTitle": "What is inside", "get": None, "next": None}
FLOW = [("1", "Setup", "init · document · extract", "ctx"), ("2", "Plan / build", "shape · craft", "plan"),
        ("3", "Diagnose", "critique + audit", "diag"), ("4", "Fix & style", "harden … bolder, animate", "fix"),
        ("5", "Finish", "polish, always last", "fin")]
flow = "".join(f'<div class="step g-{g}"><span class="n">{n}</span><b>{e(t)}</b><small>{e(s)}</small></div>' for n, t, s, g in FLOW)
colors = "".join(f".g-{g[0]}{{--c:var(--{g[0]})}}" for g in GROUPS)
page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>impeccable commands map</title>
<style>
:root{{--bg:#f4f5f7;--fg:#0f172a;--muted:#64748b;--card:#fff;--line:#e2e8f0;
--ctx:#ea580c;--plan:#c2410c;--diag:#e11d48;--fix:#059669;--style:#0891b2;--motion:#0e7490;--fin:#475569;--sys:#7c3aed;--util:#d97706}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0b1020;--fg:#e2e8f0;--muted:#94a3b8;--card:#111827;--line:#1f2937;--ctx:#fbbf24;--plan:#fb923c;--diag:#fb7185;--fix:#34d399;--style:#22d3ee;--motion:#22d3ee;--fin:#94a3b8;--util:#a78bfa}}}}
:root[data-theme="dark"]{{--bg:#0b1020;--fg:#e2e8f0;--muted:#94a3b8;--card:#111827;--line:#1f2937;--ctx:#fbbf24;--plan:#fb923c;--diag:#fb7185;--fix:#34d399;--style:#22d3ee;--motion:#22d3ee;--fin:#94a3b8;--util:#a78bfa}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}}
main{{max-width:1440px;margin:0 auto;padding:24px 16px 32px}}
h1{{font-size:24px;margin:0 0 2px}} .sub{{color:var(--muted);margin:0 0 14px}}
{colors}
.canvas{{position:relative;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px}}
.tools{{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:2px 4px 6px;color:var(--muted);font-size:12.5px}}
.tools button{{white-space:nowrap;font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:3px 10px;cursor:pointer}}
.scroll{{overflow-x:auto}}
svg.map{{display:block;width:100%;min-width:1000px;height:auto}}
svg.map text{{font-family:inherit;fill:var(--fg)}}
.r rect{{fill:none;stroke:var(--c);stroke-opacity:.55;stroke-dasharray:5 5}}
.r text{{font-size:12px;font-weight:700;fill:var(--c);text-transform:uppercase;letter-spacing:.04em}}
.n{{cursor:pointer;outline:none}}
.n rect{{fill:color-mix(in srgb,var(--c) 13%,var(--card));stroke:var(--c);stroke-width:1.5}}
.n.stage rect{{fill:color-mix(in srgb,var(--c) 24%,var(--card));stroke-width:2}}
.n:hover rect,.n:focus-visible rect{{stroke-width:3}} .n.on rect{{stroke-width:3.5;fill:color-mix(in srgb,var(--c) 30%,var(--card))}}
.t1{{font:600 14px ui-monospace,Menlo,monospace}} .t2{{font-size:11px;fill:var(--muted)!important}}
.arrow{{stroke:var(--muted);stroke-width:1.6;fill:none}} .ahead{{fill:var(--muted)}}
.pop{{position:absolute;z-index:5;width:340px;max-height:calc(100% - 16px);overflow:auto;background:var(--card);color:var(--fg);border:1px solid var(--line);border-top:4px solid var(--c);border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.22);padding:12px 14px 14px;font-size:13px}}
.pop[hidden]{{display:none}}
.pop h2{{font:700 16px ui-monospace,Menlo,monospace;margin:0 28px 6px 0;color:var(--c)}}
.pop .x{{position:absolute;top:6px;right:6px;width:32px;height:32px;border:0;border-radius:8px;background:transparent;color:var(--muted);font-size:22px;line-height:1;cursor:pointer}}
.pop .x:hover{{background:var(--bg)}}
.pop h3{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--c);margin:10px 0 3px}}
.pop p{{margin:0}} .pop ul{{margin:0;padding-left:18px}} .pop li{{margin:2px 0}}
.pop .tag{{display:inline-block;background:color-mix(in srgb,var(--c) 16%,var(--card));color:var(--c);font-weight:600;border-radius:99px;padding:1px 10px}}
.pop .nx{{margin-top:10px;padding-top:8px;border-top:1px solid var(--line)}} .pop .nx b{{color:var(--c)}}
.flow{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:8px}}
.step{{background:var(--bg);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:6px 10px;display:grid;grid-template-columns:auto 1fr;column-gap:8px}}
.step .n{{grid-row:span 2;font:700 18px/1 ui-monospace,Menlo,monospace;color:var(--c);align-self:center}} .step small{{color:var(--muted)}}
@media (max-width:760px){{
 main{{padding:16px 12px 24px}} h1{{font-size:20px}}
 .flow{{grid-template-columns:1fr 1fr}}
 .pop{{position:fixed;left:8px;right:8px;bottom:8px;width:auto;max-height:68vh;border-radius:14px}}
}}
</style></head><body><main>
<h1>impeccable · slash commands</h1>
<p class="sub">v4.0.4 · {len(C)} commands · read left to right, then tap a command to see how it works.</p>
<div class="canvas" id="canvas">
<div class="tools"><span>Setup → plan / build → diagnose → fix &amp; style → polish last</span><button id="theme" type="button" aria-label="Toggle light or dark">Light / dark</button></div>
<div class="scroll">{svg}</div>
<div class="flow" aria-label="Best-practice order">{flow}</div>
<div class="pop" id="pop" role="dialog" aria-modal="false" aria-labelledby="pt" hidden></div>
</div>
</main>
<script>
var INFO={json.dumps(INFO)};
var canvas=document.getElementById('canvas'),pop=document.getElementById('pop'),cur=null,lastNode=null;
function esc(s){{var d=document.createElement('div');d.textContent=s;return d.innerHTML}}
function close(){{pop.hidden=true;if(cur)cur.classList.remove('on');cur=null;if(lastNode)lastNode.focus&&lastNode.focus({{preventScroll:true}})}}
function place(n){{if(matchMedia('(max-width:760px)').matches){{pop.style.left=pop.style.top='';return}}
 var c=canvas.getBoundingClientRect(),r=n.getBoundingClientRect(),w=pop.offsetWidth,h=pop.offsetHeight;
 var x=r.right-c.left+12;if(x+w>c.width-8)x=r.left-c.left-w-12;x=Math.max(8,Math.min(x,c.width-w-8));
 var y=r.top-c.top-10;y=Math.max(8,Math.min(y,c.height-h-8));pop.style.left=x+'px';pop.style.top=y+'px'}}
function open(n){{var i=INFO[n.dataset.id];if(!i)return;if(cur)cur.classList.remove('on');cur=n;lastNode=n;n.classList.add('on');
 pop.className='pop g-'+i.g;
 var h='<button class="x" type="button" aria-label="Close">×</button><h2 id="pt">'+esc(i.name)+'</h2><h3>What it is</h3><p>'+esc(i.what)+'</p>';
 if(i.when)h+='<h3>When to use it</h3><p><span class="tag">'+esc(i.when)+'</span></p>';
 h+='<h3>'+(i.howTitle||'How it works behind the scenes')+'</h3><ul>'+i.how.map(function(s){{return'<li>'+esc(s)+'</li>'}}).join('')+'</ul>';
 if(i.get)h+='<h3>What you get</h3><p>'+esc(i.get)+'</p>';
 if(i.next)h+='<p class="nx"><b>Next:</b> '+esc(i.next)+'</p>';
 pop.innerHTML=h;pop.hidden=false;pop.scrollTop=0;pop.querySelector('.x').onclick=close;place(n)}}
canvas.addEventListener('click',function(ev){{var n=ev.target.closest('.n[data-id]');if(n){{ev.stopPropagation();cur===n&&!pop.hidden?close():open(n)}}}});
canvas.addEventListener('keydown',function(ev){{var n=ev.target.closest&&ev.target.closest('.n[data-id]');if(n&&(ev.key==='Enter'||ev.key===' ')){{ev.preventDefault();open(n)}}}});
document.addEventListener('keydown',function(ev){{if(ev.key==='Escape'&&!pop.hidden)close()}});
document.addEventListener('click',function(ev){{if(!pop.hidden&&!pop.contains(ev.target)&&!ev.target.closest('.n'))close()}});
window.addEventListener('resize',function(){{if(cur&&!pop.hidden)place(cur)}});
document.getElementById('theme').onclick=function(){{var r=document.documentElement,d=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');r.setAttribute('data-theme',d==='dark'?'light':'dark')}};
</script></body></html>'''
Path(out).write_text(page, encoding="utf-8"); print(out, len(page))
