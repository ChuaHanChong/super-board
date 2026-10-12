# Shared skill-map shell

Every skill-map page (`impeccable`, `pstack`, ...) renders through one shell, so nav bar, header, toolbar, dialog, order strip and footer look and behave the same.

Build one page: `python3 diagrams/_shared/build_skillmap.py <map>` writes `diagrams/<map>/index.html` (single self-contained file, stdlib only).

Files: `sitenav.html` (site nav, same markup as /onboarding/), `shell.css` + `shell.html` + `shell.js` (page frame, search/filter, full screen, theme, dialog glue), `skillmap.css` + `skillmap.js` (dialog component).

## Add a map
1. Create `diagrams/<map>/map.py` with `build()` returning a dict:
   `key` (nav entry: `impeccable`, `pstack` or a new one you add to `sitenav.html`), `title`, `version`, `subtitle` (html), `svg` (inline `<svg class="map" id="map" viewBox=...>`, every clickable node/group has `data-id`), `mapw` (svg width in px), `css` (your palette + svg styles; set `--c` per node class), `js`, `order` (list of `(n, title, sub, css_class)`), `footer` (html), optional `filter` (`label`, `options=[(value,label,icon_svg)]`) and `legend` (html).
2. `js` must set `SMPAGE={model:function(id){...}, label:function(id){...}}` and `window.SMDATA={search:{id:text}, filt:{id:[values]}}`. `model(id)` returns `{accent, title, tags, blocks}` (see `skillmap.js` `render`).
3. Add the page to `.github/workflows/pages.yml` and a card to `diagrams/index.html`.
