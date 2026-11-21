// Ride maths for the browser: a line-for-line mirror of scripts/build_data.py (ride_entry, resolve_labels)
// and scripts/strava_data.py (points, match_segment, suggestions). tests/parity checks that both produce the
// same ride data from the same Strava data, so change them together.
//
// Points are [lat, lon, ele, tMillis].

export const SCOPE = "read,activity:read_all";
const R_EARTH = 6371008.8;
const rad = d => d * Math.PI / 180;

export function hav(a, b) {
  const la1 = rad(a[0]), lo1 = rad(a[1]), la2 = rad(b[0]), lo2 = rad(b[1]);
  const d = Math.sin((la2-la1)/2)**2 + Math.cos(la1)*Math.cos(la2)*Math.sin((lo2-lo1)/2)**2;
  return 2*R_EARTH*Math.asin(Math.sqrt(d));
}

export function smooth(v, w) {
  const n = v.length, c = [0];
  for (const x of v) c.push(c[c.length-1] + x);
  return v.map((_, i) => (c[Math.min(n, i+w+1)] - c[Math.max(0, i-w)]) / (Math.min(n, i+w+1) - Math.max(0, i-w)));
}

// Python's round(x, n): correctly rounded, exact ties to even (toFixed rounds exact ties up)
export function pyRound(x, n = 0) {
  const s = x * 10**n;
  if (Math.abs(s % 1) === 0.5) { const f = Math.floor(s); return (f % 2 === 0 ? f : f + 1) / 10**n; }
  return Number(x.toFixed(n));
}

export function points(activity, streams) {
  const ll = streams.latlng?.data, alt = streams.altitude?.data, t = streams.time?.data;
  if (!ll || !alt || !t || !ll.length || ll.length !== alt.length || ll.length !== t.length) return null;
  const t0 = Date.parse(activity.start_date);
  return ll.map(([la, lo], i) => [la, lo, Number(alt[i]), t0 + t[i]*1000]);
}

// IANA zone from Strava's "(GMT-07:00) America/Denver"
export function tzOf(activity) {
  const m = /\)\s*(\S+)$/.exec(activity.timezone || "");
  return m ? m[1] : "UTC";
}

export function localDate(tMillis, tz) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(tMillis));
}

// ---------- Segment names ----------
export const norm = s => s.replace(/\s+/g, " ").trim().toLowerCase();

// Exact, then case/whitespace-normalized. (The Python version also tries the closest fuzzy name; the browser
// only ever offers names taken from the activity itself, so it doesn't need that.)
export function matchSegment(efforts, name, near) {
  let cands = efforts.filter(e => e.name === name), how = "exact";
  if (!cands.length) { cands = efforts.filter(e => norm(e.name) === norm(name)); how = "normalized"; }
  if (!cands.length) return { effort: null, how: "missing", note: "" };
  let note = "";
  if (cands.length > 1) {
    if (near != null) cands = [...cands].sort((a, b) => Math.abs(a.start_index - near) - Math.abs(b.start_index - near));
    else note = `${cands.length} efforts named like this; used the first`;
  }
  return { effort: cands[0], how, note };
}

// ---------- Climb suggestions ----------
export const CATEGORY = { 5: "HC", 4: "Cat 1", 3: "Cat 2", 2: "Cat 3", 1: "Cat 4", 0: "uncat." };
export const SUMMIT_GAP = 500;

export function sameClimb(a, b) {
  if (a.si > b.ei || b.si > a.ei) return false;
  const nested = (a.si <= b.si && b.ei <= a.ei) || (b.si <= a.si && a.ei <= b.ei);
  return nested || Math.abs(a.summit_d - b.summit_d) <= SUMMIT_GAP;
}

export function suggestions(activity, pts, exclude = [], minGrade = 2.0, minGain = 20.0) {
  const excl = new Set(exclude.map(norm));
  const dist = [0];
  for (let i = 1; i < pts.length; i++) dist.push(dist[i-1] + hav(pts[i-1], pts[i]));
  const cands = [];
  for (const e of activity.segment_efforts || []) {
    const seg = e.segment || {};
    const si = e.start_index, ei = Math.min(e.end_index, pts.length - 1);
    if (excl.has(norm(e.name)) || ei <= si || (seg.average_grade ?? 0) < minGrade) continue;
    let top = si;
    for (let i = si; i <= ei; i++) if (pts[i][2] > pts[top][2]) top = i;
    const gain = pts[top][2] - pts[si][2];
    if (gain < minGain) continue;
    cands.push({ effort: e, name: e.name, si, ei, cat: seg.climb_category || 0, gain, summit: top, summit_ele: pts[top][2], summit_d: dist[top] });
  }
  cands.sort((a, b) => (b.cat - a.cat) || (b.gain - a.gain));
  const kept = [];
  for (const c of cands) if (!kept.some(k => sameClimb(k, c))) kept.push(c);
  const names = (activity.segment_efforts || []).map(e => e.name);
  for (const c of kept) {
    c.entry = { label: c.name.trim(), segment: c.name };
    if (names.filter(n => n === c.name).length > 1) c.entry.near = c.si;
  }
  return kept;
}

// ---------- Labels and the ride entry (build_data.py) ----------
export function resolveLabels(ride, pts, activity, log = () => {}) {
  const efforts = activity ? activity.segment_efforts || [] : null;
  if (!("climbs" in ride)) {
    if (!activity) { log("no climbs listed and no Strava data to suggest from: none"); return []; }
    return suggestions(activity, pts, ride.exclude || []).slice(0, 3).map(c => [c.entry.label, "range", [c.si, c.ei]]);
  }
  const out = [];
  for (const c of ride.climbs) {
    if ("place" in c) {
      let im = 0;
      if (c.place === "northernmost") { for (let i = 1; i < pts.length; i++) if (pts[i][0] > pts[im][0]) im = i; }
      else { let best = Infinity; pts.forEach((p, i) => { const d = hav(p, c.place); if (d < best) { best = d; im = i; } }); }
      out.push([c.label, "place", [im, c.caption || null]]);
      continue;
    }
    const rng = c.range ? [c.range[0], c.range[1]] : null;
    if (c.segment && efforts) {
      const m = matchSegment(efforts, c.segment, c.near);
      if (m.effort) { out.push([c.label, "range", [m.effort.start_index, m.effort.end_index]]); continue; }
      log(`${c.label}: no segment effort matches "${c.segment}"` + (rng ? ", using fallback range" : ", skipped"));
    }
    if (rng) out.push([c.label, "range", rng]);
  }
  return out;
}

export function rideEntry(ride, name, pts, tz, strip, activity, log) {
  const dist = [0]; let moving = 0;
  for (let i = 1; i < pts.length; i++) {
    const d = hav(pts[i-1], pts[i]), dt = (pts[i][3] - pts[i-1][3]) / 1000;
    dist.push(dist[i-1] + d);
    if (0 < dt && dt <= 30 && d/dt > 0.9) moving += dt;
  }
  const es = smooth(pts.map(p => p[2]), 4);
  let gain = 0, ref = es[0];
  for (const v of es) { if (v > ref + 1.5) { gain += v - ref; ref = v; } else if (v < ref) ref = v; }
  const total = dist[dist.length-1];
  const N = Math.max(200, Math.trunc(total/1609.344*30));
  const prof = []; let j = 0;
  for (let s = 0; s <= N; s++) {
    const target = total*s/N;
    while (j < dist.length-1 && dist[j+1] < target) j++;
    prof.push(pyRound(es[j], 1));
  }
  const labels = [];
  for (const [label, kind, info] of resolveLabels(ride, pts, activity, log)) {
    if (kind === "place") {
      const [im, caption] = info;
      const lab = { name: label, at: pyRound(dist[im]/total, 4), ele: pyRound(es[im], 1), place: true };
      if (caption) lab.sub = caption;
      labels.push(lab);
    } else {
      const si = info[0], ei = info[1] == null ? es.length-1 : Math.min(info[1], es.length-1);
      let im = si;
      for (let i = si; i <= ei; i++) if (es[i] > es[im]) im = i;
      labels.push({ name: label, at: pyRound(dist[im]/total, 4), ele: pyRound(es[im], 1) });
    }
  }
  if (strip) name = name.replace(strip, "").trim();
  return { id: ride.id, name, town: ride.town || "", region: ride.region, date: localDate(pts[0][3], tz),
           dist: pyRound(total, 1), gain: pyRound(gain, 1), moving: pyRound(moving), elapsed: pyRound((pts[pts.length-1][3] - pts[0][3]) / 1000),
           maxEle: pyRound(Math.max(...es), 1), minEle: pyRound(Math.min(...es), 1), profile: prof, climbs: labels };
}
