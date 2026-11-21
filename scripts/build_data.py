"""Build a poster's ride data from fetched Strava data, falling back to GPX per ride.

    python3 scripts/build_data.py <poster>                 # write src/posters/<poster>/rides_data.js
    python3 scripts/build_data.py <poster> --compare-gpx   # compare Strava vs GPX per ride, write nothing

Inputs: src/posters/<poster>/rides.json (rides in chronological order with climbs and places);
data/strava/<id>/ from fetch_strava.py; gpx/<poster>/*.gpx (start-time order) for rides not fetched.
Both are git-ignored. Distance, smoothing, gain, moving time and resampling are the same for either source.
"""
import glob, json, os, re, sys
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
import strava_data as sd
from strava_data import hav

NS = {"g": "http://www.topografix.com/GPX/1/1"}
ROOT = sd.ROOT

def smooth(v, w):
    n = len(v); c = [0.0]
    for x in v: c.append(c[-1]+x)
    return [(c[min(n, i+w+1)]-c[max(0, i-w)])/(min(n, i+w+1)-max(0, i-w)) for i in range(n)]

def gpx_rides(poster):
    """GPX files of a poster in start-time order: [(name, pts)], pts = [(lat, lon, ele, datetime)]."""
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

def resolve_labels(ride, pts, activity=None, log=print):
    """rides.json "climbs" -> [(label, kind, info)]: kind "range" (info = (start, end)) or "place" (info =
    (index, caption)). Segment climbs use the fetched effort's indices, else their fallback range.
    No "climbs" key: the top 3 suggested climbs (needs fetched data)."""
    efforts = activity.get("segment_efforts", []) if activity else None
    if "climbs" not in ride:
        if not activity:
            log("    no climbs listed and no Strava data to suggest from: none"); return []
        top = sd.suggestions(activity, pts, ride.get("exclude", []))[:3]
        log("    auto climbs: " + (", ".join(f'{c["name"]!r}' for c in top) or "none found"))
        return [(c["entry"]["label"], "range", (c["si"], c["ei"])) for c in top]
    out = []
    for c in ride["climbs"]:
        if "place" in c:
            if c["place"] == "northernmost":
                im = max(range(len(pts)), key=lambda i: pts[i][0])
            else:
                im = min(range(len(pts)), key=lambda i: hav(pts[i], c["place"]))
            out.append((c["label"], "place", (im, c.get("caption"))))
            continue
        rng = tuple(c["range"]) if "range" in c else None
        if "segment" in c and efforts is not None:
            e, how, note = sd.match_segment(efforts, c["segment"], c.get("near"))
            if e:
                got = (e["start_index"], e["end_index"])
                msg = f'    {c["label"]}: segment {how}' + (f' -> "{e["name"]}"' if how != "exact" else "") + f" {got[0]}–{got[1]}"
                if rng and (rng[0], rng[1] if rng[1] is not None else got[1]) != got: msg += f" (fallback range was {rng[0]}–{rng[1]})"
                if note: msg += f"; {note}"
                if how != "exact" or note or (rng and rng[0] != got[0]): log(msg)
                out.append((c["label"], "range", got)); continue
            log(f'    ! {c["label"]}: no segment effort matches "{c["segment"]}"' + (", using fallback range" if rng else ", skipped"))
        elif "segment" in c and not rng:
            log(f'    ! {c["label"]}: activity not fetched and no fallback range, skipped')
        if rng: out.append((c["label"], "range", rng))
    return out

def ride_entry(ride, name, pts, tz, strip, activity=None, log=print):
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
    for label, kind, info in resolve_labels(ride, pts, activity, log):
        if kind == "place":
            im, caption = info
            lab = dict(name=label, at=round(dist[im]/total, 4), ele=round(es[im], 1), place=True)
            if caption: lab["sub"] = caption
        else:   # summit = highest point in the range; end None = to the end of the ride
            si, ei = info
            ei = len(es)-1 if ei is None else min(ei, len(es)-1)
            im = max(range(si, ei+1), key=lambda i: es[i])
            lab = dict(name=label, at=round(dist[im]/total, 4), ele=round(es[im], 1))
        labels.append(lab)
    if strip: name = strip.sub("", name).strip()
    st = pts[0][3].astimezone(tz)
    return dict(id=ride["id"], name=name, town=ride.get("town") or "", region=ride["region"],
                date=st.strftime("%Y-%m-%d"), dist=round(total, 1), gain=round(gain, 1),
                moving=round(moving), elapsed=round((pts[-1][3]-pts[0][3]).total_seconds()),
                maxEle=round(max(es), 1), minEle=round(min(es), 1), profile=prof, climbs=labels)

def activity_town(activity):
    """The activity's own location fields, often empty."""
    return next((activity.get(k) for k in ("location_city", "location_state", "location_country") if activity.get(k)), "")

def compare(poster, cfg, tz, strip, gpx):
    """Per ride: point counts (stop on mismatch) and every total/summit that changes between GPX and Strava."""
    fmt = lambda v, u: f"{v:,.1f} {u}"
    quiet = lambda *a: None
    rows, a_tot, b_tot = [], {"dist": 0, "gain": 0, "moving": 0}, {"dist": 0, "gain": 0, "moving": 0}
    hi_a, hi_b = (None, -1), (None, -1)
    for k, ride in enumerate(cfg["rides"]):
        s = sd.load(ride["id"])
        if not s: sys.exit(f"ride {k+1} ({ride['id']}) hasn't been fetched; run fetch_strava.py {poster}")
        pts_s = sd.points(*s)
        name_g, pts_g = gpx[k]
        if pts_s is None: sys.exit(f"ride {k+1} ({ride['id']}): Strava streams incomplete (need latlng, altitude, time)")
        if len(pts_s) != len(pts_g):
            sys.exit(f"STOP: ride {k+1} ({ride['id']}) has {len(pts_s)} stream points but {len(pts_g)} GPX trackpoints, so the "
                     "hand-copied climb indices aren't comparable. Nothing written.")
        a = ride_entry(ride, name_g, pts_g, tz, strip, None, quiet)
        b = ride_entry(ride, s[0]["name"], pts_s, tz, strip, s[0], quiet)
        print(f"ride {k+1:2d} {ride['id']}: {len(pts_s)} points in both")
        for key, unit, conv in (("dist", "mi", 1/1609.344), ("gain", "ft", 3.28084), ("moving", "min", 1/60)):
            va, vb = a[key]*conv, b[key]*conv
            a_tot[key] += a[key]; b_tot[key] += b[key]
            if round(va, 1) != round(vb, 1):
                pct = (vb-va)/va*100 if va else 0
                print(f"   {key:7s} {fmt(va, unit)} -> {fmt(vb, unit)} ({pct:+.2f}%)" + ("  <-- over 2%" if abs(pct) > 2 else ""))
        la, lb = {l["name"]: l for l in a["climbs"]}, {l["name"]: l for l in b["climbs"]}
        for n in sorted(set(la) | set(lb), key=lambda n: (la.get(n) or lb[n])["at"]):
            if n not in la or n not in lb:
                print(f"   label {n!r}: only in {'Strava' if n in lb else 'GPX'} build"); continue
            ea, eb = la[n]["ele"]*3.28084, lb[n]["ele"]*3.28084
            if round(ea) != round(eb) or la[n]["at"] != lb[n]["at"]:
                pct = (eb-ea)/ea*100
                print(f"   {n}: {ea:,.0f} ft at {la[n]['at']} -> {eb:,.0f} ft at {lb[n]['at']} ({pct:+.2f}%)" + ("  <-- over 2%" if abs(pct) > 2 else ""))
            if not la[n].get("place") and la[n]["ele"] > hi_a[1]: hi_a = (n, la[n]["ele"])
            if not lb[n].get("place") and lb[n]["ele"] > hi_b[1]: hi_b = (n, lb[n]["ele"])
    h = lambda s: f"{int(s//3600)}h {round(s%3600/60):02d}m"
    print(f"\ntotals  GPX -> Strava\n  distance {a_tot['dist']/1609.344:,.1f} mi -> {b_tot['dist']/1609.344:,.1f} mi"
          f"\n  gain     {a_tot['gain']*3.28084:,.0f} ft -> {b_tot['gain']*3.28084:,.0f} ft"
          f"\n  moving   {h(a_tot['moving'])} -> {h(b_tot['moving'])}"
          f"\n  high pt  {hi_a[0]} {hi_a[1]*3.28084:,.0f} ft -> {hi_b[0]} {hi_b[1]*3.28084:,.0f} ft")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1: sys.exit(__doc__)
    poster = args[0]
    cfg = json.load(open(os.path.join(ROOT, "src", "posters", poster, "rides.json"), encoding="utf-8"))
    tz = ZoneInfo(cfg["tz"])
    strip = re.compile(cfg["stripName"]) if cfg.get("stripName") else None
    fetched = [sd.load(r["id"]) for r in cfg["rides"]]
    gpx = None
    if "--compare-gpx" in sys.argv or not all(fetched):
        gpx = gpx_rides(poster)
        if len(gpx) != len(cfg["rides"]):
            missing = sum(1 for f in fetched if not f)
            sys.exit(f"{missing} ride(s) not fetched from Strava, so GPX is needed, but gpx/{poster}/ has {len(gpx)} "
                     f"files for {len(cfg['rides'])} rides. Run fetch_strava.py {poster}, or add the GPX files.")
    if "--compare-gpx" in sys.argv:
        return compare(poster, cfg, tz, strip, gpx)

    rides = []
    for k, (ride, s) in enumerate(zip(cfg["rides"], fetched)):
        pts = sd.points(*s) if s else None
        if pts:
            name, src, activity = s[0]["name"], "strava", s[0]
            if not ride.get("town"): ride = dict(ride, town=activity_town(activity))
        else:
            if s: print(f"  ! ride {k+1}: Strava streams incomplete, using GPX")
            name, pts = gpx[k]; src, activity = "gpx", None
        print(f"{k+1:2d} [{src:6s}] {name[:40]}")
        e = ride_entry(ride, name, pts, tz, strip, activity)
        rides.append(e)
        print("     " + (", ".join(f'{l["name"]} {round(l["ele"]*3.28084):,} ft' for l in e["climbs"]) or "(no labels)"))

    out = os.path.join(ROOT, "src", "posters", poster, "rides_data.js")
    open(out, "w", encoding="utf-8").write("const RIDES = " + json.dumps(rides, separators=(",", ":"), ensure_ascii=False) + ";\n")
    print(os.path.getsize(out), "bytes ->", os.path.relpath(out, ROOT))

if __name__ == "__main__":
    main()
