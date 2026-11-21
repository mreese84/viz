# Ride Posters

A gallery of single-page D3 posters, one per cycling trip: each trip drawn as a circular (radial) elevation profile, ride after ride, in the spirit of race-route posters.

- `italy-2024`: Il Giro d’Italia di Marco, 12 rides in Italy (June–July 2024). Italian flavour text.
- `new-mexico-2018`: La Vuelta a Nuevo México, 3 rides out of Albuquerque (September 2018). Spanish flavour text.

## Build

```
python3 scripts/strava_auth.py                  # once: OAuth for your Strava account (needs .env)
python3 scripts/fetch_strava.py [poster]        # rides.json ids -> data/strava/<id>/ (cached; --refresh to redo)
python3 scripts/suggest_climbs.py <activity id> # ranked climb suggestions as rides.json entries
python3 scripts/build_data.py <poster>          # data/strava (or gpx/ fallback) -> src/posters/<poster>/rides_data.js
python3 scripts/assemble.py                     # all posters + gallery -> dist/
```

Each `src/posters/<poster>/rides_data.js` is committed and holds everything its page needs, so day-to-day page changes only need `assemble.py`. `build_data.py` is only for when ride data or labels change.

Not in the repo (git-ignored): `.env` (Strava app id and secret; template in `.env.example`), `.strava_tokens.json` (OAuth tokens, owner-only), `data/strava/` (fetched activities and streams) and `gpx/` (GPX exports). Streams and GPX hold full GPS tracks; never commit them. Strava auth and fetch need a browser and your secrets, so they run on your computer (the cloud container can't reach strava.com).

Per ride, `build_data.py` uses the fetched Strava streams when present and otherwise the GPX file. GPX files are matched to rides by start-time order, so if any ride isn't fetched, `gpx/<poster>/` must hold the complete set (it refuses a count mismatch). Both sources go through the same maths: distance from lat/lng (haversine), 9-point smoothed elevation, gain with 1.5 m hysteresis, moving time (speed > 0.9 m/s, gaps ≤ 30 s), ~30 samples/mile. Strava's own `distance` and `moving` streams are fetched but not used, so totals stay comparable.

`python3 scripts/build_data.py <poster> --compare-gpx` (needs both sources) checks each ride's stream length against its GPX point count, stops on any mismatch (climb indices wouldn't be comparable), and lists every total and summit that changes, flagging anything over 2%. It writes nothing.

`dist/` is generated and git-ignored; run `assemble.py`, then open `dist/index.html` (gallery) or `dist/<poster>/index.html` in a browser. Posters load D3 7.9 from cdnjs and fonts from Google Fonts; everything else is inline. The gallery needs no JavaScript. Python 3.9+ standard library only (zoneinfo needs tz data, present on macOS/Linux).

## Deploy

GitHub Pages, via `.github/workflows/pages.yml`: https://mreese84.github.io/viz/ (gallery), posters at `/viz/<poster>/`.

- `dist/` is not committed. Every pull request and push to `main` builds it with `assemble.py` (a broken config or data file fails the build).
- A push to `main` (or a manual run on `main`) then publishes the built `dist/` as the site. Nothing else deploys. Commits from the gallery's "Add poster" page are pushes to `main`, so they deploy the same way.
- Repo setting this relies on: Settings → Pages → Source = "GitHub Actions" (which also restricts the `github-pages` environment to `main`).

## Layout

- `gpx/<poster>/` — local only, git-ignored: Strava GPX exports, one per ride (1-second points with time and elevation). Fallback for rides not fetched from the API.
- `data/strava/<id>/activity.json`, `streams.json` — local only, git-ignored: fetched by `fetch_strava.py`.
- `src/posters/<poster>/config.json` — the page: text, language, themes, elevation scale (see below).
- `src/posters/<poster>/rides.json` — the data inputs: rides, climbs, places (see below).
- `src/posters/<poster>/rides_data.js` — built ride data (`const RIDES = [...]`).
- `src/template.html` — the poster page, shared by all posters. `__TITLE__` and `/*__DATA__*/` are filled in by `assemble.py` (`const RIDES = …; const POSTER = <config.json>;`).
- `src/gallery.html` — the gallery page; `<!--__CARDS__-->` becomes one card per poster, newest trip first.
- `scripts/strava_client.py` — `.env`, token storage and refresh, rate-limited GET (prints usage from `X-RateLimit-*`/`X-ReadRateLimit-*`, waits for the next 15-minute window on 429, stops if the daily limit is used up). Never prints secrets or tokens. `STRAVA_API_BASE`/`STRAVA_OAUTH_BASE` exist only for testing against a local fake.
- `scripts/strava_auth.py` — one-time OAuth: opens Strava's consent page (scope `read,activity:read_all`), catches the redirect on `http://localhost:8721/callback` (`--port` to change; the Strava app's callback domain must be `localhost`).
- `scripts/fetch_strava.py` — `GET /activities/{id}?include_all_efforts=true` and `/activities/{id}/streams?keys=time,distance,latlng,altitude,moving&key_by_type=true` per ride.
- `scripts/strava_data.py` — reading fetched data, segment-name matching, climb suggestions (shared by build and suggest).
- `scripts/suggest_climbs.py` — uphill efforts (grade ≥ 2%, ≥ 20 m gain) ranked by climb category then gain; pieces of one climb merged (overlapping efforts where one lies inside the other, or whose tops are within 500 m along the ride); top 5 printed as rides.json entries (`--all` for every one).
- `scripts/build_data.py` — builds `rides_data.js` from Strava streams or GPX (see Build), placing summit and place labels.
- `scripts/assemble.py` — writes `dist/` from scratch (it deletes the old one): `dist/<poster>/index.html` per poster and `dist/index.html`. Gallery thumbnails are radial silhouettes drawn in Python from each poster's data, in its default theme and relief, so they never go stale.
- `dist/` — built output, git-ignored; CI builds it and GitHub Pages serves it.

## Poster config (src/posters/<poster>/config.json)

- `title`, `summary` (gallery card), `ariaLabel`, `storageKey` (localStorage key for theme/units/relief; keep it stable once published).
- `lang`: flavour language for the poster — `it`, `es` or `en` (`LOCALES` in the template: month names, date range, start/finish words, default place caption). UI and stats labels stay English everywhere.
- `disc`: centre-disc text — `kicker`, `title`, `subtitle`, `quote` (1–3 hand-broken lines; the block re-centres), `cite`. `flag`: stripe colours above the kicker.
- `headline`: the boxed line under the stats; `{rides}` and `{regions}` are replaced with counts.
- `elevation`: `minM` = elevation at the profile base (0 for Italy; just under the trip's low point for high-altitude trips), `topFt`/`topM` = the outer edge, `ringsFt`/`ringsM` = dashed rings. `defaultRelief`: `sqrt` (Enhanced) or `linear` (True scale).
- `themes` (presets with the 20 colour tokens; `r1…rN` = one per region in order of appearance) and `defaultTheme`.

## Ride inputs (src/posters/<poster>/rides.json)

- `tz` (local dates), `stripName` (regex removed from Strava titles, e.g. a "Day 2:" prefix, or null).
- `rides`, in chronological order: `id` (Strava activity), `region`, optional `town` (hover readout; falls back to the activity's location fields, which are often empty), optional `exclude` (segment names never auto-suggested), and `climbs`.
- `climbs` entries, drawn in list order (put places first to keep their label order):
  - `{"label", "segment": "<Strava segment name>", "near"?: index, "range"?: [start, end|null]}` — uses that effort's start/end index. Names match exactly, then ignoring case/whitespace, then by closest name; build prints any non-exact match. `near` picks among several efforts with the same name (closest start). `range` is the fallback when the activity hasn't been fetched (Italy's are the old hand-copied indices).
  - `{"label", "range": [start, end|null]}` — manual range of trackpoint/stream indices (they're the same thing); `null` end = to the end of the ride.
  - `{"label", "place": "northernmost" | [lat, lon], "caption"?}` — a town label at the northernmost or nearest point; default caption is the language's word for town.
  - The label always sits at the highest (smoothed) point in its range.
  - No `climbs` key at all: the top 3 suggestions (needs fetched data). `"climbs": []` means no labels.

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

## Adding a poster or a ride

1. Once per computer: create a Strava API app (callback domain `localhost`), copy `.env.example` to `.env` with its client id and secret, and run `python3 scripts/strava_auth.py`.
2. Add the activity ids to `src/posters/<poster>/rides.json` in chronological order, with `region` (and `town` if you want one). For a new poster also create `config.json` (copy an existing one): text, `lang`, themes, `elevation` range.
3. `python3 scripts/fetch_strava.py <poster>`.
4. `python3 scripts/suggest_climbs.py <id>` for each ride and paste the entries you want into its `climbs` (or leave `climbs` out for the top 3). Only name places you can confirm the route passes.
5. `python3 scripts/build_data.py <poster>`, then `python3 scripts/assemble.py`, and commit `rides.json` and `rides_data.js`. The gallery picks up a new poster automatically.

## Conventions

- Poster flavour text follows the trip's language (Italian for Italy, Spanish for New Mexico): dates ("8 giu", "13 sep"), start/finish, disc text. UI and stats labels are English.
- Distances/elevations are computed from the raw points and differ slightly from Strava's own totals (e.g. Joy 1,231 ft vs Strava 1,204 ft); recorded elevations can also sit below a summit's surveyed height (Sandia Crest reads 10,323 ft vs 10,678 ft). That's expected.
