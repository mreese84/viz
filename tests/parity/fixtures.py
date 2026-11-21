"""Synthetic Strava activities for the parity check (no real rides: made-up coordinates and terrain)."""
import math
from datetime import datetime, timedelta, timezone

def _lcg(seed):
    x = seed
    while True:
        x = (1103515245 * x + 12345) % 2**31
        yield x / 2**31

def ride(seed, n, start, lat0=45.0, lon0=7.0):
    """n points ~1 s apart moving ~6–9 m/s with hills, a stop, a GPS gap, and noisy elevation."""
    r = _lcg(seed)
    lat, lon, t = lat0, lon0, 0
    ll, alt, tt = [], [], []
    for i in range(n):
        if i and n//3 <= i < n//3 + 40:      # stopped at a cafe: time passes, no movement
            t += 1
        elif i == n//2:                        # a 45-second recording gap
            t += 45; lat += 0.0005
        else:
            t += 1; step = (6 + 3*next(r)) / 111_000
            lat += step*math.cos(i/700); lon += step*math.sin(i/700)
        e = 300 + 250*math.sin(i/(n/3)) + 120*math.sin(i/(n/11)) + 4*next(r)
        ll.append([round(lat, 7), round(lon, 7)]); alt.append(round(e, 1)); tt.append(t)
    streams = {"latlng": {"data": ll}, "altitude": {"data": alt}, "time": {"data": tt},
               "distance": {"data": [0]*n}, "moving": {"data": [True]*n}}
    return {"start_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "timezone": "(GMT+01:00) Europe/Rome", "name": f"Test ride {seed}"}, streams

def effort(name, si, ei, cat, grade):
    return {"name": name, "start_index": si, "end_index": ei, "segment": {"climb_category": cat, "average_grade": grade}}

def cases():
    t0 = datetime(2024, 6, 8, 22, 30, tzinfo=timezone.utc)   # 00:30 next day in Rome: local-date check
    a1, s1 = ride(1, 4000, t0)
    a1["segment_efforts"] = [effort("Big climb", 300, 1600, 3, 6), effort("Big climb top", 1200, 1600, 2, 7),
                             effort("Big climb", 2600, 3300, 1, 5),           # same name twice
                             effort("Little Kicker", 3400, 3700, 0, 4), effort("Downhill", 1600, 2200, 0, -5)]
    a2, s2 = ride(2, 3000, t0 + timedelta(days=1), 45.3, 7.4)
    a2["segment_efforts"] = [effort("Col  de  Test", 200, 1400, 4, 7), effort("Wall", 1900, 2100, 1, 9), effort("Sprint", 2500, 2560, 0, 1)]
    a3, s3 = ride(3, 2500, t0 + timedelta(days=2), 44.8, 6.9)
    a3["segment_efforts"] = [effort("Ridge A", 100, 900, 2, 5), effort("Ridge A lower", 100, 500, 1, 5), effort("Ridge B", 1500, 2300, 2, 4)]
    rides = [
        ({"id": 1, "region": "Test North", "town": "Testville",
          "climbs": [{"label": "North tip", "place": "northernmost"},
                     {"label": "Big climb", "segment": "Big climb", "near": 2600, "range": [2600, 3300]},
                     {"label": "Top", "segment": "Big climb top"},
                     {"label": "Kicker", "segment": "little  kicker"},            # normalized match
                     {"label": "Gone", "segment": "No such segment", "range": [3700, None]},
                     {"label": "Far", "place": [45.02, 7.03], "caption": "village"}]}, a1, s1),
        ({"id": 2, "region": "Test South"}, a2, s2),                                # no climbs key: auto top 3
        ({"id": 3, "region": "Test South", "town": "", "exclude": ["Ridge A"]}, a3, s3),
    ]
    return rides
