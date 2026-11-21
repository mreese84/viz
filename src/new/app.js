// "Add a poster": Strava links -> prompts -> preview -> one commit to the repo (GitHub Actions then builds the site).
// Ride maths come from ridemath.js (a mirror of the Python build, kept identical by tests/parity).
import { points, rideEntry, suggestions, tzOf, CATEGORY } from "./ridemath.js";

const $ = id => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k in e && k !== "list") e[k] = v; else e.setAttribute(k, v); }
  for (const k of kids) e.append(k);
  return e;
};
const store = {   // localStorage can be unavailable (private mode); never let that break the page
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};
const draft = {
  get() { try { return JSON.parse(sessionStorage.getItem("viz-new-draft")) || {}; } catch { return {}; } },
  set(v) { try { sessionStorage.setItem("viz-new-draft", JSON.stringify(v)); } catch {} },
  clear() { try { sessionStorage.removeItem("viz-new-draft"); } catch {} },
};
const msg = (id, text, kind = "") => { const m = $(id); m.textContent = text; m.className = "msg " + kind; };

const MONTHS = {
  en: ["January","February","March","April","May","June","July","August","September","October","November","December"],
  it: ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"],
  es: ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"],
};
const RIDES_WORD = { en: "RIDES", it: "CORSE", es: "ETAPAS" };
const FLAGS = { "Italy": ["#009246","#f4f5f0","#ce2b37"], "New Mexico": ["#ffd200","#bf0a30","#ffd200"], "France": ["#0055a4","#ffffff","#ef4135"],
                "Spain": ["#aa151b","#f1bf00","#aa151b"], "United States": ["#b22234","#ffffff","#3c3b6e"], "Germany": ["#000000","#dd0000","#ffce00"] };
const REGION_FALLBACK = ["#a68d2a", "#4f8fca", "#de6a3a", "#5f9a55", "#9a62b8", "#c4546e"];
const DEFAULT_THEMES = ["Maglia Rosa", "Turquesa", "Adobe"];
const KEY_STRAVA = "viz-strava-tokens", KEY_GH = "viz-github-token";

let SITE = {}, PRESETS = { themes: {}, slugs: [] }, TEMPLATE = "";
let RIDES = [];          // [{id, act, streams, pts, base}] in date order
const dirty = new Set(); // prefilled fields the user has edited (stop auto-updating them)

// ---------- Strava (through the Worker) ----------
class NeedLogin extends Error {}
function stravaLogin() {
  saveDraft({ pendingFetch: true });
  location.href = SITE.stravaWorker + "/auth/start?return=" + encodeURIComponent(location.href.split("#")[0]);
}
async function stravaToken() {
  let t = store.get(KEY_STRAVA);
  if (!t) throw new NeedLogin();
  if (t.expires_at - 60 < Date.now() / 1000) {
    const r = await fetch(SITE.stravaWorker + "/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" },
                                                                body: JSON.stringify({ refresh_token: t.refresh_token }) });
    if (!r.ok) { store.del(KEY_STRAVA); throw new NeedLogin(); }
    t = { ...t, ...(await r.json()) }; store.set(KEY_STRAVA, t);
  }
  return t.access_token;
}
async function sget(path, params) {
  const r = await fetch(SITE.stravaWorker + "/api" + path + (params ? "?" + new URLSearchParams(params) : ""),
                        { headers: { Authorization: "Bearer " + await stravaToken() } });
  if (r.status === 401) { store.del(KEY_STRAVA); throw new NeedLogin(); }
  if (r.status === 404) throw new Error("not found (wrong link, or not your activity?)");
  if (r.status === 429) throw new Error("Strava's rate limit is used up; try again in 15 minutes");
  if (!r.ok) throw new Error(`Strava returned ${r.status}`);
  return r.json();
}

// ---------- Draft (survives the trip to Strava's login page) ----------
const FIELDS = ["links", "f-title", "f-slug", "f-lang", "f-kicker", "f-dtitle", "f-dsub", "f-quote", "f-cite", "f-headline", "f-summary"];
function saveDraft(extra = {}) {
  const d = { ...draft.get(), ...extra, fields: Object.fromEntries(FIELDS.map(f => [f, $(f).value])), dirty: [...dirty] };
  draft.set(d);
}
function restoreDraft() {
  const d = draft.get();
  for (const [f, v] of Object.entries(d.fields || {})) if ($(f)) $(f).value = v;
  (d.dirty || []).forEach(f => dirty.add(f));
  return d;
}

// ---------- Step 1–2: links -> rides ----------
function parseLinks(text) {
  const ids = [], bad = [];
  for (const line of text.split(/\n/).map(s => s.trim()).filter(Boolean)) {
    const m = /strava\.com\/activities\/(\d+)/.exec(line) || /^(\d{6,})$/.exec(line);
    if (m) { if (!ids.includes(m[1])) ids.push(m[1]); } else bad.push(line);
  }
  return { ids, bad };
}

async function getRides() {
  const { ids, bad } = parseLinks($("links").value);
  if (bad.length) return msg("links-msg", `Not a Strava activity link: ${bad.slice(0, 3).join(", ")}${bad.length > 3 ? "…" : ""}`, "bad");
  if (!ids.length) return msg("links-msg", "Paste at least one Strava activity link.", "bad");
  msg("links-msg", "");
  if (!store.get(KEY_STRAVA)) return stravaLogin();
  $("b-fetch").disabled = true;
  $("s-rides").hidden = false;
  const list = $("progress"); list.replaceChildren();
  const got = [];
  try {
    for (const id of ids) {
      const li = el("li", {}, `Activity ${id}: fetching…`); list.append(li);
      try {
        const act = await sget(`/activities/${id}`, { include_all_efforts: "true" });
        const streams = await sget(`/activities/${id}/streams`, { keys: "time,distance,latlng,altitude,moving", key_by_type: "true" });
        const pts = points(act, streams);
        if (!pts) throw new Error("no GPS or elevation data (indoor ride?)");
        got.push({ id: Number(id), act, streams, pts });
        li.replaceChildren(el("span", { class: "ok" }, "✓ "), `${act.name} (${pts.length.toLocaleString()} points, ${(act.segment_efforts || []).length} segments)`);
      } catch (e) {
        if (e instanceof NeedLogin) throw e;
        li.replaceChildren(el("span", { class: "err" }, "✗ "), `Activity ${id}: ${e.message}`);
      }
    }
  } catch (e) {
    if (e instanceof NeedLogin) return stravaLogin();
    throw e;
  } finally { $("b-fetch").disabled = false; }
  if (got.length !== ids.length) return msg("links-msg", "Some rides couldn't be fetched (see above). Fix or remove those links and try again.", "bad");
  got.sort((a, b) => Date.parse(a.act.start_date) - Date.parse(b.act.start_date));
  const tz = tzOf(got[0].act);
  for (const r of got) r.base = rideEntry({ id: r.id, region: "", climbs: [] }, r.act.name, r.pts, tz, null, null);
  RIDES = got;
  saveDraft({ pendingFetch: false });
  showRides(); initDetails(); initPerRide(); initClimbs(); initLook();
  for (const s of ["s-details", "s-perride", "s-climbs", "s-look", "s-publish"]) $(s).hidden = false;
  $("s-details").scrollIntoView({ behavior: "smooth" });
}

function showRides() {
  const tb = $("ride-table").querySelector("tbody"); tb.replaceChildren();
  for (const r of RIDES) tb.append(el("tr", {}, el("td", {}, r.base.date), el("td", {}, r.act.name),
    el("td", {}, `${(r.base.dist / 1609.344).toFixed(1)} mi`), el("td", {}, `${Math.round(r.base.gain * 3.28084).toLocaleString()} ft`)));
  $("ride-table").hidden = false;
}

// ---------- Step 3: text ----------
function kickerFor(lang) {
  const d0 = RIDES[0].base.date, d1 = RIDES[RIDES.length - 1].base.date;
  const [y0, m0] = d0.split("-").map(Number), [y1, m1] = d1.split("-").map(Number), M = MONTHS[lang];
  if (y0 !== y1) return `${y0} · ${y1}`;
  return (m0 === m1 ? `${M[m0 - 1]} ${y1}` : `${M[m0 - 1]} · ${M[m1 - 1]} ${y1}`).toUpperCase();
}
const slugify = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
function autoSlug() {
  if (dirty.has("f-slug")) return;
  const year = RIDES[0].base.date.slice(0, 4), base = slugify($("f-title").value);
  $("f-slug").value = base ? (base.includes(year) ? base : `${base}-${year}`) : "";
  checkSlug();
}
function checkSlug() {
  const s = $("f-slug").value, h = $("slug-hint");
  if (!s) { h.textContent = ""; return false; }
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(s)) { h.textContent = "Lowercase letters, numbers and dashes only."; h.className = "hint err"; return false; }
  if (PRESETS.slugs.includes(s)) { h.textContent = "A poster already uses this address."; h.className = "hint err"; return false; }
  h.textContent = `${SITE.siteUrl || "../"}${s}/`; h.className = "hint"; return true;
}
// written without the "i" flag so the same pattern works when the Python build reads it from rides.json
const STRIP = /^([Dd]ay|DAY|[Dd][ií]a|D[IÍ]A|[Gg]iorno|GIORNO|[Ss]tage|STAGE|[Tt]appa|TAPPA|[Ee]tapa|ETAPA)\s*\d+\s*[:.\-–]\s*/;
function initDetails() {
  const set = (f, v) => { if (!dirty.has(f) && !$(f).value) $(f).value = v; };
  set("f-kicker", kickerFor($("f-lang").value));
  set("f-headline", `MARCO  ·  {rides} ${RIDES_WORD[$("f-lang").value]}`);
  if (!$("f-dtitle").value) $("f-dtitle").value = $("f-title").value;
  autoSlug();
  const strippable = RIDES.length > 1 && RIDES.every(r => STRIP.test(r.act.name));
  $("strip-wrap").hidden = !strippable;
  if (strippable) $("strip-text").textContent = `Remove "${STRIP.exec(RIDES[0].act.name)[0].trim()}"-style prefixes from ride titles (each ride is already numbered)`;
}
function wireDetails() {
  for (const f of ["f-slug", "f-kicker", "f-dtitle", "f-headline"]) $(f).addEventListener("input", () => { dirty.add(f); if (f === "f-slug") checkSlug(); saveDraft(); });
  for (const f of ["f-dsub", "f-quote", "f-cite", "f-summary", "links"]) $(f).addEventListener("input", () => saveDraft());
  $("f-title").addEventListener("input", () => { if (!dirty.has("f-dtitle")) $("f-dtitle").value = $("f-title").value; if (RIDES.length) autoSlug(); saveDraft(); });
  $("f-lang").addEventListener("change", () => {
    const l = $("f-lang").value;
    if (RIDES.length && !dirty.has("f-kicker")) $("f-kicker").value = kickerFor(l);
    if (!dirty.has("f-headline")) $("f-headline").value = `MARCO  ·  {rides} ${RIDES_WORD[l]}`;
    saveDraft();
  });
}

// ---------- Step 4: regions and towns ----------
function initPerRide() {
  const tb = $("region-table").querySelector("tbody"); tb.replaceChildren();
  let prev = "";
  RIDES.forEach((r, i) => {
    const region = el("input", { type: "text", id: `region-${i}`, list: "region-list", required: true, value: r.act.location_state || prev || "" });
    const town = el("input", { type: "text", id: `town-${i}`, value: r.act.location_city || "" });
    region.addEventListener("change", () => { refreshRegionList(); fillNextRegions(i); });
    prev = region.value;
    tb.append(el("tr", {}, el("td", {}, `${i + 1}. ${r.act.name}`), el("td", {}, region), el("td", {}, town)));
  });
  refreshRegionList();
}
function fillNextRegions(i) {   // typing a region fills the empty ones after it
  for (let j = i + 1; j < RIDES.length && !$(`region-${j}`).value; j++) $(`region-${j}`).value = $(`region-${i}`).value;
}
function refreshRegionList() {
  const names = [...new Set(RIDES.map((_, i) => $(`region-${i}`).value.trim()).filter(Boolean))];
  $("region-list").replaceChildren(...names.map(n => el("option", { value: n })));
}

// ---------- Step 5: climbs ----------
function initClimbs() {
  const box = $("climb-list"); box.replaceChildren();
  RIDES.forEach((r, i) => {
    const sugg = suggestions(r.act, r.pts).slice(0, 6);
    const div = el("div", { class: "ride" }, el("h3", {}, `${i + 1}. ${r.act.name} `, el("small", {}, r.base.date)));
    if (!sugg.length) div.append(el("p", { class: "hint" }, "No uphill Strava segments on this ride."));
    sugg.forEach((c, k) => {
      const cb = el("input", { type: "checkbox", checked: k < 3 });
      const label = el("input", { type: "text", value: c.entry.label });
      Object.assign(cb.dataset, { ride: i, kind: "segment", k });
      const row = el("div", { class: "climb" }, cb, label,
        el("div", { class: "meta" }, `${CATEGORY[c.cat] ?? c.cat} · +${Math.round(c.gain * 3.28084).toLocaleString()} ft · summit ${Math.round(c.summit_ele * 3.28084).toLocaleString()} ft · Strava segment “${c.name}”`));
      row._climb = c; row._label = label; row._cb = cb;
      div.append(row);
    });
    // the ride's own high point, for when you went past the end of every segment (or there are none)
    const hiCb = el("input", { type: "checkbox" }), hiLabel = el("input", { type: "text", placeholder: "Name for the ride's highest point" });
    const hiRow = el("div", { class: "climb" }, hiCb, hiLabel, el("div", { class: "meta" }, `Label the ride's highest point (${Math.round(r.base.maxEle * 3.28084).toLocaleString()} ft)`));
    hiRow._high = true; hiRow._label = hiLabel; hiRow._cb = hiCb;
    hiLabel.addEventListener("input", () => { hiCb.checked = !!hiLabel.value.trim(); });
    div.append(hiRow);
    div.dataset.ride = i;
    box.append(div);
  });
}
function chosenClimbs(i) {
  const div = $("climb-list").querySelector(`.ride[data-ride="${i}"]`);
  const out = [];
  for (const row of div.querySelectorAll(".climb")) {
    if (!row._cb.checked) continue;
    const label = row._label.value.trim();
    if (!label) continue;
    if (row._high) { out.push({ label, range: [0, null] }); continue; }
    const c = row._climb, e = { label, segment: c.name };
    if (c.entry.near != null) e.near = c.entry.near;
    e.range = [c.effort.start_index, c.effort.end_index];
    out.push(e);
  }
  return out;
}

// ---------- Step 6: look ----------
function initLook() {
  const box = $("theme-list"); box.replaceChildren();
  const names = Object.keys(PRESETS.themes);
  const pre = DEFAULT_THEMES.filter(n => names.includes(n));
  if (!pre.length) pre.push(...names.slice(0, 3));
  for (const n of names) {
    const t = PRESETS.themes[n];
    const cb = el("input", { type: "checkbox", value: n, checked: pre.includes(n) });
    const def = el("input", { type: "radio", name: "def-theme", value: n, checked: n === pre[0] });
    box.append(el("label", { class: "theme" }, cb, el("span", { class: "sw" }, ...[t.bgTop, t.profile, t.accent].map(c => el("i", { style: `background:${c}` }))), n,
                  el("span", { class: "def" }, def, "default")));
    def.addEventListener("change", () => { cb.checked = true; });
    cb.addEventListener("change", () => { if (!cb.checked && def.checked) { const other = box.querySelector("input[type=checkbox]:checked"); if (other) box.querySelector(`input[type=radio][value="${CSS.escape(other.value)}"]`).checked = true; } });
  }
  const flag = $("f-flag");
  if (flag.options.length === 1) for (const n of Object.keys(FLAGS)) flag.append(el("option", { value: n }, n));
  // elevation scale from the data: base 0 for low terrain (Enhanced relief), otherwise just under the low point (True scale)
  const lo = Math.min(...RIDES.map(r => r.base.minEle)), hi = Math.max(...RIDES.map(r => r.base.maxEle));
  const minM = lo < 400 ? 0 : Math.floor((lo - 100) / 100) * 100;
  const topM = Math.ceil((hi + 50) / 100) * 100;
  $("f-emin").value = minM; $("f-etop").value = topM; $("f-etopft").value = Math.ceil(topM * 3.28084 / 100) * 100;
  $("f-relief").value = minM === 0 ? "sqrt" : "linear";
  $("elev-hint").textContent = `Your rides go from ${Math.round(lo).toLocaleString()} m to ${Math.round(hi).toLocaleString()} m (${Math.round(lo * 3.28084).toLocaleString()}–${Math.round(hi * 3.28084).toLocaleString()} ft).`;
  $("f-etop").addEventListener("input", () => { $("f-etopft").value = Math.ceil($("f-etop").value * 3.28084 / 100) * 100; });
}
function rings(lo, hi, steps) {   // 3–4 round values strictly inside (lo, hi)
  for (const s of steps) {
    const v = []; for (let x = Math.ceil((lo + 1) / s) * s; x < hi; x += s) v.push(x);
    if (v.length <= 4 && v.length >= 2) return v;
  }
  return [Math.round((lo + hi) / 2)];
}

// ---------- Assemble the poster's files ----------
function collect() {
  const errors = [];
  const title = $("f-title").value.trim(), slug = $("f-slug").value.trim();
  if (!title) errors.push("Give the poster a title (step 3).");
  if (!checkSlug()) errors.push("Choose a valid, unused web address (step 3).");
  const regions = RIDES.map((_, i) => $(`region-${i}`).value.trim());
  if (regions.some(r => !r)) errors.push("Every ride needs a region (step 4).");
  const themes = [...$("theme-list").querySelectorAll("input[type=checkbox]:checked")].map(c => c.value);
  if (!themes.length) errors.push("Pick at least one colour theme (step 6).");
  const minM = Number($("f-emin").value), topM = Number($("f-etop").value), topFt = Number($("f-etopft").value);
  if (!(topM > minM)) errors.push("The outer-edge elevation must be above the base (step 6).");
  if (errors.length) return { errors };

  const lang = $("f-lang").value, tz = tzOf(RIDES[0].act);
  const strip = !$("strip-wrap").hidden && $("f-strip").checked ? STRIP.source : null;
  const ridesJson = { tz, stripName: strip, rides: RIDES.map((r, i) => {
    const o = { id: r.id, region: regions[i] };
    const town = $(`town-${i}`).value.trim(); if (town) o.town = town;
    o.climbs = chosenClimbs(i);
    return o;
  }) };
  const regionNames = [...new Set(regions)];
  const def = $("theme-list").querySelector("input[type=radio]:checked")?.value;
  const themeMap = {};
  for (const n of themes) {   // make sure every region has a colour token
    const t = { ...PRESETS.themes[n] }, used = new Set(Object.keys(t).filter(k => /^r\d+$/.test(k)).map(k => t[k]));
    regionNames.forEach((_, i) => { if (!t["r" + (i + 1)]) t["r" + (i + 1)] = REGION_FALLBACK.find(c => !used.has(c)) || REGION_FALLBACK[i % REGION_FALLBACK.length]; used.add(t["r" + (i + 1)]); });
    themeMap[n] = t;
  }
  const quote = $("f-quote").value.split("\n").map(s => s.trim()).filter(Boolean).slice(0, 3);
  const disc = { kicker: $("f-kicker").value.trim(), title: $("f-dtitle").value.trim() || title, subtitle: $("f-dsub").value.trim(), quote };
  if ($("f-cite").value.trim()) disc.cite = $("f-cite").value.trim();
  const d0 = RIDES[0].base.date, d1 = RIDES[RIDES.length - 1].base.date;
  const config = {
    title, summary: $("f-summary").value.trim() || `${RIDES.length} ride${RIDES.length > 1 ? "s" : ""}, ${d0 === d1 ? d0 : d0 + " to " + d1}.`,
    lang, storageKey: `poster-${slug}-v1`,
    ariaLabel: `Circular elevation profile of ${RIDES.length} bike ride${RIDES.length > 1 ? "s" : ""}: ${title}`,
    disc, flag: FLAGS[$("f-flag").value] || [], headline: $("f-headline").value.trim() || "{rides} RIDES",
    elevation: { minM, topFt, topM, ringsFt: rings(minM * 3.28084, topFt, [500, 1000, 2000, 2500, 5000]), ringsM: rings(minM, topM, [250, 500, 1000]) },
    defaultTheme: themes.includes(def) ? def : themes[0], defaultRelief: $("f-relief").value, themes: themeMap,
  };
  const stripRe = strip ? new RegExp(strip) : null;
  const rides = RIDES.map((r, i) => rideEntry(ridesJson.rides[i], r.act.name, r.pts, tz, stripRe, r.act));
  return { slug, config, ridesJson, rides };
}
const posterHtml = ({ config, rides }) => TEMPLATE.replace("__TITLE__", config.title.replace(/[&<>"]/g, c => `&#${c.charCodeAt(0)};`))
  .replace("/*__DATA__*/", "const RIDES = " + JSON.stringify(rides) + ";\nconst POSTER = " + JSON.stringify(config) + ";");

function preview() {
  const p = collect();
  if (p.errors) return msg("preview-msg", p.errors.join(" "), "bad");
  msg("preview-msg", "");
  const f = $("preview"); f.hidden = false; f.srcdoc = posterHtml(p);
  f.scrollIntoView({ behavior: "smooth" });
}

// ---------- Step 7: publish (one commit through GitHub's API) ----------
async function gh(path, opts = {}) {
  const token = $("f-gh").value.trim() || store.get(KEY_GH);
  const r = await fetch((SITE.githubApi || "https://api.github.com") + path, { ...opts,
    headers: { Accept: "application/vnd.github+json", Authorization: "Bearer " + token, "X-GitHub-Api-Version": "2022-11-28", ...(opts.body ? { "Content-Type": "application/json" } : {}) } });
  if (r.status === 401) throw new Error("GitHub didn't accept the token (expired or mistyped?).");
  if (r.status === 403) throw new Error("The token can't write to this repository. Give it Contents: Read and write.");
  return r;
}
// rides.json in the same compact layout as the hand-written ones: a ride per block, a climb per line
function ridesJsonText(r) {
  const j = v => JSON.stringify(v);
  const ride = x => {
    const head = Object.entries(x).filter(([k]) => k !== "climbs").map(([k, v]) => `${j(k)}: ${j(v)}`).join(", ");
    const obj = o => "{" + Object.entries(o).map(([k, v]) => `${j(k)}: ${j(v)}`).join(", ") + "}";
    const cl = x.climbs.map(c => "      " + obj(c)).join(",\n");
    return `    {${head},\n     "climbs": [${cl ? "\n" + cl + "\n     ]" : "]"}}`;
  };
  return `{\n  "tz": ${j(r.tz)},\n  "stripName": ${j(r.stripName)},\n  "rides": [\n${r.rides.map(ride).join(",\n")}\n  ]\n}\n`;
}
async function publish() {
  const p = collect();
  if (p.errors) return msg("publish-msg", p.errors.join(" "), "bad");
  if (!($("f-gh").value.trim() || store.get(KEY_GH))) return msg("publish-msg", "Paste a GitHub token first.", "bad");
  const [owner, repo] = SITE.repo.split("/"), branch = SITE.branch || "main", base = `/repos/${owner}/${repo}`;
  const dir = `src/posters/${p.slug}`;
  const files = { [`${dir}/config.json`]: JSON.stringify(p.config, null, 2) + "\n",
                  [`${dir}/rides.json`]: ridesJsonText(p.ridesJson),
                  [`${dir}/rides_data.js`]: "const RIDES = " + JSON.stringify(p.rides) + ";\n" };
  $("b-publish").disabled = true; msg("publish-msg", "Publishing…");
  try {
    const exists = await gh(`${base}/contents/${dir}?ref=${branch}`);
    if (exists.status === 200) throw new Error(`The repository already has a poster at ${dir}. Choose another web address.`);
    if (exists.status !== 404) throw new Error(`Couldn't check the repository (GitHub returned ${exists.status}). Does the token have access to ${SITE.repo}?`);
    for (let attempt = 0; ; attempt++) {
      const ref = await (await gh(`${base}/git/ref/heads/${branch}`)).json();
      const head = ref.object.sha;
      const commit = await (await gh(`${base}/git/commits/${head}`)).json();
      const tree = await (await gh(`${base}/git/trees`, { method: "POST", body: JSON.stringify({ base_tree: commit.tree.sha,
        tree: Object.entries(files).map(([path, content]) => ({ path, mode: "100644", type: "blob", content })) }) })).json();
      const made = await (await gh(`${base}/git/commits`, { method: "POST", body: JSON.stringify({
        message: `Add poster: ${p.config.title}\n\nCreated with the gallery's Add poster page from ${RIDES.length} Strava activit${RIDES.length > 1 ? "ies" : "y"}.`,
        tree: tree.sha, parents: [head] }) })).json();
      const upd = await gh(`${base}/git/refs/heads/${branch}`, { method: "PATCH", body: JSON.stringify({ sha: made.sha, force: false }) });
      if (upd.ok) break;
      if (upd.status === 422 && attempt === 0) continue;   // someone pushed meanwhile: rebuild on the new head once
      throw new Error(`GitHub refused the update (${upd.status}). If ${branch} requires pull requests, publishing can't commit to it directly.`);
    }
    if ($("f-gh-remember").checked && $("f-gh").value.trim()) store.set(KEY_GH, $("f-gh").value.trim());
    draft.clear();
    const url = `${SITE.siteUrl || "../"}${p.slug}/`;
    const m = $("publish-msg"); m.className = "msg good";
    m.replaceChildren("Published. The site is rebuilding; your poster will be at ", el("a", { href: url }, url),
      " in a minute or two (", el("a", { href: `https://github.com/${SITE.repo}/actions`, target: "_blank", rel: "noopener" }, "build progress"), ").");
    PRESETS.slugs.push(p.slug);
  } catch (e) {
    msg("publish-msg", e.message, "bad");
  } finally { $("b-publish").disabled = false; showGhState(); }
}
function showGhState() {
  const saved = !!store.get(KEY_GH);
  $("gh-token-wrap").hidden = saved; $("gh-saved").hidden = !saved;
}

// ---------- Start ----------
async function main() {
  const get = async (f, as) => { const r = await fetch(f, { cache: "no-cache" }); if (!r.ok) throw new Error(f); return as === "text" ? r.text() : r.json(); };
  [SITE, PRESETS, TEMPLATE] = await Promise.all([get("site.json"), get("presets.json"), get("template.html", "text")]);
  $("repo-name").textContent = SITE.repo;
  if (!SITE.stravaWorker) { $("s-setup").hidden = false; $("b-fetch").disabled = true; }
  wireDetails(); showGhState();
  $("gh-forget").addEventListener("click", e => { e.preventDefault(); store.del(KEY_GH); showGhState(); });
  $("b-fetch").addEventListener("click", () => getRides().catch(e => msg("links-msg", e.message, "bad")));
  $("b-preview").addEventListener("click", preview);
  $("b-publish").addEventListener("click", publish);

  const d = restoreDraft();
  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get("access_token")) {
    store.set(KEY_STRAVA, { access_token: h.get("access_token"), refresh_token: h.get("refresh_token"), expires_at: Number(h.get("expires_at")), scope: h.get("scope") });
    history.replaceState(null, "", location.pathname + location.search);   // tokens out of the address bar
    if (h.get("scope") && !h.get("scope").includes("activity:read_all")) msg("links-msg", "Private activities weren't allowed at the Strava login; only public ones can be fetched.", "bad");
  } else if (h.get("strava_error")) {
    history.replaceState(null, "", location.pathname + location.search);
    msg("links-msg", h.get("strava_error") === "access_denied" ? "Strava login was cancelled." : `Strava login failed (${h.get("strava_error")}).`, "bad");
    return;
  }
  if (d.pendingFetch && store.get(KEY_STRAVA) && SITE.stravaWorker) getRides().catch(e => msg("links-msg", e.message, "bad"));
}
main().catch(e => { document.querySelector(".lead").textContent = "This page couldn't load its settings (" + e.message + ")."; });
