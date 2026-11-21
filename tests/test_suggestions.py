"""Climb-suggestion rules (scripts/strava_data.py): ranking, merging pieces of one climb, exclude.
Run: python3 tests/test_suggestions.py"""
import os, sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import strava_data as sd

t0 = datetime(2024, 1, 1)
# points ~10 m apart heading north. Climb 1: idx 0–300 up to 400 m, gentle rise to 404 m at idx 340 (~400 m on),
# descent, flat; Climb 2: idx 600–700 up to ~460 m
ele = [100 + i for i in range(301)] + [400 + (i-300)*0.1 for i in range(301, 341)] + [404 - (i-340)*0.6 for i in range(341, 501)] \
    + [308.0]*99 + [308 + (i-599)*1.5 for i in range(599, 701)] + [459.5]*100
pts = [(45 + i*0.00009, 11.0, e, t0 + timedelta(seconds=i)) for i, e in enumerate(ele)]
def eff(name, si, ei, cat, grade): return {"name": name, "start_index": si, "end_index": ei, "segment": {"climb_category": cat, "average_grade": grade}}
names = lambda act, **kw: [c["name"] for c in sd.suggestions(act, pts, **kw)]

act = {"segment_efforts": [
    eff("Climb 1 full", 0, 300, 2, 8),
    eff("Climb 1 lower stretch", 0, 140, 1, 8),       # nested; own top 1.6 km earlier -> merged
    eff("Climb 1 middle stretch", 100, 250, 0, 9),    # nested -> merged
    eff("Climb 1 to the lookout", 150, 340, 1, 6),    # not nested; top ~400 m past "full"'s -> merged (500 m rule)
    eff("Climb 2", 600, 700, 1, 6),                   # separate climb -> kept
    eff("Descent", 340, 500, 0, -4), eff("Flat", 520, 590, 0, 0.5)]}
assert names(act) == ["Climb 1 full", "Climb 2"], names(act)
# partly overlapping, not nested, tops 3.6 km apart -> different climbs
act2 = {"segment_efforts": [eff("Climb 1 full", 0, 300, 2, 8), eff("Tail into climb 2", 250, 700, 1, 3)]}
assert names(act2) == ["Climb 1 full", "Tail into climb 2"], names(act2)
# exclude (case-insensitive): the next-best stretch of that climb takes its place
got = names(act, exclude=["climb 1 FULL"])
assert got[0].startswith("Climb 1") and "Climb 2" in got, got
# same-named efforts get "near"
act3 = {"segment_efforts": [eff("Repeat", 0, 300, 1, 8), eff("Repeat", 600, 700, 1, 6)]}
entries = [c["entry"] for c in sd.suggestions(act3, pts)]
assert entries == [{"label": "Repeat", "segment": "Repeat", "near": 0}, {"label": "Repeat", "segment": "Repeat", "near": 600}], entries
print("suggestion tests passed")
