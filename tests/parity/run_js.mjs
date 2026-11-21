// Helper for check.py: compute ride entries with the browser's ridemath.js and print them as JSON.
import { readFileSync } from "node:fs";
import { points, rideEntry } from "../../src/new/ridemath.js";
const inp = JSON.parse(readFileSync(process.argv[2], "utf8"));
const strip = new RegExp(inp.strip);
const out = inp.rides.map(([ride, act, st]) => rideEntry(ride, act.name + " — loop", points(act, st), inp.tz, strip, act));
process.stdout.write(JSON.stringify(out));
