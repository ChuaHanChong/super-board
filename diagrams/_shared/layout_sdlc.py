"""Layout `sdlc`: six stage layers (Plan > Design > Build > Test > Deploy > Maintain), categories side by side with chains of skills,
plus an Anytime band. build(data) -> dict for build_skillmap.py. Schema: see _shared/README.md and the map.json files."""
import html, json, math, re
E = html.escape
STAGES = ["plan", "design", "build", "test", "deploy", "maintain"]
SNAME = dict(plan="Plan", design="Design", build="Build", test="Test", deploy="Deploy", maintain="Maintain")
LIGHT = dict(plan="#b45309", design="#7c3aed", build="#2563eb", test="#15803d", deploy="#c2410c", maintain="#0e7490", anytime="#475569")
DARK = dict(plan="#fbbf24", design="#a78bfa", build="#60a5fa", test="#34d399", deploy="#fb923c", maintain="#22d3ee", anytime="#94a3b8")
W = 1440; X0 = 16; NW = 132; NH = 54; GX = 30; GY = 26; PADX = 14

def wrapname(n, lim=17):
    if len(n) <= lim: return [n]
    parts = n.split('-'); best = None
    for i in range(1, len(parts)):
        a = '-'.join(parts[:i]) + '-'; b = '-'.join(parts[i:]); sc = max(len(a), len(b))
        if best is None or sc < best[0]: best = (sc, a, b)
    return list(best[1:]) if best else [n[:lim]]

def build(data, mdir):
    meta = data["meta"]; skills = data["skills"]; cats = data["categories"]; stages = {s["id"]: s for s in data["stages"]}
    cat_by = {c["id"]: c for c in cats}
    skill_stage = {}
    for c in cats:
        for sid in c["chain"]: skill_stage.setdefault(sid, c["stage"])
    for g in data.get("anytime", []):
        for sid in g["items"]: skill_stage.setdefault(sid, "anytime")
    out = []; y = 14; prev = None; bands = {}

    def node(sid, x, yy, grp, start=False):
        s = skills[sid]; L = wrapname(s["name"]); st = skill_stage.get(sid, "anytime")
        ty = yy + (19 if len(L) == 1 else 15)
        tx = "".join(f'<text class="nn" x="{x+9}" y="{ty+i*12}">{E(l)}</text>' for i, l in enumerate(L))
        tr = f'<text class="nt" x="{x+9}" y="{yy+(36 if len(L)==1 else 41)}">{E(s.get("trigger",""))}</text>'
        sb = f'<rect class="stbg" x="{x+NW-44}" y="{yy-7}" width="40" height="13" rx="6.5"/><text class="stt" x="{x+NW-24}" y="{yy+3}" text-anchor="middle">START</text>' if start else ""
        return (f'<g class="nd st-{st}" data-id="{E(sid)}" data-grp="{grp}" tabindex="0" role="button" aria-label="{E(s["name"])}: {E(s.get("trigger",""))}">'
                f'<title>{E(s["name"])}</title><rect x="{x}" y="{yy}" width="{NW}" height="{NH}" rx="8"/>{tx}{tr}{sb}</g>')

    def head(stage_id, n, label, x, yy, w, kind):
        return (f'<g class="sh st-{stage_id}" data-id="{kind}:{stage_id}" data-grp="{stage_id}" data-head="1" tabindex="0" role="button" aria-label="{E(label)} (a stage, not a skill)">'
                f'<rect class="tag" x="{x}" y="{yy}" width="{w}" height="26" rx="5"/>'
                f'<text class="tagt" x="{x+11}" y="{yy+17.5}">{E(label)}</text></g>')

    for i, sid in enumerate(STAGES):
        st = stages.get(sid, {"id": sid, "name": SNAME[sid]}); cs = [c for c in cats if c["stage"] == sid]
        label = f"{i+1} · {SNAME[sid].upper()}"
        parts = []
        if not cs:
            h = 82
            parts.append(f'<g class="rg st-{sid} empty" data-region="{sid}"><rect class="band" x="{X0}" y="{y}" width="{W-2*X0}" height="{h}" rx="10"/></g>')
            parts.append(head(sid, i + 1, label, X0 + 12, y + 12, 18 + len(label) * 8, "stage"))
            parts.append(f'<text class="emp" data-grp="{sid}" x="{X0+18}" y="{y+64}">No skills for this stage in {E(meta["name"])}</text>')
        else:
            avail = W - 2 * X0 - 2 * PADX; wts = [min(max(len(c["chain"]), 2), 4) for c in cs]; tot = sum(wts)
            cw = [avail * w_ / tot for w_ in wts]; cx = []; acc = X0 + PADX
            for w_ in cw: cx.append(acc); acc += w_
            infos = []
            for c, w_ in zip(cs, cw):
                cols = max(1, int((w_ - 2 * PADX + GX) // (NW + GX))); rows = math.ceil(len(c["chain"]) / cols); infos.append((cols, rows))
            ch = max(r for _, r in infos) * (NH + GY) - GY
            h = 12 + 26 + 14 + 24 + 14 + ch + 18
            parts.append(f'<g class="rg st-{sid}" data-region="{sid}"><rect class="band" x="{X0}" y="{y}" width="{W-2*X0}" height="{h}" rx="10"/></g>')
            parts.append(head(sid, i + 1, label, X0 + 12, y + 12, 18 + len(label) * 8, "stage"))
            ty = y + 12 + 26 + 14
            for k, (c, w_, (cols, rows)) in enumerate(zip(cs, cw, infos)):
                x = cx[k]
                if k:
                    parts.append(f'<line class="div" data-grp="{sid}" x1="{x-PADX/2}" y1="{ty-4}" x2="{x-PADX/2}" y2="{y+h-14}"/>')
                parts.append(f'<g class="ch st-{sid}" data-id="cat:{E(c["id"])}" data-grp="{sid}" tabindex="0" role="button" aria-label="{E(c["name"])} (a category)"><title>Category: {E(c["name"])}. Tap for details.</title>'
                             f'<rect class="chb" x="{x-4}" y="{ty-3}" width="{w_-2*PADX+8}" height="24" rx="6"/><text class="cht" x="{x+2}" y="{ty+14}">{E(c["name"])}</text><text class="chn" x="{x+w_-2*PADX}" y="{ty+14}" text-anchor="end">{len(c["chain"])}</text></g>')
                ny = ty + 24 + 14
                pos = []
                for j, sk in enumerate(c["chain"]):
                    r, cc = divmod(j, cols); px = x + cc * (NW + GX); py = ny + r * (NH + GY); pos.append((px, py))
                    parts.append(node(sk, px, py, sid, j == 0))
                for j in range(len(pos) - 1):
                    (ax, ay), (bx, by) = pos[j], pos[j + 1]
                    if by == ay: parts.append(f'<path class="arr" data-grp="{sid}" d="M{ax+NW} {ay+NH/2} H{bx-2}" marker-end="url(#ah)"/>')
                    else:
                        ym = ay + NH + GY / 2
                        parts.append(f'<path class="arr" data-grp="{sid}" d="M{ax+NW/2} {ay+NH} V{ym} H{bx+NW/2} V{by-2}" marker-end="url(#ah)"/>')
        out.append("".join(parts)); bands[sid] = (y, h)
        if prev is not None:
            py_, ph_ = bands[prev]; xm = W / 2
            out.append(f'<path class="arr flowdn" data-edge="{prev} {sid}" d="M{xm} {py_+ph_+1} V{y-3}" marker-end="url(#ah)"/>')
        prev = sid; y += h + 30
    # anytime
    ag = data.get("anytime", [])
    if ag:
        n = len(ag); avail = W - 2 * X0 - 2 * PADX; gw = avail / n
        percol = max(1, int((gw - 2 * PADX + 20) // (NW + 20))); rows = max(math.ceil(len(g["items"]) / percol) for g in ag)
        h = 12 + 26 + 14 + 24 + 14 + rows * (NH + 18) + 6
        out.append(f'<g class="rg st-anytime" data-region="anytime"><rect class="band any" x="{X0}" y="{y}" width="{W-2*X0}" height="{h}" rx="10"/></g>')
        out.append(head("anytime", 0, "ANYTIME", X0 + 12, y + 12, 96, "stage"))
        ty = y + 12 + 26 + 14
        for k, g in enumerate(ag):
            x = X0 + PADX + k * gw
            if k: out.append(f'<line class="div" data-grp="anytime" x1="{x-PADX/2}" y1="{ty-4}" x2="{x-PADX/2}" y2="{y+h-14}"/>')
            out.append(f'<g class="ch st-anytime" data-id="any:{E(g["id"])}" data-grp="anytime" tabindex="0" role="button" aria-label="{E(g["name"])} (a group)"><title>Group: {E(g["name"])}</title>'
                       f'<rect class="chb" x="{x-4}" y="{ty-3}" width="{gw-2*PADX+8}" height="24" rx="6"/><text class="cht" x="{x+2}" y="{ty+14}">{E(g["name"])}</text><text class="chn" x="{x+gw-2*PADX}" y="{ty+14}" text-anchor="end">{len(g["items"])}</text></g>')
            for j, sk in enumerate(g["items"]):
                r, cc = divmod(j, percol); out.append(node(sk, x + cc * (NW + 20), ty + 38 + r * (NH + 18), "anytime"))
        y += h
    VH = y + 16
    svg = (f'<svg class="map" id="map" viewBox="0 0 {W} {VH}" role="group" aria-label="{E(meta["name"])} diagram"><defs>'
           '<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" class="ahp"/></marker></defs>' + "".join(out) + "</svg>")
    css = (":root{" + "".join(f"--st-{k}:{v};" for k, v in LIGHT.items()) + "}\n@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){" + "".join(f"--st-{k}:{v};" for k, v in DARK.items()) + "}}\n:root[data-theme=\"dark\"]{" + "".join(f"--st-{k}:{v};" for k, v in DARK.items()) + "}\n"
           + "".join(f".st-{k}{{--c:var(--st-{k})}}" for k in LIGHT) + r'''
.band{fill:color-mix(in srgb,var(--c) 5%,var(--bg));stroke:var(--c);stroke-width:1.4}.band.any{stroke-dasharray:6 4}
.empty .band{fill:var(--bg2);stroke:var(--muted);stroke-dasharray:4 4;opacity:.7}.emp{fill:var(--muted);font:600 13px var(--sans)}
.tag{fill:var(--c)}.tagt{fill:var(--bg);font:800 12px var(--sans);letter-spacing:.08em}
.sh{cursor:pointer;outline:none}.sh:hover .tag,.sh:focus-visible .tag,.sh.sel .tag{filter:brightness(1.15)}.empty .tag{fill:var(--muted)}
.div{stroke:var(--c);stroke-opacity:.45;stroke-width:1.2;stroke-dasharray:3 4}
.ch{cursor:pointer;outline:none}.chb{fill:color-mix(in srgb,var(--c) 14%,transparent);stroke:none}.ch:hover .chb,.ch:focus-visible .chb,.ch.sel .chb{fill:color-mix(in srgb,var(--c) 28%,transparent)}
.cht{fill:var(--c);font:800 13px var(--sans)}.chn{fill:var(--muted);font:600 11px var(--sans)}
.nd{cursor:pointer;outline:none}.nd rect{fill:var(--bg);stroke:var(--c);stroke-width:1.6}
.nd:hover rect,.nd:focus-visible rect{fill:color-mix(in srgb,var(--c) 16%,var(--bg));stroke-width:2.6}.nd.sel rect{fill:color-mix(in srgb,var(--c) 24%,var(--bg));stroke-width:3}
.nn{fill:var(--fg);font:600 11px var(--mono)}.nt{fill:var(--muted);font:10px var(--sans)}
.stbg{fill:var(--c)!important;stroke:none!important}.stt{fill:var(--bg);font:800 8px var(--sans);letter-spacing:.06em}
.arr{stroke:var(--muted);stroke-width:1.5;fill:none}.ahp{fill:var(--muted)}.flowdn{stroke-width:2}
''')
    # ---- page js: models built from the same json
    pack = {"stages": stages, "cats": {c["id"]: c for c in cats}, "any": {g["id"]: g for g in ag}, "skills": skills, "order": STAGES,
            "skillStage": skill_stage, "meta": meta, "SN": SNAME}
    js = "var PACK=" + json.dumps(pack, ensure_ascii=False).replace("</", "<\\/") + ";\n" + (open(__file__.replace("layout_sdlc.py", "layout_sdlc.js"), encoding="utf-8").read())
    plats = sorted({p for s in skills.values() for p in s.get("platforms", [])})
    PL = dict(zip(["claude-code", "cursor", "codex"], ["Claude Code", "Cursor", "Codex"]))
    flt = dict(label="Show skills for", options=[("all", "All", "All")] + [(p, PL.get(p, p), PL.get(p, p)) for p in plats]) if plats else None
    src = "".join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener">{E(s["label"])}</a> · ' for s in meta.get("sources", []))[:-3]
    order = [(str(i + 1), SNAME[s], re.sub(r"\*\*|==", "", stages.get(s, {}).get("principle") or "No skills in this pack")[:46], f"st-{s}") for i, s in enumerate(STAGES)]
    return dict(key=meta.get("nav", ""), title=meta["name"], version=meta.get("version", "") or "template", subtitle=E(meta.get("tagline", "")),
                svg=svg, mapw=1200, css=css, js=js, order=order, filter=flt, legend="", footer=("Sources: " + src) if src else "", out=meta.get("out"))
