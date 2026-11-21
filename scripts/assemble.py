"""Build the site into dist/ (everything there is generated; the directory is rewritten on each run).

    python3 scripts/assemble.py

- dist/<poster>/index.html for every src/posters/<poster>/ (template.html + config.json + rides_data.js)
- dist/index.html, the gallery (gallery.html + a card per poster, newest trip first). Card thumbnails are
  radial elevation silhouettes drawn here from each poster's data, so they always match the posters.
- dist/new/, the "Add poster" page: src/new/* plus site.json, the poster template, and presets.json (every
  poster's colour themes, and the web addresses already taken).
"""
import html, json, math, os, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, DIST = os.path.join(ROOT, "src"), os.path.join(ROOT, "dist")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def read(*p): return open(os.path.join(*p), encoding="utf-8").read()

def load(slug):
    cfg = json.loads(read(SRC, "posters", slug, "config.json"))
    data = read(SRC, "posters", slug, "rides_data.js")
    rides = json.loads(data.strip()[len("const RIDES = "):].rstrip(";"))
    return cfg, data, rides

def date_range(d0, d1):
    (y0, m0, a), (y1, m1, b) = [tuple(map(int, d.split("-"))) for d in (d0, d1)]
    if (y0, m0) == (y1, m1): return f"{MONTHS[m0-1]} {a} – {b}, {y1}"
    return f"{MONTHS[m0-1]} {a} – {MONTHS[m1-1]} {b}, {y1}"

def silhouette(cfg, rides, size=400):
    """Small radial elevation profile in the poster's default theme, same geometry and relief scale as the poster."""
    T, E = cfg["themes"][cfg["defaultTheme"]], cfg["elevation"]
    c, disc, base, top = size/2, size*0.18, size*0.21, size*0.46
    total = sum(r["dist"] for r in rides)
    span = E["topFt"]/3.28084 - E["minM"]   # the poster's default scale (imperial, default relief)
    shape = math.sqrt if cfg.get("defaultRelief", "sqrt") == "sqrt" else (lambda x: x)
    sc = lambda e: base + (top-base)*shape(min(1, max(0, (e - E["minM"]) / span)))
    pt = lambda a, r: f"{c + r*math.sin(a):.1f},{c - r*math.cos(a):.1f}"
    out, start = [], 0.0
    for i, r in enumerate(rides):
        a0, a1 = start/total*2*math.pi, (start + r["dist"])/total*2*math.pi
        prof = r["profile"]; step = max(1, len(prof)//max(24, int(720*r["dist"]/total)))
        idx = list(range(0, len(prof), step))
        if idx[-1] != len(prof)-1: idx.append(len(prof)-1)
        outer = " L".join(pt(a0 + (a1-a0)*k/(len(prof)-1), sc(prof[k])) for k in idx)
        large = 1 if a1 - a0 > math.pi else 0
        wedge = f"M{pt(a0, base)} A{base:.1f},{base:.1f} 0 {large} 1 {pt(a1, base)} L{pt(a1, top+6)} A{top+6:.1f},{top+6:.1f} 0 {large} 0 {pt(a0, top+6)}Z"
        out.append(f'<path d="{wedge}" fill="{T["text"]}" opacity="{0.08 if i % 2 else 0.03}"/>')
        out.append(f'<path d="M{outer} L{pt(a1, base)} A{base:.1f},{base:.1f} 0 {large} 0 {pt(a0, base)}Z" fill="{T["profile"]}" stroke="{T["profileLine"]}" stroke-width=".6" stroke-linejoin="round"/>')
        start += r["dist"]
    gid = "g-" + cfg["storageKey"]
    return (f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="{html.escape(cfg["ariaLabel"])}">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{T["bgTop"]}"/>'
            f'<stop offset="1" stop-color="{T["bgBottom"]}"/></linearGradient></defs>'
            f'<rect width="{size}" height="{size}" fill="url(#{gid})"/>{"".join(out)}'
            f'<circle cx="{c}" cy="{c}" r="{disc:.1f}" fill="{T["disc"]}"/>'
            f'<line x1="{c}" y1="{c-disc:.1f}" x2="{c}" y2="{c-top-10:.1f}" stroke="{T["accent"]}" stroke-width="1.2"/></svg>')

def card(slug, cfg, rides):
    mi = sum(r["dist"] for r in rides) / 1609.344
    ft = sum(r["gain"] for r in rides) * 3.28084
    n = len(rides)
    return f'''    <a class="card" href="{slug}/">
      {silhouette(cfg, rides)}
      <div class="meta">
        <h2>{html.escape(cfg["title"])}</h2>
        <p class="when">{date_range(rides[0]["date"], rides[-1]["date"])} · {n} ride{"s" if n != 1 else ""}</p>
        <p class="stats">{mi:,.0f} mi · {ft:,.0f} ft climbed</p>
        <p class="summary">{html.escape(cfg["summary"])}</p>
      </div>
    </a>'''

def main():
    template = read(SRC, "template.html")
    slugs = sorted(d for d in os.listdir(os.path.join(SRC, "posters")) if os.path.isfile(os.path.join(SRC, "posters", d, "config.json")))
    posters = [(slug, *load(slug)) for slug in slugs]
    if os.path.isdir(DIST): shutil.rmtree(DIST)
    for slug, cfg, data, rides in posters:
        page = {k: v for k, v in cfg.items() if k != "build"}
        out = (template.replace("__TITLE__", html.escape(cfg["title"]))
                       .replace("/*__DATA__*/", data + "const POSTER = " + json.dumps(page, ensure_ascii=False) + ";"))
        os.makedirs(os.path.join(DIST, slug))
        open(os.path.join(DIST, slug, "index.html"), "w", encoding="utf-8").write(out)
        print(f"wrote dist/{slug}/index.html")
    posters.sort(key=lambda p: p[3][0]["date"], reverse=True)   # newest trip first
    cards = "\n".join(card(slug, cfg, rides) for slug, cfg, _, rides in posters)
    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(read(SRC, "gallery.html").replace("<!--__CARDS__-->", cards))
    print("wrote dist/index.html (gallery)")
    shutil.copytree(os.path.join(SRC, "new"), os.path.join(DIST, "new"))
    shutil.copy(os.path.join(SRC, "site.json"), os.path.join(DIST, "new", "site.json"))
    shutil.copy(os.path.join(SRC, "template.html"), os.path.join(DIST, "new", "template.html"))
    themes = {}
    for _, cfg, _, _ in posters:
        for name, t in cfg["themes"].items(): themes.setdefault(name, t)
    presets = {"themes": themes, "slugs": sorted(slug for slug, *_ in posters)}
    open(os.path.join(DIST, "new", "presets.json"), "w", encoding="utf-8").write(json.dumps(presets, ensure_ascii=False, indent=1))
    print("wrote dist/new/ (Add poster page)")

if __name__ == "__main__":
    main()
