# Il Giro d'Italia di Marco

Circular elevation-profile poster of 12 rides in Italy, June–July 2024 (Abruzzo, Trentino-Alto Adige, Toscana).

**Live:** https://mreese84.github.io/viz/

```
python3 scripts/assemble.py
open dist/index.html
```

The ride data is already built in `src/rides_data.js`. The raw GPX tracks are kept out of the repo; to regenerate the data, put the Strava GPX exports in `gpx/` and run `python3 scripts/build_data.py` first.

Themes, units (mi/ft or km/m), relief scale, zoom, and SVG/PNG export are built into the page. See CLAUDE.md for how it works and how to add rides.
