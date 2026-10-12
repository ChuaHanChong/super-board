#!/usr/bin/env python3
"""Build one skill-map page: python3 diagrams/_shared/build_skillmap.py <map>
Reads diagrams/<map>/map.py (function build() -> dict) and writes diagrams/<map>/index.html as one self-contained file.
See diagrams/_shared/README.md for the dict contract and how to add a map."""
import html, importlib.util, json, sys
from pathlib import Path
SH = Path(__file__).resolve().parent
name = sys.argv[1]
mdir = SH.parent / name
sys.path.insert(0, str(mdir))
if (mdir / "map.json").exists():  # data-only map: rendered by a shared layout
    sys.path.insert(0, str(SH))
    data = json.loads((mdir / "map.json").read_text(encoding="utf-8"))
    import layout_sdlc
    m = layout_sdlc.build(data, mdir)
    if m.get("out"): mdir = SH.parent / m["out"]; mdir.mkdir(exist_ok=True)
else:
    spec = importlib.util.spec_from_file_location(name + "_map", mdir / "map.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    m = mod.build()
rd = lambda f: (SH / f).read_text(encoding="utf-8")
e = html.escape
import base64
def uri(rel): return "data:image/png;base64," + base64.b64encode((SH.parent / rel).read_bytes()).decode()
LOGOS = {"impeccable": "assets/logos/impeccable.png", "pstack": "assets/logos/poteto.png", "mattpocock": "assets/logos/mattpocock.png"}
img = lambda k: '<img class="ni nimg" alt="" src="%s">' % uri(LOGOS[k])
NAV = rd("sitenav.html")
for k in ("impeccable", "pstack"): NAV = NAV.replace("%%LOGO_" + k + "%%", img(k))
matt = ""
if (SH.parent / "mattpocock" / "index.html").exists() or name == "mattpocock":
    matt = '<a class="lk" href="../mattpocock/"%%A_mattpocock%%>' + img("mattpocock") + '<span class="nl">Matt Pocock<span class="hide-s"> map</span></span></a>'
NAV = NAV.replace("%%NAV_MATT%%", matt)
GENERIC = '<svg class="plogo" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4M4 16.5l8 4 8-4"/></svg>'
logo_rel = m.get("logo") or LOGOS.get(m["key"])
PLOGO = ('<img class="plogo" alt="" src="%s">' % uri(logo_rel)) if logo_rel else GENERIC
FAV = ('<link rel="icon" href="%s">' % uri(logo_rel)) if logo_rel else ""
for k in ("skill", "impeccable", "pstack", "mattpocock"):
    NAV = NAV.replace("%%A_" + k + "%%", ' aria-current="page"' if k == m["key"] else "")
flt = ""
if m.get("filter"):
    f = m["filter"]
    flt = f'<div class="seg" role="group" aria-label="{e(f["label"])}">' + "".join(
        f'<button type="button" data-f="{e(v)}" aria-pressed="{"true" if i == 0 else "false"}" aria-label="{e(l)}" title="{e(l)}">{icon}</button>' for i, (v, l, icon) in enumerate(f["options"])) + "</div>"
order = "".join(f'<div class="step {c}"><i>{e(n)}</i><span><b>{e(t)}</b><small>{e(s)}</small></span></div>' for n, t, s, c in m["order"])
t = rd("shell.html")
for k, v in {"%%TITLE%%": e(m["title"]), "%%PLOGO%%": PLOGO, "%%FAV%%": FAV, "%%VERSION%%": e(m["version"]), "%%SUBTITLE%%": m["subtitle"], "%%NAV%%": NAV, "%%FILTER%%": flt,
             "%%TOOLS%%": m.get("tools", ""), "%%SVG%%": m["svg"], "%%LEGEND%%": m.get("legend", ""), "%%ORDER%%": order, "%%FOOTER%%": m["footer"],
             "%%SHELLCSS%%": rd("shell.css") + "\n:root{--mapw:%dpx}" % m["mapw"], "%%SMCSS%%": rd("skillmap.css"), "%%PAGECSS%%": m["css"],
             "%%SMJS%%": rd("skillmap.js"), "%%PAGEJS%%": m["js"], "%%SHELLJS%%": rd("shell.js"), "%%CANVASJS%%": rd("canvas.js")}.items():
    t = t.replace(k, v)
(mdir / "index.html").write_text(t, encoding="utf-8")
print(mdir / "index.html", len(t))
