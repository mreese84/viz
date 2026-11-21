# Ride Posters

An experiment in turning cycling data into bespoke artwork: each trip drawn as one circular elevation profile, ride after ride.

**Live:** https://mreese84.github.io/viz/

- [Il Giro d’Italia di Marco](https://mreese84.github.io/viz/italy-2024/): 12 rides in Italy, June–July 2024 (Abruzzo, Trentino-Alto Adige, Toscana).
- [La Vuelta a Nuevo México](https://mreese84.github.io/viz/new-mexico-2018/): 3 rides out of Albuquerque, September 2018.

```
python3 scripts/assemble.py
open dist/index.html
```

Each poster's ride data is already built in `src/posters/<poster>/rides_data.js`. The raw GPX tracks are kept out of the repo; to regenerate a poster's data, put its Strava GPX exports in `gpx/<poster>/` and run `python3 scripts/build_data.py <poster>` first.

Themes, units (mi/ft or km/m), relief scale, zoom, and SVG/PNG export are built into every poster. See CLAUDE.md for how it works and how to add a poster.
