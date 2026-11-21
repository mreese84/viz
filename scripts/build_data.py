"""Build a poster's ride data from its GPX files.

    python3 scripts/build_data.py <poster>      # e.g. italy-2024

Reads src/posters/<poster>/rides.json (rides in chronological order, with climbs and places) and
gpx/<poster>/*.gpx (git-ignored), writes src/posters/<poster>/rides_data.js (the RIDES array the page draws).
"""
import glob, json, math, os, re, sys
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

NS = {"g": "http://www.topografix.com/GPX/1/1"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def hav(a, b):
    R = 6371008.8
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(d))

def smooth(v, w):
    n = len(v); c = [0.0]
    for x in v: c.append(c[-1]+x)
    return [(c[min(n, i+w+1)]-c[max(0, i-w)])/(min(n, i+w+1)-max(0, i-w)) for i in range(n)]

# ---------- Sources: each gives the ride's name and points [(lat, lon, ele, datetime)] ----------
def gpx_rides(poster):
    """GPX files of a poster, in start-time order: [(name, pts)]."""
    files = []
    for f in glob.glob(os.path.join(ROOT, "gpx", poster, "*.gpx")):
        root = ET.parse(f).getroot()
        files.append((root.find(".//g:trkpt/g:time", NS).text, f, root))
    out = []
    for _, f, root in sorted(files):
        pts = [(float(p.get("lat")), float(p.get("lon")), float(p.find("g:ele", NS).text),
                datetime.fromisoformat(p.find("g:time", NS).text.replace("Z", "+00:00")))
               for p in root.iterfind(".//g:trkpt", NS)]
        out.append((root.find("g:trk/g:name", NS).text.strip(), pts))
    return out

# ---------- Labels ----------
def resolve_labels(ride, pts, efforts=None):
    """rides.json "climbs" entries -> [(label, kind, info)] with kind "range" (info=(start, end)) or
    "place" (info=(index, caption)). Segment climbs use their fallback range when no efforts are available."""
    out = []
    for c in ride.get("climbs", []):
        if "place" in c:
            if c["place"] == "northernmost":
                im = max(range(len(pts)), key=lambda i: pts[i][0])
            else:
                im = min(range(len(pts)), key=lambda i: hav(pts[i], c["place"]))
            out.append((c["label"], "place", (im, c.get("caption"))))
        elif "range" in c:
            out.append((c["label"], "range", tuple(c["range"])))
        else:
            print(f'  ! "{c["label"]}": segment climb without a fallback range, skipped (activity not fetched)')
    return out

def main(poster):
    cfg = json.load(open(os.path.join(ROOT, "src", "posters", poster, "rides.json"), encoding="utf-8"))
    tz = ZoneInfo(cfg["tz"])
    strip = re.compile(cfg["stripName"]) if cfg.get("stripName") else None
    sources = gpx_rides(poster)
    if len(sources) != len(cfg["rides"]):
        sys.exit(f"{len(sources)} GPX files in gpx/{poster}/ but {len(cfg['rides'])} rides in rides.json")

    rides = []
    for k, (ride, (name, pts)) in enumerate(zip(cfg["rides"], sources)):
        dist = [0.0]; moving = 0.0
        for i in range(1, len(pts)):
            d = hav(pts[i-1], pts[i]); dt = (pts[i][3]-pts[i-1][3]).total_seconds()
            dist.append(dist[-1]+d)
            if 0 < dt <= 30 and d/dt > 0.9: moving += dt
        es = smooth([p[2] for p in pts], 4)
        gain = 0.0; ref = es[0]
        for v in es:
            if v > ref + 1.5: gain += v-ref; ref = v
            elif v < ref: ref = v
        total = dist[-1]
        N = max(200, int(total/1609.344*30))  # ~30 samples per mile
        prof = []; j = 0
        for s in range(N+1):
            target = total*s/N
            while j < len(dist)-1 and dist[j+1] < target: j += 1
            prof.append(round(es[j], 1))
        labels = []
        for label, kind, info in resolve_labels(ride, pts):
            if kind == "place":
                im, caption = info
                lab = dict(name=label, at=round(dist[im]/total, 4), ele=round(es[im], 1), place=True)
                if caption: lab["sub"] = caption
            else:   # summit = highest point in the range; end null = to the end of the ride
                si, ei = info
                ei = len(es)-1 if ei is None else min(ei, len(es)-1)
                im = max(range(si, ei+1), key=lambda i: es[i])
                lab = dict(name=label, at=round(dist[im]/total, 4), ele=round(es[im], 1))
            labels.append(lab)
        if strip: name = strip.sub("", name).strip()
        st = pts[0][3].astimezone(tz)
        rides.append(dict(
            id=ride["id"], name=name, town=ride["town"], region=ride["region"],
            date=st.strftime("%Y-%m-%d"), dist=round(total, 1), gain=round(gain, 1),
            moving=round(moving), elapsed=round((pts[-1][3]-pts[0][3]).total_seconds()),
            maxEle=round(max(es), 1), minEle=round(min(es), 1), profile=prof, climbs=labels,
        ))
        print(k+1, name[:30], [(l["name"], l["at"], round(l["ele"]*3.28084)) for l in labels])

    out = os.path.join(ROOT, "src", "posters", poster, "rides_data.js")
    open(out, "w", encoding="utf-8").write("const RIDES = " + json.dumps(rides, separators=(",", ":"), ensure_ascii=False) + ";\n")
    print(os.path.getsize(out), "bytes ->", os.path.relpath(out, ROOT))

if __name__ == "__main__":
    if len(sys.argv) != 2: sys.exit(__doc__)
    main(sys.argv[1])
