"""
generate_map.py
---------------
Generates output/hospital_proximity_map.html — a self-contained interactive map.

  - Leaflet.js tiles (OpenStreetMap, pan/zoom, no API token needed)
  - Canvas renderer handles 25k ZIP dots efficiently
  - Sidebar: color-by dropdown, distance/income range sliders, RUCA checkboxes
  - Live legend + ZIP counter

Usage:
    python3 generate_map.py
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ── Data loading ───────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    df = pd.read_excel(BASE_DIR / "output" / "accounts_enriched.xlsx", dtype={"Zip": str})
    df["Zip"] = df["Zip"].astype(str).str.zfill(5)
    df["Count of Zip"] = pd.to_numeric(df["Count of Zip"], errors="coerce")

    centroids = pd.read_csv(
        BASE_DIR / "data" / "processed" / "zip_centroids.csv", dtype={"zip": str}
    )
    centroids["zip"] = centroids["zip"].str.zfill(5)

    df = df.merge(centroids, left_on="Zip", right_on="zip", how="left")
    df = df.dropna(subset=["lat", "lon"])

    df["hospital_distance_miles"] = pd.to_numeric(df["hospital_distance_miles"], errors="coerce")
    df["median_hh_income"]        = pd.to_numeric(df["median_hh_income"],        errors="coerce")
    df["ruca_code"]               = pd.to_numeric(df["ruca_code"],               errors="coerce")
    return df


def build_json(df: pd.DataFrame) -> str:
    records = []
    for _, row in df.iterrows():
        dist   = None if pd.isna(row.get("hospital_distance_miles")) else round(float(row["hospital_distance_miles"]), 2)
        income = None if pd.isna(row.get("median_hh_income"))        else int(row["median_hh_income"])
        ruca   = None if pd.isna(row.get("ruca_code"))               else int(row["ruca_code"])
        ruca_c = str(row.get("ruca_category") or "")
        count  = int(row["Count of Zip"]) if pd.notna(row.get("Count of Zip")) else 0
        records.append({
            "z":  str(row["Zip"]),
            "la": round(float(row["lat"]), 5),
            "lo": round(float(row["lon"]), 5),
            "n":  count,
            "d":  dist,
            "i":  income,
            "r":  ruca,
            "rc": ruca_c,
        })
    return json.dumps(records, separators=(",", ":"))


# ── HTML generation (no triple-quoted templates with JS braces) ────────────────

def html_head() -> str:
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="UTF-8"/>\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1"/>\n'
        '<title>Hospital Proximity Map</title>\n'
        '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>\n'
        '<style>\n'
        '  *{box-sizing:border-box;margin:0;padding:0}\n'
        '  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'
        'background:#F7EFE5;color:#2D1B41;height:100vh;display:flex;flex-direction:column}\n'
        '  header{background:#2D1B41;color:#fff;padding:12px 20px;display:flex;'
        'align-items:center;gap:12px;flex-shrink:0;box-shadow:0 2px 8px rgba(45,27,65,.4)}\n'
        '  header h1{font-size:16px;font-weight:600;letter-spacing:.01em}\n'
        '  .badges{display:flex;gap:8px;margin-left:auto}\n'
        '  .badge{border-radius:20px;padding:3px 12px;font-size:12px;font-weight:600;white-space:nowrap}\n'
        '  .badge-zip{background:#4724A5;color:#fff}\n'
        '  .badge-acct{background:#C9ACE8;color:#2D1B41}\n'
        '  .layout{display:flex;flex:1;overflow:hidden}\n'
        '  .panel{width:270px;flex-shrink:0;background:#fff;border-right:1px solid #D8D8D8;'
        'padding:16px 14px;overflow-y:auto;display:flex;flex-direction:column;gap:20px}\n'
        '  .panel-section h2{font-size:10px;font-weight:700;text-transform:uppercase;'
        'letter-spacing:.1em;color:#4724A5;margin-bottom:8px}\n'
        '  select{width:100%;padding:7px 10px;border:1px solid #D8D8D8;border-radius:7px;'
        'background:#F7EFE5;font-size:13px;cursor:pointer;color:#2D1B41}\n'
        '  select:focus{outline:none;border-color:#4724A5;box-shadow:0 0 0 3px rgba(71,36,165,.15)}\n'
        '  .slider-wrap{display:flex;flex-direction:column;gap:6px}\n'
        '  .slider-labels{display:flex;justify-content:space-between;font-size:11px;color:#6b5a7e}\n'
        '  .slider-labels b{color:#2D1B41;font-weight:600}\n'
        '  input[type=range]{width:100%;accent-color:#4724A5;height:4px;cursor:pointer}\n'
        '  .ruca-list{display:flex;flex-direction:column;gap:6px}\n'
        '  .ruca-item{display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:7px;'
        'cursor:pointer;transition:background .15s}\n'
        '  .ruca-item:hover{background:#F0E8F8}\n'
        '  .ruca-item input{width:14px;height:14px;cursor:pointer;accent-color:#4724A5}\n'
        '  .swatch{width:12px;height:12px;border-radius:50%;flex-shrink:0}\n'
        '  .ruca-item span{font-size:13px;color:#2D1B41}\n'
        '  .legend{padding:8px 0 0;border-top:1px solid #D8D8D8}\n'
        '  .legend h2{font-size:10px;font-weight:700;text-transform:uppercase;'
        'letter-spacing:.1em;color:#4724A5;margin-bottom:8px}\n'
        '  .legend-gradient{height:12px;border-radius:6px;margin-bottom:4px}\n'
        '  .legend-labels{display:flex;justify-content:space-between;font-size:10px;color:#6b5a7e}\n'
        '  .legend-swatches{display:flex;flex-direction:column;gap:5px}\n'
        '  .legend-swatch-row{display:flex;align-items:center;gap:7px;font-size:12px;color:#2D1B41}\n'
        '  .counter{font-size:12px;color:#6b5a7e;padding-top:4px;display:flex;flex-direction:column;gap:3px}\n'
        '  .counter b{color:#2D1B41}\n'
        '  #map{flex:1}\n'
        '</style>\n</head>\n'
    )


def html_body(total: int, max_dist: int, max_inc: int) -> str:
    max_inc_fmt = f"{max_inc:,}"
    return (
        '<body>\n'
        '<header>\n'
        '  <h1>Hospital Proximity &amp; Market Map</h1>\n'
        '  <div class="badges">\n'
        '    <span class="badge badge-zip" id="hdr-zip">Loading&hellip;</span>\n'
        '    <span class="badge badge-acct" id="hdr-acct"></span>\n'
        '  </div>\n'
        '</header>\n'
        '<div class="layout">\n'
        '  <aside class="panel">\n'

        '    <div class="panel-section">\n'
        '      <h2>Color by</h2>\n'
        '      <select id="color-by">\n'
        '        <option value="distance">Hospital Distance (miles)</option>\n'
        '        <option value="income">Median HH Income</option>\n'
        '        <option value="ruca">RUCA Category</option>\n'
        '      </select>\n'
        '    </div>\n'

        '    <div class="panel-section">\n'
        '      <h2>Distance to Hospital (miles)</h2>\n'
        '      <div class="slider-wrap">\n'
        '        <div class="slider-labels">Min <b id="d-min-lbl">0</b>'
        '&nbsp;&nbsp;Max <b id="d-max-lbl">' + str(max_dist) + '</b></div>\n'
        '        <input type="range" id="d-min" min="0" max="' + str(max_dist) + '" value="0" step="1"/>\n'
        '        <input type="range" id="d-max" min="0" max="' + str(max_dist) + '" value="' + str(max_dist) + '" step="1"/>\n'
        '      </div>\n'
        '    </div>\n'

        '    <div class="panel-section">\n'
        '      <h2>Median Household Income</h2>\n'
        '      <div class="slider-wrap">\n'
        '        <div class="slider-labels">Min <b id="i-min-lbl">$0</b>'
        '&nbsp;&nbsp;Max <b id="i-max-lbl">$' + max_inc_fmt + '</b></div>\n'
        '        <input type="range" id="i-min" min="0" max="' + str(max_inc) + '" value="0" step="1000"/>\n'
        '        <input type="range" id="i-max" min="0" max="' + str(max_inc) + '" value="' + str(max_inc) + '" step="1000"/>\n'
        '      </div>\n'
        '    </div>\n'

        '    <div class="panel-section">\n'
        '      <h2>RUCA Category</h2>\n'
        '      <div class="ruca-list">\n'
        '        <label class="ruca-item"><input type="checkbox" class="ruca-cb" value="Metropolitan" checked/>'
        '<span class="swatch" style="background:#4724A5"></span><span>Metropolitan</span></label>\n'
        '        <label class="ruca-item"><input type="checkbox" class="ruca-cb" value="Micropolitan" checked/>'
        '<span class="swatch" style="background:#7B52D4"></span><span>Micropolitan</span></label>\n'
        '        <label class="ruca-item"><input type="checkbox" class="ruca-cb" value="Small Town" checked/>'
        '<span class="swatch" style="background:#C9ACE8"></span><span>Small Town</span></label>\n'
        '        <label class="ruca-item"><input type="checkbox" class="ruca-cb" value="Rural" checked/>'
        '<span class="swatch" style="background:#2D1B41"></span><span>Rural</span></label>\n'
        '        <label class="ruca-item"><input type="checkbox" class="ruca-cb" value="" checked/>'
        '<span class="swatch" style="background:#D8D8D8"></span><span>Unknown</span></label>\n'
        '      </div>\n'
        '    </div>\n'

        '    <div class="legend" id="legend">\n'
        '      <h2>Legend</h2>\n'
        '      <div id="legend-body"></div>\n'
        '    </div>\n'

        '    <div class="counter">'
        '<div>ZIPs: <b id="zip-count">-</b> of <b>' + f"{total:,}" + '</b></div>'
        '<div>Accounts: <b id="acct-count">-</b> of <b id="acct-total">-</b></div>'
        '</div>\n'
        '  </aside>\n'
        '  <div id="map"></div>\n'
        '</div>\n'
    )


JS = r"""
const RUCA_COLORS = {
  "Metropolitan": "#4724A5",
  "Micropolitan": "#7B52D4",
  "Small Town":   "#C9ACE8",
  "Rural":        "#2D1B41",
  "":             "#D8D8D8"
};

// Continuous color scales: [value 0-1] -> hex color
function lerpColor(t, stops) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    if (t <= stops[i][0]) {
      const lo = stops[i-1], hi = stops[i];
      const u = (t - lo[0]) / (hi[0] - lo[0]);
      return blendHex(lo[1], hi[1], u);
    }
  }
  return stops[stops.length-1][1];
}
function hexToRgb(h) {
  const n = parseInt(h.slice(1), 16);
  return [(n>>16)&255, (n>>8)&255, n&255];
}
function blendHex(a, b, t) {
  const ra = hexToRgb(a), rb = hexToRgb(b);
  const r = ra.map((v,i) => Math.round(v + (rb[i]-v)*t));
  return '#' + r.map(v => v.toString(16).padStart(2,'0')).join('');
}

const DIST_STOPS  = [[0,'#9B72D0'],[.5,'#4724A5'],[1,'#2D1B41']];
const INC_STOPS   = [[0,'#d73027'],[.33,'#fc8d59'],[.67,'#fee08b'],[1,'#1a9850']];

let distMax = 0, incMax = 0;
DATA.forEach(p => {
  if (p.d != null && p.d > distMax) distMax = p.d;
  if (p.i != null && p.i > incMax)  incMax  = p.i;
});

function getColor(p, colorBy) {
  if (colorBy === 'ruca') return RUCA_COLORS[p.rc] || '#aaa';
  if (colorBy === 'distance') {
    if (p.d == null) return '#ccc';
    return lerpColor(p.d / distMax, DIST_STOPS);
  }
  if (p.i == null) return '#ccc';
  return lerpColor(p.i / incMax, INC_STOPS);
}

function scaleDot(n) {
  if (!n) return 4;
  return Math.max(4, Math.min(13, 3 + Math.log2(n + 1) * 1.5));
}

function fmtDist(v)   { return v == null ? 'N/A' : v.toFixed(1) + ' mi'; }
function fmtIncome(v) { return v == null ? 'N/A' : '$' + v.toLocaleString(); }

// ── Map init ────────────────────────────────────────────────────────────────
const map = L.map('map', { preferCanvas: true }).setView([39.5, -98.35], 4);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
}).addTo(map);

const renderer = L.canvas({ padding: 0.5 });
const markers  = [];

DATA.forEach(p => {
  const m = L.circleMarker([p.la, p.lo], {
    renderer, radius: 5, weight: 0,
    fillOpacity: 0.8, fillColor: '#3a86ff'
  });
  m.bindPopup(
    '<b>ZIP ' + p.z + '</b><br>' +
    'Accounts: ' + p.n.toLocaleString() + '<br>' +
    'Distance: ' + fmtDist(p.d) + '<br>' +
    'Income: '   + fmtIncome(p.i) + '<br>' +
    'RUCA: '     + (p.rc || 'Unknown') + (p.r != null ? ' (' + p.r + ')' : '')
  );
  m.addTo(map);
  markers.push({ m, p });
});

// ── Filter + recolor ─────────────────────────────────────────────────────────
function getFilters() {
  return {
    colorBy:   document.getElementById('color-by').value,
    dMin:      +document.getElementById('d-min').value,
    dMax:      +document.getElementById('d-max').value,
    iMin:      +document.getElementById('i-min').value,
    iMax:      +document.getElementById('i-max').value,
    rucaOn:    new Set([...document.querySelectorAll('.ruca-cb:checked')].map(e => e.value))
  };
}

const totalAccounts = DATA.reduce((sum, p) => sum + p.n, 0);
document.getElementById('acct-total').textContent = totalAccounts.toLocaleString();

function update() {
  const f = getFilters();
  let visibleZips = 0, visibleAccts = 0;
  markers.forEach(({ m, p }) => {
    const rucaOk = f.rucaOn.has(p.rc);
    const distOk = p.d == null || (p.d >= f.dMin && p.d <= f.dMax);
    const incOk  = p.i == null || (p.i >= f.iMin  && p.i <= f.iMax);
    const show   = rucaOk && distOk && incOk;
    if (show) {
      m.setStyle({ fillColor: getColor(p, f.colorBy), radius: scaleDot(p.n) });
      if (!map.hasLayer(m)) m.addTo(map);
      visibleZips++;
      visibleAccts += p.n;
    } else {
      if (map.hasLayer(m)) map.removeLayer(m);
    }
  });
  const zs = visibleZips.toLocaleString();
  const as = visibleAccts.toLocaleString();
  document.getElementById('zip-count').textContent  = zs;
  document.getElementById('acct-count').textContent = as;
  document.getElementById('hdr-zip').textContent    = zs + ' ZIPs';
  document.getElementById('hdr-acct').textContent   = as + ' Accounts';
  updateLegend(f.colorBy);
}

// ── Legend ──────────────────────────────────────────────────────────────────
function gradientBar(stops, label, minLbl, maxLbl) {
  const colors = stops.map(s => s[1]).join(',');
  return (
    '<div class="legend-gradient" style="background:linear-gradient(to right,' + colors + ')"></div>' +
    '<div class="legend-labels"><span>' + minLbl + '</span><span>' + label + '</span><span>' + maxLbl + '</span></div>'
  );
}

function updateLegend(colorBy) {
  const el = document.getElementById('legend-body');
  if (colorBy === 'ruca') {
    el.innerHTML = '<div class="legend-swatches">' +
      Object.entries(RUCA_COLORS).filter(([k]) => k !== '').map(([k, c]) =>
        '<div class="legend-swatch-row"><span class="swatch" style="background:' + c + ';width:12px;height:12px;border-radius:50%;display:inline-block"></span>' + k + '</div>'
      ).join('') +
      '</div>';
  } else if (colorBy === 'distance') {
    el.innerHTML = gradientBar(DIST_STOPS, 'miles', '0 mi', distMax.toFixed(0) + ' mi');
  } else {
    el.innerHTML = gradientBar(INC_STOPS, 'income', '$0', '$' + Math.round(incMax/1000) + 'k');
  }
}

// ── Slider label sync ────────────────────────────────────────────────────────
function syncLabels() {
  let dMin = +document.getElementById('d-min').value;
  let dMax = +document.getElementById('d-max').value;
  let iMin = +document.getElementById('i-min').value;
  let iMax = +document.getElementById('i-max').value;
  if (dMin > dMax) { document.getElementById('d-max').value = dMin; dMax = dMin; }
  if (iMin > iMax) { document.getElementById('i-max').value = iMin; iMax = iMin; }
  document.getElementById('d-min-lbl').textContent = dMin;
  document.getElementById('d-max-lbl').textContent = dMax;
  document.getElementById('i-min-lbl').textContent = '$' + iMin.toLocaleString();
  document.getElementById('i-max-lbl').textContent = '$' + iMax.toLocaleString();
}

document.querySelectorAll('input, select').forEach(el =>
  el.addEventListener('input', () => { syncLabels(); update(); })
);

update();
"""


def generate(out_path: Path, df: pd.DataFrame):
    json_data  = build_json(df)
    total      = len(df)
    max_dist   = int(np.ceil(df["hospital_distance_miles"].dropna().max())) if df["hospital_distance_miles"].notna().any() else 250
    max_inc    = int(np.ceil(df["median_hh_income"].dropna().max() / 1000) * 1000) if df["median_hh_income"].notna().any() else 250000

    html = (
        html_head()
        + html_body(total, max_dist, max_inc)
        + '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>\n'
        + '<script>\nconst DATA = ' + json_data + ';\n'
        + JS
        + '\n</script>\n</body>\n</html>\n'
    )

    out_path.write_text(html, encoding="utf-8")
    print(f"Map written → {out_path}  ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    print("Loading data...")
    df = load_data()
    print(f"  {len(df):,} ZIPs with coordinates")
    generate(OUTPUT_DIR / "hospital_proximity_map.html", df)
    print("Done.")
