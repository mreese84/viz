"""Parse every GPX in gpx/ and write src/rides_data.js (RIDES array used by the poster).

Rides are sorted by start time; META and CLIMBS below are indexed in that same order.
CLIMBS start/end indices are Strava segment-effort stream indices (= GPX trackpoint indices).
"""
import glob, json, math, os, sys
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

NS = {"g": "http://www.topografix.com/GPX/1/1"}
ROME = ZoneInfo("Europe/Rome")

def hav(a, b):
    R = 6371008.8
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(d))

def smooth(v, w):
    n = len(v); c = [0.0]
    for x in v: c.append(c[-1]+x)
    return [(c[min(n, i+w+1)]-c[max(0, i-w)])/(min(n, i+w+1)-max(0, i-w)) for i in range(n)]

# Strava metadata, chronological order (matches GPX sort by start time)
META = [
  (11600233983, "Montefino", "Abruzzo"),
  (11609126332, "Montefino", "Abruzzo"),
  (11656439784, "San Giovanni di Fassa", "Dolomiti"),
  (11657162354, "Moena", "Dolomiti"),
  (11703642308, "Corvara in Badia", "Dolomiti"),
  (11710694545, "Corvara in Badia", "Dolomiti"),
  (11852086931, "Trequanda", "Toscana"),
  (11867926748, "Trequanda", "Toscana"),
  (11875958990, "Trequanda", "Toscana"),
  (11925078632, "Greve in Chianti", "Toscana"),
  (11941344747, "Greve in Chianti", "Toscana"),
  (11958410684, "Greve in Chianti", "Toscana"),
]
# Named climbs from Strava segments: (label, start_index, end_index); summit = highest point in range
CLIMBS = {
  0: [("Salita Castilenti", 1163, 2442)],
  1: [("Atri", 597, 2435),("Salita Marciano", 6149, 7123)],
  3: [("Soraga → Pozza", 204, 571)],
  4: [("Passo Gardena", 246, 3388), ("Passo Sella", 3400, 6182), ("Passo Pordoi", 7000, 9200), ("Passo Campolongo", 10300, None)],
  5: [("Passo Campolongo", 147, 1811), ("Falzarego · Valparola", 3357, 7810)],
  6: [("Madonnino dei Monti", 99, 402), ("Pienza", 2228, 2468), ("Castelmuzio", 2654, 3060)],
  7: [("Madonnino dei Monti", 214, 1167), ("Trequanda", 2239, 2720)],
  8: [("Montepulciano", 3540, 4865), ("Monticchiello", 6943, 7207), ("Pienza", 7676, 8800)],
  9: [("Radda in Chianti", 1043, 1970), ("Badia a Coltibuono", 2943, 4720)],
  10: [("Spedaluzzo", 7456, 9650), ("Panzano", 10461, 11948)],
  11: [("La Montagnola", 5567, 7297), ("Castellina in Chianti", 9920, 12226)],
}

files = []
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GPX_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "gpx")
OUT = os.path.join(ROOT, "src", "rides_data.js")
for f in glob.glob(os.path.join(GPX_DIR, "*.gpx")):
    root = ET.parse(f).getroot()
    t0 = root.find(".//g:trkpt/g:time", NS).text
    files.append((t0, f, root))
files.sort()

rides = []
for k, (t0, f, root) in enumerate(files):
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
    for name, si, ei in CLIMBS.get(k, []):
        ei = len(es)-1 if ei is None else min(ei, len(es)-1)
        im = max(range(si, ei+1), key=lambda i: es[i])
        labels.append(dict(name=name, at=round(dist[im]/total, 4), ele=round(es[im], 1)))
    if k == 10:  # Bistecca alla Fiorentina: turnaround in Florence = northernmost point
        im = max(range(len(pts)), key=lambda i: pts[i][0])
        labels.insert(0, dict(name="Firenze", at=round(dist[im]/total, 4), ele=round(es[im], 1), place=True))
    sid, town, region = META[k]
    st = pts[0][3].astimezone(ROME)
    rides.append(dict(
        id=sid, name=root.find("g:trk/g:name", NS).text.strip(), town=town, region=region,
        date=st.strftime("%Y-%m-%d"), dist=round(total, 1), gain=round(gain, 1),
        moving=round(moving), elapsed=round((pts[-1][3]-pts[0][3]).total_seconds()),
        maxEle=round(max(es), 1), minEle=round(min(es), 1), profile=prof, climbs=labels,
        maxLat=max(p[0] for p in pts),
    ))
    print(k+1, rides[-1]["name"][:30], [ (l["name"], l["at"], round(l["ele"]*3.28084)) for l in labels], round(rides[-1]["maxLat"], 3))

for r in rides: r.pop("maxLat")
open(OUT, "w").write("const RIDES = " + json.dumps(rides, separators=(",", ":"), ensure_ascii=False) + ";\n")
print(os.path.getsize(OUT), "bytes")
