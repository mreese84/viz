# Il Giro d'Italia di Marco

A single-page D3 poster: a circular (radial) elevation profile of 12 bike rides in Italy (June–July 2024), in the spirit of race-route posters.

## Build

```
python3 scripts/build_data.py   # gpx/*.gpx -> src/rides_data.js (only needed when ride data changes)
python3 scripts/assemble.py     # src/template.html + src/rides_data.js -> dist/index.html
```

`gpx/` is git-ignored and not in the repo (the raw tracks hold full GPS coordinates). `src/rides_data.js` is committed and holds everything the page needs, so day-to-day changes to the page only need `assemble.py`. To regenerate the data, re-download all 12 GPX files from Strava into `gpx/` first; `build_data.py` matches files to `META`/`CLIMBS` by start-time order, so it needs the complete set.

Open `dist/index.html` in a browser. It loads D3 7.9 from cdnjs and fonts from Google Fonts; everything else is inline. Python 3.9+ standard library only (zoneinfo needs tz data, present on macOS/Linux).

## Deploy

GitHub Pages, via `.github/workflows/pages.yml`: https://mreese84.github.io/viz/

- Every pull request and push to `main` re-runs `assemble.py` and fails if the committed `dist/index.html` differs, so always rebuild and commit `dist/` together with `src/` changes.
- A push to `main` (or a manual run on `main`) then publishes `dist/` as the site. Nothing else deploys.
- Repo setting this relies on: Settings → Pages → Source = "GitHub Actions" (which also restricts the `github-pages` environment to `main`).

## Layout

- `gpx/` — local only, git-ignored: Strava GPX exports, one per ride (Garmin Edge 820, 1-second points with time and elevation).
- `scripts/build_data.py` — parses GPX: haversine distance, 9-point smoothed elevation, gain with 1.5 m hysteresis, moving time (speed > 0.9 m/s, gaps ≤ 30 s), profile resampled to ~30 points/mile, summit labels.
  - `META`: Strava activity id, base town, region per ride, **in chronological order**.
  - `CLIMBS`: per ride index, `(label, start_index, end_index)`. Indices are Strava segment-effort stream indices (= GPX trackpoint indices); the label sits at the highest point in that range. `end_index=None` means "to the end of the ride".
  - Ride 11 also gets a "Firenze" place label at its northernmost point.
- `src/template.html` — the page. `/*__DATA__*/` is replaced by `const RIDES = [...]`.
- `dist/index.html` — built output, committed; this is what GitHub Pages serves.

## Page internals (src/template.html)

- SVG viewBox 1200×1600, centre (600,600). Radii in the `R` object; angle 0 = top, clockwise, proportional to cumulative distance (`ang()`).
- `THEMES` (6 presets) and `TOKENS` (20 colour slots). Users override per token; state persists in localStorage key `giro-marco-v1`.
- `render()` rebuilds the whole SVG on any change (theme, units, relief). Colours are written as attributes, not CSS vars, so SVG/PNG export keeps them.
- Fonts are loaded explicitly (`FACES`, `document.fonts.load`) before the first `render()`, because label fitting measures text; `document.fonts.ready` alone can resolve before an unused weight is fetched, which made titles measure too wide.
- Each ride has a backing wedge in the profile zone, alternating between two opacities of the `text` colour so neighbouring rides read apart in every theme.
- Region colours (r1–r3) were checked with a colour-vision validator (adjacent-pair ΔE ≥ 15 normal vision, ≥ 8 under CVD simulation). Keep them separated if you change them; region names are printed on the band as secondary encoding.
- Zoom: d3.zoom on `.zoomable`, scale 1–10. Wheel zoom only with Ctrl/⌘ (trackpad pinch), one-finger touch scrolls the page until zoomed. Fine lines use `vector-effect: non-scaling-stroke`. Export strips the zoom transform.
- Ride band titles: tried as `n · name · date` at 12px, then `n · name` at 12/11/10px. If none fit, the band shows just the number and the full title goes in an outer label (bracket over the ride's span, title just beyond the distance labels). Neighbouring overflowing rides sit side by side. Currently only ride 4 overflows.
- Ride list below the poster: 3 columns × 4 rows, full name with stats on a second line; an over-long name is condensed (`textLength`), never cut.
- Climb labels: radial text, simple 1-D collision relaxation (`minSep`), flipped on the left half.
- Hover: annulus hit-area → ride, distance, elevation and grade (±150 m window).

## Adding a ride

1. Export its GPX from strava.com (⋯ → Export GPX) into `gpx/`.
2. Add a `META` row at its chronological position and shift `CLIMBS` keys after it.
3. Climb labels need segment start/end indices. They came from the Strava activity page's embedded segment-effort JSON (`start_index`, `end_index`), which requires a logged-in session; alternatively pick ranges by eye from the elevation profile.
4. If it's in a new region, add a 4th region colour token and theme values.
5. Rebuild.

## Conventions

- Dates and poster flavour text are Italian ("8 giu", "partenza/arrivo"); UI and stats labels are English.
- Distances/elevations are computed from GPX and differ slightly from Strava's own totals (e.g. Joy 1,231 ft vs Strava 1,204 ft). That's expected.
