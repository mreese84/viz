"""Parse a poster's GPX files and write its ride data.

    python3 scripts/build_data.py <poster>      # e.g. italy-2024

Reads gpx/<poster>/*.gpx (git-ignored) and src/posters/<poster>/config.json ("build" section),
writes src/posters/<poster>/rides_data.js (the RIDES array the page draws).

Rides are sorted by start time; config "build.rides" is in that same order.
Climb start/end indices are Strava segment-effort stream indices (= GPX trackpoint indices).
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

def main(poster):
    cfg = json.load(open(os.path.join(ROOT, "src", "posters", poster, "config.json"), encoding="utf-8"))["build"]
    tz = ZoneInfo(cfg["tz"])
    strip = re.compile(cfg["stripName"]) if cfg.get("stripName") else None
    files = []
    for f in glob.glob(os.path.join(ROOT, "gpx", poster, "*.gpx")):
        root = ET.parse(f).getroot()
        files.append((root.find(".//g:trkpt/g:time", NS).text, f, root))
    files.sort()
    if len(files) != len(cfg["rides"]):
        sys.exit(f"{len(files)} GPX files in gpx/{poster}/ but {len(cfg['rides'])} rides in the config")

    rides = []
    for k, (t0, f, root) in enumerate(files):
        meta = cfg["rides"][k]
        pts = []
        for p in root.iterfind(".//g:trkpt", NS):
            pts.append((float(p.get("lat")), float(p.get("lon")), float(p.find("g:ele", NS).text),
                        datetime.fromisoformat(p.find("g:time", NS).text.replace("Z", "+00:00"))))
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
        # place labels: ["Name", "north"] = northernmost point, ["Name", lat, lon] = nearest point;
        # an optional last string is the caption under the name (default: the poster language's word for town)
        for pl in meta.get("places", []):
            if pl[1] == "north":
                im = max(range(len(pts)), key=lambda i: pts[i][0]); sub = pl[2] if len(pl) > 2 else None
            else:
                im = min(range(len(pts)), key=lambda i: hav(pts[i], pl[1:3])); sub = pl[3] if len(pl) > 3 else None
            label = dict(name=pl[0], at=round(dist[im]/total, 4), ele=round(es[im], 1), place=True)
            if sub: label["sub"] = sub
            labels.append(label)
        # climbs: ["Label", start_index, end_index or null]; the label sits at the highest point in range
        for name, si, ei in meta.get("climbs", []):
            ei = len(es)-1 if ei is None else min(ei, len(es)-1)
            im = max(range(si, ei+1), key=lambda i: es[i])
            labels.append(dict(name=name, at=round(dist[im]/total, 4), ele=round(es[im], 1)))
        name = root.find("g:trk/g:name", NS).text.strip()
        if strip: name = strip.sub("", name).strip()
        st = pts[0][3].astimezone(tz)
        rides.append(dict(
            id=meta["id"], name=name, town=meta["town"], region=meta["region"],
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
