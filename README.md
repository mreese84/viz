# Ride Posters

An experiment in turning cycling data into bespoke artwork: each trip drawn as one circular elevation profile, ride after ride.

**Live:** https://mreese84.github.io/viz/

- [Il Giro d’Italia di Marco](https://mreese84.github.io/viz/italy-2024/): 12 rides in Italy, June–July 2024 (Abruzzo, Trentino-Alto Adige, Toscana).
- [La Vuelta a Nuevo México](https://mreese84.github.io/viz/new-mexico-2018/): 3 rides out of Albuquerque, September 2018.

```
python3 scripts/assemble.py
open dist/index.html
```

Each poster's ride data is already built in `src/posters/<poster>/rides_data.js`, so changing a page only needs `assemble.py`.

To add rides or regenerate data from Strava (on your own computer):

```
cp .env.example .env                              # fill in your Strava API app's client id and secret
python3 scripts/strava_auth.py                    # once: authorize in the browser
python3 scripts/fetch_strava.py <poster>          # after adding activity ids to src/posters/<poster>/rides.json
python3 scripts/suggest_climbs.py <activity id>   # paste the climbs you want into rides.json
python3 scripts/build_data.py <poster>
python3 scripts/assemble.py
```

Fetched Strava data (`data/strava/`), GPX exports (`gpx/`), `.env` and tokens stay out of the repo: the tracks hold full GPS coordinates. Rides that haven't been fetched fall back to GPX files in `gpx/<poster>/`.

**Add poster from the browser:** the gallery's last card opens a page that turns a list of Strava links into a new poster, prompting for the title, regions, climb labels and colours, with a live preview, and publishes it to the gallery with one commit. One-time setup: deploy the small Strava login Worker (see [`workers/strava-auth/README.md`](workers/strava-auth/README.md)) and put its address in `src/site.json`.

Themes, units (mi/ft or km/m), relief scale, zoom, and SVG/PNG export are built into every poster. See CLAUDE.md for how it works and how to add a poster.
