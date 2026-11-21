# Ride Posters

A gallery of single-page D3 posters, one per cycling trip: each trip drawn as a circular (radial) elevation profile, ride after ride, in the spirit of race-route posters.

- `italy-2024`: Il Giro d’Italia di Marco, 12 rides in Italy (June–July 2024). Italian flavour text.
- `new-mexico-2018`: La Vuelta a Nuevo México, 3 rides out of Albuquerque (September 2018). Spanish flavour text.

## Build

```
python3 scripts/build_data.py <poster>   # gpx/<poster>/*.gpx -> src/posters/<poster>/rides_data.js (only when ride data changes)
python3 scripts/assemble.py              # all posters + gallery -> dist/
```

`gpx/` is git-ignored and not in the repo (the raw tracks hold full GPS coordinates). Each `src/posters/<poster>/rides_data.js` is committed and holds everything its page needs, so day-to-day changes only need `assemble.py`. To regenerate a poster's data, put all of its GPX files back in `gpx/<poster>/` first; `build_data.py` matches files to the config's rides by start-time order, so it needs the complete set (it refuses a count mismatch).

Open `dist/index.html` (gallery) or `dist/<poster>/index.html` in a browser. Posters load D3 7.9 from cdnjs and fonts from Google Fonts; everything else is inline. The gallery needs no JavaScript. Python 3.9+ standard library only (zoneinfo needs tz data, present on macOS/Linux).

## Deploy

GitHub Pages, via `.github/workflows/pages.yml`: https://mreese84.github.io/viz/ (gallery), posters at `/viz/<poster>/`.

- Every pull request and push to `main` re-runs `assemble.py` and fails if anything under `dist/` differs from what's committed (changed, deleted or new files), so always rebuild and commit `dist/` together with `src/` changes.
- A push to `main` (or a manual run on `main`) then publishes `dist/` as the site. Nothing else deploys.
- Repo setting this relies on: Settings → Pages → Source = "GitHub Actions" (which also restricts the `github-pages` environment to `main`).

## Layout

- `gpx/<poster>/` — local only, git-ignored: Strava GPX exports, one per ride (1-second points with time and elevation).
- `src/posters/<poster>/config.json` — everything poster-specific (see below).
- `src/posters/<poster>/rides_data.js` — built ride data (`const RIDES = [...]`).
- `src/template.html` — the poster page, shared by all posters. `__TITLE__` and `/*__DATA__*/` are filled in by `assemble.py` (`const RIDES = …; const POSTER = <config without "build">;`).
- `src/gallery.html` — the gallery page; `<!--__CARDS__-->` becomes one card per poster, newest trip first.
- `scripts/build_data.py` — parses GPX: haversine distance, 9-point smoothed elevation, gain with 1.5 m hysteresis, moving time (speed > 0.9 m/s, gaps ≤ 30 s), profile resampled to ~30 points/mile, summit and place labels.
- `scripts/assemble.py` — writes `dist/` from scratch (it deletes the old one): `dist/<poster>/index.html` per poster and `dist/index.html`. Gallery thumbnails are radial silhouettes drawn in Python from each poster's data, in its default theme and relief, so they never go stale.
- `dist/` — built output, committed; this is what GitHub Pages serves.

## Poster config (src/posters/<poster>/config.json)

- `title`, `summary` (gallery card), `ariaLabel`, `storageKey` (localStorage key for theme/units/relief; keep it stable once published).
- `lang`: flavour language for the poster — `it`, `es` or `en` (`LOCALES` in the template: month names, date range, start/finish words, default place caption). UI and stats labels stay English everywhere.
- `disc`: centre-disc text — `kicker`, `title`, `subtitle`, `quote` (1–3 hand-broken lines; the block re-centres), `cite`. `flag`: stripe colours above the kicker.
- `headline`: the boxed line under the stats; `{rides}` and `{regions}` are replaced with counts.
- `elevation`: `minM` = elevation at the profile base (0 for Italy; just under the trip's low point for high-altitude trips), `topFt`/`topM` = the outer edge, `ringsFt`/`ringsM` = dashed rings. `defaultRelief`: `sqrt` (Enhanced) or `linear` (True scale).
- `themes` (presets with the 20 colour tokens; `r1…rN` = one per region in order of appearance) and `defaultTheme`.
- `build`: only for `build_data.py` — `tz` (local dates), `stripName` (regex removed from Strava titles, e.g. a "Day 2:" prefix), and `rides` in chronological order: `id` (Strava activity), `town` (hover readout), `region`, `climbs` and `places`.
  - `climbs`: `[label, start_index, end_index]`, indices are GPX trackpoint indices (= Strava segment-effort stream indices); the label sits at the highest point in that range; `end_index` null = to the end of the ride.
  - `places`: `[name, "north"]` (northernmost point) or `[name, lat, lon]` (nearest point), optionally followed by a caption (e.g. "pueblo"); default caption is the language's word for town.

## Page internals (src/template.html)

- SVG viewBox 1200×H (H = 1600 for 4 rows of the ride list, shorter for fewer), centre (600,600). Radii in the `R` object; angle 0 = top, clockwise, proportional to cumulative distance (`ang()`).
- `TOKENS` (20 colour slots, region slots named from the data). Users override per token; state persists in localStorage under the poster's `storageKey`. A saved theme that no longer exists falls back to the default theme, keeping units and relief.
- `render()` rebuilds the whole SVG on any change (theme, units, relief). Colours are written as attributes, not CSS vars, so SVG/PNG export keeps them.
- Fonts are loaded explicitly (`FACES`, `document.fonts.load`) before the first `render()`, because label fitting measures text; `document.fonts.ready` alone can resolve before an unused weight is fetched, which made titles measure too wide.
- Elevation scale: `sc(v)` maps height above `elevation.minM` to radius (square root for Enhanced, linear for True scale).
- Each ride has a backing wedge in the profile zone, alternating between two opacities of the `text` colour so neighbouring rides read apart in every theme.
- Region band: one segment per run of rides with the same region; a single region becomes a full ring labelled at the bottom. Italy's region colours (r1–r3) were checked with a colour-vision validator (adjacent-pair ΔE ≥ 15 normal vision, ≥ 8 under CVD simulation). Keep adjacent regions separated if you change them; region names are printed on the band as secondary encoding.
- Zoom: d3.zoom on `.zoomable`, scale 1–10. Wheel zoom only with Ctrl/⌘ (trackpad pinch), one-finger touch scrolls the page until zoomed. Fine lines use `vector-effect: non-scaling-stroke`. Export strips the zoom transform.
- Ride band titles: tried as `n · name · date` at 12px, then `n · name` at 12/11/10px. If none fit, the band shows just the number and the full title goes in an outer label (bracket over the ride's span, title just beyond the distance labels). Neighbouring overflowing rides sit side by side.
- Ride list below the poster: 3 columns for 6+ rides, otherwise one wide column; full name with stats on a second line; an over-long name is condensed (`textLength`), never cut.
- Climb labels: radial text, simple 1-D collision relaxation (`minSep`), flipped on the left half.
- Hover: annulus hit-area → ride, distance, elevation and grade (±150 m window). On touch screens a tap shows the readout and it stays until you tap elsewhere.
- Phones (≤ 600px wide, CSS only): the poster comes first and runs edge to edge, the zoom buttons sit under it instead of over its top-right corner, and the controls follow below (theme chips on one row; the "Theme" label drops below 358px). The help note has a mouse and a touch wording (`.note.mouse` / `.note.touch`, switched on `hover:none`).

## Adding a poster

1. Export each ride's GPX from strava.com (⋯ → Export GPX) into `gpx/<poster>/`.
2. Create `src/posters/<poster>/config.json` (copy an existing one): text, `lang`, themes, `elevation` range, and `build.rides` in chronological order.
3. Climb labels need trackpoint index ranges. Italy's came from the Strava activity page's embedded segment-effort JSON (`start_index`, `end_index`), which requires a logged-in session; otherwise pick ranges from the elevation profile (find the high point's index in the GPX). Only name places you can confirm the route passes.
4. `python3 scripts/build_data.py <poster>`, then `python3 scripts/assemble.py`. The gallery picks the new poster up automatically.

## Conventions

- Poster flavour text follows the trip's language (Italian for Italy, Spanish for New Mexico): dates ("8 giu", "13 sep"), start/finish, disc text. UI and stats labels are English.
- Distances/elevations are computed from GPX and differ slightly from Strava's own totals (e.g. Joy 1,231 ft vs Strava 1,204 ft); recorded elevations can also sit below a summit's surveyed height (Sandia Crest reads 10,323 ft vs 10,678 ft). That's expected.
