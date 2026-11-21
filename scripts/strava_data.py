"""Read fetched Strava data (data/strava/<id>/) and work with its segment efforts. No network access.

Used by build_data.py and suggest_climbs.py.
"""
import difflib, json, math, os, re
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "strava")

def hav(a, b):
    R = 6371008.8
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    d = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*R*math.asin(math.sqrt(d))

def load(rid):
    """(activity, streams) for a fetched activity id, or None if it hasn't been fetched."""
    d = os.path.join(DATA, str(rid))
    a, s = os.path.join(d, "activity.json"), os.path.join(d, "streams.json")
    if not (os.path.exists(a) and os.path.exists(s)): return None
    return json.load(open(a, encoding="utf-8")), json.load(open(s, encoding="utf-8"))

def points(activity, streams):
    """Stream data as [(lat, lon, ele, datetime)] like the GPX reader, or None if a needed stream is missing."""
    try:
        ll, alt, t = streams["latlng"]["data"], streams["altitude"]["data"], streams["time"]["data"]
    except KeyError:
        return None
    if not (len(ll) == len(alt) == len(t)) or not ll: return None
    t0 = datetime.fromisoformat(activity["start_date"].replace("Z", "+00:00"))
    return [(la, lo, float(e), t0 + timedelta(seconds=s)) for (la, lo), e, s in zip(ll, alt, t)]

# ---------- Segment names ----------
def norm(s):
    return re.sub(r"\s+", " ", s).strip().casefold()

def match_segment(efforts, name, near=None):
    """Effort for a segment name -> (effort, how, note). how: "exact", "normalized" (case/whitespace) or
    "closest" (fuzzy, reported). Several efforts with that name: the one starting nearest `near`, else the first."""
    cands = [e for e in efforts if e["name"] == name]; how = "exact"
    if not cands:
        cands = [e for e in efforts if norm(e["name"]) == norm(name)]; how = "normalized"
    if not cands:
        names = sorted({e["name"] for e in efforts})
        close = difflib.get_close_matches(norm(name), [norm(n) for n in names], n=1, cutoff=0.6)
        if not close: return None, "missing", ""
        cands = [e for e in efforts if norm(e["name"]) == close[0]]; how = "closest"
    note = ""
    if len(cands) > 1:
        if near is not None:
            cands.sort(key=lambda e: abs(e["start_index"] - near))
        else:
            note = f"{len(cands)} efforts named like this; used the first (add \"near\": <index> to choose)"
    return cands[0], how, note

# ---------- Climb suggestions ----------
CATEGORY = {5: "HC", 4: "Cat 1", 3: "Cat 2", 2: "Cat 3", 1: "Cat 4", 0: "uncat."}

def suggestions(activity, pts, exclude=(), min_grade=2.0, min_gain=20.0):
    """Uphill segment efforts ranked by climb category, then elevation gain; overlapping efforts that share a
    summit merged into the best-ranked one. Returns dicts with effort, gain, summit index and elevation."""
    excl = {norm(x) for x in exclude}
    dist = [0.0]
    for i in range(1, len(pts)): dist.append(dist[-1] + hav(pts[i-1], pts[i]))
    cands = []
    for e in activity.get("segment_efforts", []):
        seg = e.get("segment", {})
        si, ei = e["start_index"], min(e["end_index"], len(pts)-1)
        if norm(e["name"]) in excl or ei <= si or seg.get("average_grade", 0) < min_grade: continue
        ele = [p[2] for p in pts[si:ei+1]]
        gain = max(ele) - ele[0]
        if gain < min_gain: continue
        top = si + ele.index(max(ele))
        cands.append(dict(effort=e, name=e["name"], si=si, ei=ei, cat=seg.get("climb_category", 0) or 0,
                          gain=gain, summit=top, summit_ele=max(ele), summit_d=dist[top]))
    cands.sort(key=lambda c: (-c["cat"], -c["gain"]))
    kept = []
    for c in cands:   # same summit (within 200 m along the ride) and overlapping ranges: keep the better one
        if any(k["si"] <= c["ei"] and c["si"] <= k["ei"] and abs(k["summit_d"] - c["summit_d"]) <= 200 for k in kept):
            continue
        kept.append(c)
    names = [e["name"] for e in activity.get("segment_efforts", [])]
    for c in kept:
        c["entry"] = {"label": c["name"].strip(), "segment": c["name"]}
        if names.count(c["name"]) > 1: c["entry"]["near"] = c["si"]
    return kept
