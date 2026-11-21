"""Suggest climb labels for a fetched ride from its Strava segment efforts.

    python3 scripts/suggest_climbs.py <activity id> [--all]

Ranks uphill efforts (average grade >= 2%, at least 20 m of climbing) by climb category, then elevation gain,
merges pieces of the same climb (one effort inside another, or tops within 500 m), and prints the top 5 (--all: every one) as ready-to-paste
rides.json "climbs" entries. A ride with no "climbs" key in rides.json gets the top 3 automatically.
Run fetch_strava.py first.
"""
import glob, json, os, sys
import strava_data as sd

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or not args[0].isdigit(): sys.exit(__doc__)
    rid = int(args[0])
    s = sd.load(rid)
    if not s: sys.exit(f"Activity {rid} hasn't been fetched. Add it to a rides.json and run fetch_strava.py.")
    activity, streams = s
    pts = sd.points(activity, streams)
    if not pts: sys.exit("Its streams are incomplete (need latlng, altitude, time).")
    # honour the ride's "exclude" list if the id is in a poster's rides.json
    exclude = []
    for f in glob.glob(os.path.join(sd.ROOT, "src", "posters", "*", "rides.json")):
        for r in json.load(open(f, encoding="utf-8"))["rides"]:
            if r["id"] == rid: exclude = r.get("exclude", [])
    sugg = sd.suggestions(activity, pts, exclude)
    shown = sugg if "--all" in sys.argv else sugg[:5]
    n_eff = len(activity.get("segment_efforts", []))
    print(f"{activity.get('name', rid)}: {n_eff} segment efforts, {len(sugg)} distinct uphill climbs"
          + (f", {len(exclude)} excluded by name" if exclude else ""))
    if not shown: return
    w = max(len(c["name"]) for c in shown)
    for i, c in enumerate(shown, 1):
        print(f"  {i}. {c['name']:<{w}}  {sd.CATEGORY.get(c['cat'], c['cat']):>6}  +{c['gain']:,.0f} m  "
              f"summit {c['summit_ele']*3.28084:,.0f} ft  idx {c['si']}–{c['ei']}")
    print('\nPaste into the ride\'s "climbs" list (edit the labels):')
    print(",\n".join("  " + json.dumps(c["entry"], ensure_ascii=False) for c in shown))

if __name__ == "__main__":
    main()
