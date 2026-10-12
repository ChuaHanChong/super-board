# usage: python3 gen.py && python3 build.py index.html   (stdlib only; shared dialog from ../_shared/)
import html, json, sys
from pathlib import Path
from data import *
out = sys.argv[1]; e = html.escape
root = Path(__file__).resolve().parent
svg = (root / "diagram.svg").read_text(encoding="utf-8")
SH = root.parent / "_shared"
SMCSS = (SH / "skillmap.css").read_text(encoding="utf-8"); SMJS = (SH / "skillmap.js").read_text(encoding="utf-8")
commands = {c[0]: c for c in C}
CMDS = "|".join(sorted(commands, key=len, reverse=True))
import re
def chipify(t):  # command names in plain NEXT text -> [[chip]]
    return re.sub(r"\b(" + CMDS + r")\b", r"[[\1]]", t) if t not in ("Done. Ship it",) else t
def step(cid, t):  # bold the first verb; one highlight per section
    h = HOWH.get(cid)
    if h and h in t: t = t.replace(h, "==" + h + "==", 1)
    elif len(t.split(" ")[0]) > 3: t = "**" + t.split(" ")[0] + "**" + t[len(t.split(" ")[0]):]
    return t
def name(cid): return "/impeccable" if cid == "menu" else commands[cid][1]
MODELS = {}
for cid, c in commands.items():
    B = [{"label": "When to use it", "key": "when", "type": "when", "v": WHENL[cid]},
         {"label": "What it is", "key": "is", "type": "p", "v": ONE[cid]},
         {"label": "How it works", "key": "how", "type": "ol", "v": [step(cid, t) for t in HOW[cid]]}]
    sit, typ, steps, get = EX2[cid]
    B.append({"label": "Example", "key": "ex", "type": "example", "note": "Example. A realistic case, written from the reference file.",
              "v": [["Situation", sit], ["You type", typ, "code"], ["What happens", steps], ["You get", get]]})
    if cid == "menu":
        B.append({"label": "How it picks", "key": "picks", "type": "flows", "v": ROUTE_PICKS})
        B.append({"label": "Or just say it in words", "key": "picks", "type": "flows", "v": ROUTE_WORDS})
    else:
        B.append({"label": "Behind the scenes", "key": "bts", "type": "flows", "v": FLOWS[cid]})
    if cid in CALLS:
        B.append({"label": "Calls these", "key": "calls", "type": "flows", "v": [["/" + name(cid), ["@" + k for k, _ in CALLS[cid]]]]})
    B.append({"label": "What you get", "key": "get", "type": "p", "v": GET[cid]})
    if NEXT[cid]: B.append({"label": "Next", "key": "next", "type": "p", "v": chipify(NEXT[cid])})
    MODELS[cid] = {"title": name(cid), "accent": "g-rt" if cid == "menu" else "g-" + c[2], "tags": [[TRIG[cid], 1], ["router" if cid == "menu" else dict((g[0], g[1]) for g in GROUPS)[c[2]].split(" · ")[0]]], "blocks": B}
for group, title, subtitle, ids in STAGES:
    x = STAGEX[group]; sit, typ, steps, get = STAGE_EX2[group]
    MODELS["stage_" + group] = {"title": title, "accent": "g-" + group, "tags": [["STAGE · GROUP", 1]], "blocks": [
        {"label": "What this stage is for", "key": "grp", "type": "p", "v": x["for"]},
        {"label": "Not a command", "key": "warn", "type": "note", "v": '**You cannot run "' + title + '".** It is a **group label**. You run the **commands inside it**.'},
        {"label": "When X → pick Y", "key": "when", "type": "when", "v": STAGE_WHEN[group]},
        {"label": "No router for this stage yet", "key": "picks", "type": "p", "v": "Pick by the symptom above. " + x["run"]},
        {"label": "Example", "key": "ex", "type": "example", "note": "Example. A realistic case.", "v": [["Situation", sit], ["You type", typ, "code"], ["What happens", steps], ["You get", get]]}]}
JS = "var MODELS=" + json.dumps(MODELS) + ";\nvar NAMES=" + json.dumps({k: name(k) for k in commands}) + ";" + r'''
var canvas=document.getElementById('canvas'),cur=null,lastNode=null;
var D=SM.Dialog(document.getElementById('pop'),{label:function(id){return NAMES[id]||id},
 onGo:function(id){var t=canvas.querySelector('svg [data-id="'+id+'"]');if(t)open(t)},
 onClose:function(){if(cur)cur.classList.remove('on');cur=null;if(lastNode&&lastNode.focus)lastNode.focus({preventScroll:true})}});
function open(n){var m=MODELS[n.dataset.id];if(!m)return;if(cur)cur.classList.remove('on');cur=n;lastNode=n;n.classList.add('on');D.render(m);D.open()}
canvas.addEventListener('click',function(ev){var n=ev.target.closest('[data-id]');if(n)open(n)});
canvas.addEventListener('keydown',function(ev){var n=ev.target.closest&&ev.target.closest('[data-id]');if(n&&(ev.key==='Enter'||ev.key===' ')){ev.preventDefault();open(n)}});
document.getElementById('theme').onclick=function(){var r=document.documentElement,d=r.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');r.setAttribute('data-theme',d==='dark'?'light':'dark')};
'''
FLOW = [("1", "Setup", "init · document · extract", "ctx"), ("2", "Plan / build", "shape · craft", "plan"),
        ("3", "Diagnose", "critique + audit", "diag"), ("4", "Fix & style", "harden … bolder, animate", "fix"),
        ("5", "Finish", "polish, always last", "fin")]
flow = "".join(f'<div class="step g-{g}"><span class="n">{n}</span><b>{e(t)}</b><small>{e(s)}</small></div>' for n, t, s, g in FLOW)
colors = "".join(f".g-{g[0]}{{--c:var(--{g[0]})}}" for g in GROUPS) + ".g-rt{--c:var(--rt)}"
page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>impeccable commands map</title>
<style>
:root{{--bg:#f4f5f7;--fg:#0f172a;--muted:#64748b;--card:#fff;--line:#e2e8f0;
--ctx:#ea580c;--plan:#c2410c;--diag:#e11d48;--fix:#059669;--style:#0891b2;--motion:#0e7490;--fin:#475569;--sys:#7c3aed;--rt:#7c3aed;--util:#d97706}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0b1020;--fg:#e2e8f0;--muted:#94a3b8;--card:#111827;--line:#1f2937;--ctx:#fbbf24;--plan:#fb923c;--diag:#fb7185;--fix:#34d399;--style:#22d3ee;--motion:#22d3ee;--fin:#94a3b8;--util:#a78bfa;--rt:#a78bfa}}}}
:root[data-theme="dark"]{{--bg:#0b1020;--fg:#e2e8f0;--muted:#94a3b8;--card:#111827;--line:#1f2937;--ctx:#fbbf24;--plan:#fb923c;--diag:#fb7185;--fix:#34d399;--style:#22d3ee;--motion:#22d3ee;--fin:#94a3b8;--util:#a78bfa;--rt:#a78bfa}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}}
main{{max-width:1440px;margin:0 auto;padding:24px 16px 32px}}
h1{{font-size:24px;margin:0 0 2px}} .sub{{color:var(--muted);margin:0 0 14px}}
{colors}
{SMCSS}
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
.stagehead{{cursor:pointer;outline:none}} .stagehead .s1{{font-size:9.5px;letter-spacing:.08em;font-weight:700;fill:var(--muted)!important}}
.stagehead .s2{{font-size:17px;font-weight:800;fill:var(--c)!important}} .stagehead .s3{{font-size:11px;fill:var(--muted)!important;font-weight:400}}
.stagehead .bar{{fill:var(--c);opacity:.8}} .stagehead:hover .s2,.stagehead:focus-visible .s2,.stagehead.on .s2{{text-decoration:underline}}
.router{{cursor:pointer;outline:none}} .router rect{{fill:color-mix(in srgb,var(--rt) 18%,var(--card));stroke:var(--rt);stroke-width:3}} .router .s1{{font-size:10px;letter-spacing:.1em;font-weight:800;fill:var(--rt)!important}}
.router:hover rect,.router:focus-visible rect,.router.on rect{{stroke-width:4.5}} .bus{{stroke:var(--rt);stroke-width:1.6;fill:none;stroke-dasharray:4 3;opacity:.8}}
.badge rect{{fill:var(--c)}} .badge text{{font-size:10px;font-weight:700;fill:var(--card)!important}}
.flow{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:8px}}
.step{{background:var(--bg);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:6px 10px;display:grid;grid-template-columns:auto 1fr;column-gap:8px}}
.step .n{{grid-row:span 2;font:700 18px/1 ui-monospace,Menlo,monospace;color:var(--c);align-self:center}} .step small{{color:var(--muted)}}
@media (max-width:760px){{
 main{{padding:16px 12px 24px}} h1{{font-size:20px}}
 .flow{{grid-template-columns:1fr 1fr}}
}}
</style></head><body><main>
<h1>impeccable · slash commands</h1>
<p class="sub">v{VERSION} · {len(C) - 1} commands + the /impeccable router · read left to right, then tap anything to see how it works.</p>
<div class="canvas" id="canvas">
<div class="tools"><span>Setup → plan / build → diagnose → fix &amp; style → polish last</span><button id="theme" type="button" aria-label="Toggle light or dark">Light / dark</button></div>
<div class="scroll">{svg}</div>
<div class="flow" aria-label="Best-practice order">{flow}</div>
<dialog id="pop" aria-label="Details"></dialog>
</div>
</main>
<script>
{SMJS}
{JS}
</script></body></html>'''
Path(out).write_text(page, encoding="utf-8"); print(out, len(page))
