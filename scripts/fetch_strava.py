"""Fetch Strava activities (with all segment efforts) and their streams for the rides in rides.json.

    python3 scripts/fetch_strava.py [poster ...] [--refresh]     # no poster = every poster

For each activity id in src/posters/<poster>/rides.json writes
    data/strava/<id>/activity.json   GET /activities/<id>?include_all_efforts=true
    data/strava/<id>/streams.json    GET /activities/<id>/streams?keys=time,distance,latlng,altitude,moving&key_by_type=true
Already-fetched ids are skipped unless --refresh. data/strava/ is git-ignored (streams hold GPS tracks).
Run scripts/strava_auth.py once first.
"""
import argparse, json, os, sys
import strava_client as sc

DATA = os.path.join(sc.ROOT, "data", "strava")
STREAM_KEYS = "time,distance,latlng,altitude,moving"

def write_json(path, obj):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f)
    os.replace(tmp, path)   # atomic: an interrupted fetch never leaves a half-written file behind

def posters():
    base = os.path.join(sc.ROOT, "src", "posters")
    return sorted(d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, "rides.json")))

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("posters", nargs="*", help="poster folder names (default: all)")
    ap.add_argument("--refresh", action="store_true", help="fetch again even if already downloaded")
    args = ap.parse_args()
    names = args.posters or posters()
    for p in names:
        if p not in posters(): sys.exit(f"No src/posters/{p}/rides.json")
    fetched = skipped = 0
    for p in names:
        ids = [r["id"] for r in json.load(open(os.path.join(sc.ROOT, "src", "posters", p, "rides.json"), encoding="utf-8"))["rides"]]
        print(f"{p}: {len(ids)} activities")
        for rid in ids:
            d = os.path.join(DATA, str(rid))
            act_path, st_path = os.path.join(d, "activity.json"), os.path.join(d, "streams.json")
            if not args.refresh and os.path.exists(act_path) and os.path.exists(st_path):
                skipped += 1; print(f"  {rid}: cached"); continue
            os.makedirs(d, exist_ok=True)
            act = sc.get(f"/activities/{rid}", {"include_all_efforts": "true"})
            streams = sc.get(f"/activities/{rid}/streams", {"keys": STREAM_KEYS, "key_by_type": "true"})
            write_json(act_path, act); write_json(st_path, streams)
            fetched += 1
            n = len(streams.get("time", {}).get("data", []))
            missing = [k for k in STREAM_KEYS.split(",") if k not in streams]
            print(f"  {rid}: {act.get('name', '')[:50]!s} — {n} points, {len(act.get('segment_efforts', []))} segment efforts"
                  + (f", missing streams: {', '.join(missing)}" if missing else ""))
    print(f"done: {fetched} fetched, {skipped} cached. {sc.usage_line()}")

if __name__ == "__main__":
    try:
        main()
    except sc.StravaError as e:
        sys.exit(str(e))
    except KeyboardInterrupt:
        sys.exit("interrupted (completed activities are kept; run again to continue)")
