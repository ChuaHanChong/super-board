"""Layout `sdlc`: six stage layers (Plan > Design > Build > Test > Deploy > Maintain), categories side by side with chains of skills,
plus an Anytime band. build(data) -> dict for build_skillmap.py. Schema: see _shared/README.md and the map.json files."""
import html, json, math, re
E = html.escape
STAGES = ["plan", "design", "build", "test", "deploy", "maintain"]
SNAME = dict(plan="Plan", design="Design", build="Build", test="Test", deploy="Deploy", maintain="Maintain")
LIGHT = dict(plan="#b45309", design="#7c3aed", build="#2563eb", test="#15803d", deploy="#c2410c", maintain="#0e7490", anytime="#475569")
DARK = dict(plan="#fbbf24", design="#a78bfa", build="#60a5fa", test="#34d399", deploy="#fb923c", maintain="#22d3ee", anytime="#94a3b8")
W = 1440; X0 = 16; NW = 132; NH = 54; GX = 30; GY = 26; PADX = 14; CW = 330

ICON_ALL = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><rect x="3" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5"/></svg>'
ICON_CL = '<svg viewBox="0 0 24 24" aria-hidden="true"><g stroke="#d97757" stroke-width="3.2" stroke-linecap="round"><path d="M12 2.5v19M2.5 12h19M5.3 5.3l13.4 13.4M18.7 5.3L5.3 18.7"/></g></svg>'
ICON_CU = '<svg viewBox="0 0 24 24" aria-hidden="true" style="color:var(--fg)"><path d="M12 2.2l8.5 4.9v9.8L12 21.8l-8.5-4.9V7.1z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 12L3.8 7.2M12 12l8.2-4.8M12 12v9.5" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M12 12l4.2-2.4v4.8z" fill="currentColor"/></svg>'
ICON_CODEX = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/></svg>'

def wrapname(n, lim=17):
    if len(n) <= lim: return [n]
    parts = n.split('-'); best = None
    for i in range(1, len(parts)):
        a = '-'.join(parts[:i]) + '-'; b = '-'.join(parts[i:]); sc = max(len(a), len(b))
        if best is None or sc < best[0]: best = (sc, a, b)
    return list(best[1:]) if best else [n[:lim]]

def build(data, mdir):
    meta = data["meta"]; skills = data["skills"]; cats = data["categories"]; stages = {s["id"]: s for s in data["stages"]}
    skill_stage = {}
    for c in cats:
        for sid in c["chain"]: skill_stage.setdefault(sid, c["stage"])
    for g in data.get("anytime", []):
        for sid in g["items"]: skill_stage.setdefault(sid, "anytime")
    out = []; Y0 = 16

    def node(sid, x, yy, grp, start=False):
        s = skills[sid]; L = wrapname(s["name"]); nst = skill_stage.get(sid, "anytime")
        ty = yy + (19 if len(L) == 1 else 15)
        tx = "".join(f'<text class="nn" x="{x+9}" y="{ty+i*12}">{E(l)}</text>' for i, l in enumerate(L))
        tr = f'<text class="nt" x="{x+9}" y="{yy+(36 if len(L)==1 else 41)}">{E(s.get("trigger",""))}</text>'
        sb = f'<rect class="stbg" x="{x+NW-44}" y="{yy-7}" width="40" height="13" rx="6.5"/><text class="stt" x="{x+NW-24}" y="{yy+3}" text-anchor="middle">START</text>' if start else ""
        return (f'<g class="nd st-{nst}" data-id="{E(sid)}" data-grp="{grp}" tabindex="0" role="button" aria-label="{E(s["name"])}: {E(s.get("trigger",""))}">'
                f'<title>{E(s["name"])}</title><rect x="{x}" y="{yy}" width="{NW}" height="{NH}" rx="8"/>{tx}{tr}{sb}</g>')

    def head(grp, num, name, x, yy, kind, n):
        badge = f'<circle class="sbc" cx="{x+11}" cy="{yy+14}" r="11"/><text class="sbn" x="{x+11}" y="{yy+18}" text-anchor="middle">{num}</text>' if num else ""
        tx = x + (30 if num else 0)
        return (f'<g class="sh st-{grp}" data-id="{kind}:{grp}" data-grp="{grp}" data-head="1" tabindex="0" role="button" aria-label="{E(name)} ({"a stage" if num else "a band"}, not a skill)">'
                f'<rect class="hit" x="{x-4}" y="{yy-4}" width="168" height="36" fill="transparent"/>{badge}'
                f'<text class="stn" x="{tx}" y="{yy+19}">{E(name)}</text>'
                f'<text class="stc" x="{tx}" y="{yy+34}">{E(n)}</text></g>')

    per = 2
    colx = lambda i: X0 + i * CW
    # heights
    def cat_h(c): return 24 + 14 + math.ceil(len(c["chain"]) / per) * (NH + GY) - GY + 30
    cols = {sid: [c for c in cats if c["stage"] == sid] for sid in STAGES}
    body_h = max([sum(cat_h(c) for c in cs) for cs in cols.values() if cs] + [120])
    H_COL = 76 + body_h
    for i, sid in enumerate(STAGES):
        x = colx(i); cs = cols[sid]; st = stages.get(sid, {})
        out.append(f'<g class="rg{" empty" if not cs else ""}" data-region="{sid}"><rect class="col" x="{x}" y="{Y0}" width="{CW}" height="{H_COL}"/></g>')
        nsk = sum(len(c["chain"]) for c in cs)
        out.append(head(sid, i + 1, SNAME[sid], x + 18, Y0 + 14, "stage", f"{len(cs)} categories · {nsk} skills" if cs else "no skills here"))
        if i: out.append(f'<line class="div" data-grp="{sid}" x1="{x}" y1="{Y0+4}" x2="{x}" y2="{Y0+H_COL-4}"/>')
        if i < len(STAGES) - 1:
            out.append(f'<path class="arr flowdn" data-edge="{sid} {STAGES[i+1]}" d="M{x+CW-12} {Y0+50} H{x+CW+12}" marker-end="url(#ah)"/>')
        if not cs:
            out.append(f'<text class="emp" data-grp="{sid}" x="{x+18}" y="{Y0+92}">No skills for this stage</text><text class="emp" data-grp="{sid}" x="{x+18}" y="{Y0+110}">in {E(meta["name"])}</text>')
            continue
        ty = Y0 + 76
        for c in cs:
            out.append(f'<g class="ch st-{sid}" data-id="cat:{E(c["id"])}" data-grp="{sid}" tabindex="0" role="button" aria-label="{E(c["name"])} (a category)"><title>Category: {E(c["name"])}. Tap for details.</title>'
                       f'<rect class="chb" x="{x+14}" y="{ty-3}" width="{CW-28}" height="24" rx="6"/><text class="cht" x="{x+20}" y="{ty+14}">{E(c["name"])}</text><text class="chn" x="{x+CW-20}" y="{ty+14}" text-anchor="end">{len(c["chain"])}</text></g>')
            ny = ty + 24 + 14; pos = []
            for j, sk in enumerate(c["chain"]):
                r, cc = divmod(j, per); px = x + 18 + cc * (NW + GX); py = ny + r * (NH + GY); pos.append((px, py))
                out.append(node(sk, px, py, sid, j == 0))
            for j in range(len(pos) - 1):
                (ax, ay), (bx, by) = pos[j], pos[j + 1]
                if by == ay: out.append(f'<path class="arr" data-grp="{sid}" d="M{ax+NW} {ay+NH/2} H{bx-2}" marker-end="url(#ah)"/>')
                else:
                    ym = ay + NH + GY / 2
                    out.append(f'<path class="arr" data-grp="{sid}" d="M{ax+NW/2} {ay+NH} V{ym} H{bx+NW/2} V{by-2}" marker-end="url(#ah)"/>')
            ty += cat_h(c)
    TW = X0 * 2 + CW * len(STAGES)
    y = Y0 + H_COL + 36
    ag = data.get("anytime", [])
    if ag:
        per_a = max(1, int((TW - 2 * X0 - 36) // (NW + 20)))
        n = len(ag); gw = (TW - 2 * X0 - 36) / n; percol = max(1, int((gw - 10) // (NW + 20)))
        rows = max(math.ceil(len(g["items"]) / percol) for g in ag)
        h = 76 + rows * (NH + 18) + 10
        out.append(f'<g class="rg" data-region="anytime"><rect class="col top" x="{X0}" y="{y}" width="{TW-2*X0}" height="{h}"/></g>')
        out.append(head("anytime", 0, "Anytime", X0 + 18, y + 14, "stage", f"{sum(len(g['items']) for g in ag)} skills, not tied to one stage"))
        for k, g in enumerate(ag):
            x = X0 + 18 + k * gw
            if k: out.append(f'<line class="div" data-grp="anytime" x1="{x-12}" y1="{y+56}" x2="{x-12}" y2="{y+h-10}"/>')
            out.append(f'<g class="ch st-anytime" data-id="any:{E(g["id"])}" data-grp="anytime" tabindex="0" role="button" aria-label="{E(g["name"])} (a group)"><title>Group: {E(g["name"])}</title>'
                       f'<rect class="chb" x="{x-4}" y="{y+56}" width="{gw-24}" height="24" rx="6"/><text class="cht" x="{x+2}" y="{y+73}">{E(g["name"])}</text><text class="chn" x="{x+gw-32}" y="{y+73}" text-anchor="end">{len(g["items"])}</text></g>')
            for j, sk in enumerate(g["items"]):
                r, cc = divmod(j, percol); out.append(node(sk, x + cc * (NW + 20), y + 94 + r * (NH + 18), "anytime"))
        y += h
    VH = y + 16
    svg = (f'<svg class="map" id="map" viewBox="0 0 {TW} {VH}" role="group" aria-label="{E(meta["name"])} diagram"><defs>'
           '<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" class="ahp"/></marker></defs>' + "".join(out) + "</svg>")
    css = (":root{" + "".join(f"--st-{k}:{v};" for k, v in LIGHT.items()) + "}\n@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){" + "".join(f"--st-{k}:{v};" for k, v in DARK.items()) + "}}\n:root[data-theme=\"dark\"]{" + "".join(f"--st-{k}:{v};" for k, v in DARK.items()) + "}\n" + "".join(f".st-{k}{{--c:var(--st-{k})}}" for k in LIGHT) + r'''
.col{fill:none;stroke:none}.empty .stn,.empty .stc,.empty .sbn{opacity:.55}
.sh{cursor:pointer;outline:none}.stn{fill:var(--c);font:800 16px var(--sans)}.stc{fill:var(--muted);font:11px var(--sans)}
.sbc{fill:var(--c)}.empty .sbc{fill:var(--muted)}.sbn{fill:var(--bg);font:800 12px var(--sans)}
.sh:hover .stn,.sh:focus-visible .stn,.sh.sel .stn{fill:var(--c);text-decoration:underline}
.div{stroke:var(--border);stroke-width:1.5}.emp{fill:var(--muted);font:600 13px var(--sans)}
.ch{cursor:pointer;outline:none}.chb{fill:none;stroke:none}.ch:hover .chb,.ch:focus-visible .chb,.ch.sel .chb{fill:color-mix(in srgb,var(--c) 12%,transparent)}
.cht{fill:var(--c);font:800 13px var(--sans)}.chn{fill:var(--muted);font:600 11px var(--sans)}
.nd{cursor:pointer;outline:none}.nd rect{fill:var(--bg);stroke:var(--c);stroke-width:1.4}
.nd:hover rect,.nd:focus-visible rect{stroke:var(--c);stroke-width:2.4}.nd.sel rect{fill:color-mix(in srgb,var(--c) 14%,var(--bg));stroke:var(--c);stroke-width:2.6}
.nn{fill:var(--fg);font:600 11px var(--mono)}.nt{fill:var(--muted);font:10px var(--sans)}
.stbg{fill:var(--c)!important;stroke:none!important}.stt{fill:var(--bg);font:800 8px var(--sans);letter-spacing:.06em}
.arr{stroke:var(--muted);stroke-width:1.5;fill:none}.ahp{fill:var(--muted)}.flowdn{stroke-width:2}
.sm.calm h4,.sm.calm details.sec{--l:var(--c)}
.sm.calm h4,.sm.calm details.sec .sl{color:var(--c);background:color-mix(in srgb,var(--c) 10%,transparent);border-color:color-mix(in srgb,var(--c) 35%,transparent)}
.sm.calm ul.wl li{border-left-color:var(--c)}.sm.calm .chip{border-color:var(--c);color:var(--c)}
.sm.calm .ex{background:var(--bg2);border-color:var(--border)}.sm.calm .exr>b{color:var(--muted)}
''')
    # ---- page js: models built from the same json
    pack = {"stages": stages, "cats": {c["id"]: c for c in cats}, "any": {g["id"]: g for g in ag}, "skills": skills, "order": STAGES,
            "skillStage": skill_stage, "meta": meta, "SN": SNAME}
    js = "window.SMCANVAS='always';window.SMCOLLAPSED=['anytime'];var PACK=" + json.dumps(pack, ensure_ascii=False).replace("</", "<\\/") + ";\n" + (open(__file__.replace("layout_sdlc.py", "layout_sdlc.js"), encoding="utf-8").read())
    plats = sorted({p for s in skills.values() for p in s.get("platforms", [])})
    PL = dict(zip(["claude-code", "cursor", "codex"], ["Claude Code", "Cursor", "Codex"]))
    ICON = {"all": ICON_ALL, "claude-code": ICON_CL, "cursor": ICON_CU, "codex": ICON_CODEX}
    flt = dict(label="Show skills for", options=[("all", "All", ICON_ALL)] + [(p, PL.get(p, p), ICON.get(p, PL.get(p, p))) for p in plats]) if plats else None
    src = "".join(f'<a href="{E(s["url"])}" target="_blank" rel="noopener">{E(s["label"])}</a> · ' for s in meta.get("sources", []))[:-3]
    order = [(str(i + 1), SNAME[s], re.sub(r"\*\*|==", "", stages.get(s, {}).get("principle") or "No skills in this pack")[:46], f"st-{s}") for i, s in enumerate(STAGES)]
    return dict(key=meta.get("nav", ""), title=meta["name"], version=meta.get("version", "") or "template", subtitle=E(meta.get("tagline", "")),
                svg=svg, mapw=2012, css=css, js=js, order=order, filter=flt, legend="", footer=("Sources: " + src) if src else "", out=meta.get("out"))
