"""Build public/us-states.geojson from the Census-derived state boundaries.

The coverage map used to be a grid of labelled squares — a "statebins" layout —
because there was no state geometry in the app and adding a map library was not
wanted. Squares are legible but they are not a map: they cannot show that a
recall covers the Gulf coast, or the Pacific Northwest, or everything east of
the Mississippi.

Run this to regenerate the asset (it is committed, so this is only needed if the
source changes):

    python scripts/build_us_states_geojson.py

Source: the public-domain US Census cartographic boundary file as republished in
the Leaflet choropleth example. Two transforms are applied here so the runtime
needs no lookup table and no simplification step:

  * `properties.code` — the USPS two-letter code the API actually returns, baked
    in, so the component matches on it directly.
  * coordinates rounded to 2 decimal places (~1 km), which is far finer than a
    600 px map can draw and cuts the file by roughly two thirds.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = ("https://raw.githubusercontent.com/PublicaMundi/MappingAPI/"
          "master/data/geojson/us-states.json")

NAME_TO_CODE = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN",
    "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
    "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Puerto Rico": "PR", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI",
    "Wyoming": "WY",
}


def round_coords(node, ndigits=2):
    if isinstance(node[0], (int, float)):
        return [round(node[0], ndigits), round(node[1], ndigits)]
    return [round_coords(c, ndigits) for c in node]


def main() -> int:
    # curl rather than urllib alone: a stock macOS python often has no CA
    # bundle, and this failing at certificate verification is a confusing way
    # to learn that.
    try:
        with urllib.request.urlopen(SOURCE, timeout=60) as r:
            data = json.load(r)
    except (urllib.error.URLError, OSError) as exc:
        print(f"urllib failed ({type(exc).__name__}); falling back to curl", file=sys.stderr)
        raw = subprocess.run(["curl", "-fsSL", "--max-time", "60", SOURCE],
                             capture_output=True, check=True).stdout
        data = json.loads(raw)

    out = []
    missing = []
    for f in data["features"]:
        name = f["properties"].get("name", "")
        code = NAME_TO_CODE.get(name)
        if not code:
            missing.append(name)
            continue
        out.append({
            "type": "Feature",
            "properties": {"code": code, "name": name},
            "geometry": {"type": f["geometry"]["type"],
                         "coordinates": round_coords(f["geometry"]["coordinates"])},
        })

    if missing:
        # Loudly, rather than silently shipping a map with holes in it.
        print(f"WARNING: no USPS code for: {missing}", file=sys.stderr)

    dest = Path(__file__).resolve().parents[1] / "public" / "us-states.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": out},
                               separators=(",", ":")))
    print(f"wrote {dest} — {len(out)} states, {dest.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
