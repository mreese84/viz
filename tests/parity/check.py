"""Check that the browser's ride maths (src/new/ridemath.js) gives the same ride data as the Python build
(scripts/build_data.py) for the same Strava data.  Run: python3 tests/parity/check.py  (needs Node 18+)"""
import json, os, re, subprocess, sys, tempfile
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts")); sys.path.insert(0, HERE)
import build_data, strava_data, fixtures

def main():
    rides = fixtures.cases()
    strip = r"^Test ride \d+"   # exercise the name-prefix stripping too
    py = []
    for ride, act, st in rides:
        pts = strava_data.points(act, st)
        py.append(build_data.ride_entry(ride, act["name"] + " — loop", pts, ZoneInfo("Europe/Rome"), re.compile(strip), act, lambda *a: None))
    with tempfile.TemporaryDirectory() as d:
        inp = os.path.join(d, "in.json")
        json.dump({"strip": strip, "tz": "Europe/Rome", "rides": [[r, a, s] for r, a, s in rides]}, open(inp, "w"))
        out = subprocess.run(["node", os.path.join(HERE, "run_js.mjs"), inp], capture_output=True, text=True)
    if out.returncode: sys.exit("node failed:\n" + out.stderr)
    js = json.loads(out.stdout)
    diffs = []
    def cmp(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)): cmp(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{path}.{k}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b): diffs.append(f"{path}: length {len(a)} vs {len(b)}")
            for i, (x, y) in enumerate(zip(a, b)): cmp(x, y, f"{path}[{i}]")
        elif a != b or isinstance(a, bool) != isinstance(b, bool):   # True must not pass for 1
            diffs.append(f"{path}: python {a!r} vs js {b!r}")
    cmp(py, js, "rides")
    for r in py: print(f"  ride {r['id']} {r['date']} {r['name']!r}: {len(r['profile'])} profile points, labels "
                       + ", ".join(f"{l['name']}@{l['at']}" for l in r["climbs"]))
    if diffs:
        print(f"{len(diffs)} differences:"); print("\n".join("  " + x for x in diffs[:40])); sys.exit(1)
    print("parity: Python and JavaScript ride data are identical")

if __name__ == "__main__":
    main()
