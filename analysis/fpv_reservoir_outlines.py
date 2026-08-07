#!/usr/bin/env python3
"""Real reservoir shorelines -> normalized SVG paths for the coverage explorer.

The explorer's job is to make "3% coverage" feel as small as it actually is. A generic
blob would undersell that; a recognisable shoreline does not. So we pull the real water
polygon for each reservoir from OpenStreetMap (Overpass, public + keyless), simplify it,
and normalise it into a 0-1000 SVG viewBox that the page can fill to an arbitrary
coverage fraction.

Outputs: outputs/reservoir_outlines.json  {name: {path, viewBox, area_km2_osm, source}}
Public API, no keys, ZERO Claude tokens.
"""
import json, math, time, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"; OUT.mkdir(exist_ok=True)

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
CACHE = ROOT / "cache"; CACHE.mkdir(exist_ok=True)

# OSM relation/way ids resolved by name+bbox query below. We query by name within a bbox
# rather than hardcoding ids, so a re-run survives OSM id churn.
RESERVOIRS = {
    # name              south   west     north   east
    "Lake Mead":       (35.90, -114.95, 36.65, -113.95),
    "Lake Powell":     (36.75, -111.60, 38.05, -110.25),
    "Lake Mohave":     (35.00, -114.75, 35.95, -114.45),
    "Lake Havasu":     (34.25, -114.45, 34.80, -114.10),
    "Flaming Gorge":   (40.85, -110.00, 41.35, -109.30),
    "Navajo Reservoir": (36.75, -107.75, 37.15, -107.15),
    "Blue Mesa":       (38.40, -107.55, 38.60, -107.00),
}
# OSM name tags differ from our display names, and several of these water bodies are tagged
# under more than one common name. Try each in order.
OSM_NAME = {
    "Lake Mead": ["Lake Mead"],
    "Lake Powell": ["Lake Powell"],
    "Lake Mohave": ["Lake Mohave"],
    "Lake Havasu": ["Lake Havasu"],
    "Flaming Gorge": ["Flaming Gorge Reservoir", "Flaming Gorge"],
    "Navajo Reservoir": ["Navajo Lake", "Navajo Reservoir"],
    "Blue Mesa": ["Blue Mesa Reservoir", "Blue Mesa"],
}


def overpass(query, cache_key, rounds=3):
    """Query Overpass across mirrors with backoff, caching raw JSON so re-runs of this
    script (and the figure/site rebuilds downstream) never re-hammer a public API."""
    cf = CACHE / f"osm_{cache_key}.json"
    if cf.exists():
        print("  (cached)")
        return json.loads(cf.read_text())
    for rnd in range(rounds):
        for url in OVERPASS_MIRRORS:
            try:
                req = urllib.request.Request(
                    url,
                    data=urllib.parse.urlencode({"data": query}).encode(),
                    headers={"User-Agent": "steps-colorado-river/1.0 (research contact mike@stepsventures.com)"},
                )
                d = json.loads(urllib.request.urlopen(req, timeout=300).read())
                if d.get("elements"):
                    cf.write_text(json.dumps(d))
                    return d
                print(f"  {url.split('/')[2]}: 0 elements")
            except Exception as e:
                print(f"  {url.split('/')[2]}: {str(e)[:90]}")
            time.sleep(5)
        time.sleep(20 * (rnd + 1))
    return None


def fetch_polygon(display, bbox):
    """Return the largest closed ring (list of (lon,lat)) for the named water body."""
    s, w, n, e = bbox
    d = None
    for name in OSM_NAME[display]:
        q = f"""
        [out:json][timeout:150];
        (
          relation["natural"="water"]["name"="{name}"]({s},{w},{n},{e});
          way["natural"="water"]["name"="{name}"]({s},{w},{n},{e});
        );
        out geom;
        """
        key = display.lower().replace(" ", "_")
        if len(OSM_NAME[display]) > 1:
            key += "__" + name.lower().replace(" ", "_")
        d = overpass(q, key)
        if d and d.get("elements"):
            print(f"  matched OSM name '{name}'")
            break
    if not d or not d.get("elements"):
        return None
    rings = []
    for el in d["elements"]:
        if el["type"] == "way" and "geometry" in el:
            rings.append([(p["lon"], p["lat"]) for p in el["geometry"]])
        elif el["type"] == "relation":
            # stitch outer member ways into rings
            outers = [m for m in el.get("members", [])
                      if m.get("role") == "outer" and "geometry" in m]
            segs = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in outers]
            rings.extend(stitch(segs))
    if not rings:
        return None
    # largest by |shoelace| area
    rings.sort(key=lambda r: abs(shoelace(r)), reverse=True)
    return rings[0]


def stitch(segs, tol=1e-6):
    """Join way segments end-to-end into closed rings."""
    segs = [list(s) for s in segs if len(s) > 1]
    rings, cur = [], None
    while segs:
        if cur is None:
            cur = segs.pop(0)
        joined = False
        for i, s in enumerate(segs):
            if near(cur[-1], s[0], tol):
                cur += s[1:]; segs.pop(i); joined = True; break
            if near(cur[-1], s[-1], tol):
                cur += list(reversed(s))[1:]; segs.pop(i); joined = True; break
            if near(cur[0], s[-1], tol):
                cur = s[:-1] + cur; segs.pop(i); joined = True; break
            if near(cur[0], s[0], tol):
                cur = list(reversed(s))[:-1] + cur; segs.pop(i); joined = True; break
        if not joined:
            rings.append(cur); cur = None
    if cur:
        rings.append(cur)
    return rings


def near(a, b, tol):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def shoelace(ring):
    a = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i]; x2, y2 = ring[(i + 1) % len(ring)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def geo_area_km2(ring):
    """Spherical polygon area, km^2."""
    R = 6371.0088
    if len(ring) < 3:
        return 0.0
    total = 0.0
    for i in range(len(ring)):
        lon1, lat1 = map(math.radians, ring[i])
        lon2, lat2 = map(math.radians, ring[(i + 1) % len(ring)])
        total += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
    return abs(total * R * R / 2.0)


def _rdp_open(pts, eps):
    """Ramer-Douglas-Peucker on an OPEN polyline. Iterative: these rings run to 85k
    points and the recursive form overflows Python's stack."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        x1, y1 = pts[i0]; x2, y2 = pts[i1]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        dmax, idx = -1.0, -1
        for i in range(i0 + 1, i1):
            x0, y0 = pts[i]
            if norm < 1e-12:
                # degenerate baseline (endpoints coincide) -> use radial distance
                d = math.hypot(x0 - x1, y0 - y1)
            else:
                d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if d > dmax:
                dmax, idx = d, i
        if dmax > eps and idx > 0:
            keep[idx] = True
            stack.append((i0, idx)); stack.append((idx, i1))
    return [p for p, k in zip(pts, keep) if k]


def rdp(pts, eps):
    """RDP for a CLOSED ring.

    A ring's first and last point coincide, which makes the RDP baseline degenerate and
    collapses the whole shape to two points. So split the ring at the vertex farthest
    from its start, simplify the two halves as open polylines, and rejoin.
    """
    pts = list(pts)
    if len(pts) > 1 and near(pts[0], pts[-1], 1e-12):
        pts = pts[:-1]
    n = len(pts)
    if n < 4:
        return pts
    x0, y0 = pts[0]
    far = max(range(n), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
    a = _rdp_open(pts[:far + 1], eps)
    b = _rdp_open(pts[far:] + [pts[0]], eps)
    return a[:-1] + b[:-1]


def to_svg(ring, box=1000, pad=12):
    """Normalise a lon/lat ring into an SVG path in a square viewBox.

    Latitude is scaled by cos(lat) so the shape keeps its true aspect ratio
    (a plain lon/lat plot stretches these reservoirs east-west).
    """
    lat0 = sum(p[1] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    xs = [p[0] * k for p in ring]
    ys = [p[1] for p in ring]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    spanx, spany = (maxx - minx) or 1e-9, (maxy - miny) or 1e-9
    span = max(spanx, spany)
    scale = (box - 2 * pad) / span
    offx = pad + ((span - spanx) * scale) / 2.0
    offy = pad + ((span - spany) * scale) / 2.0
    pts = []
    for x, y in zip(xs, ys):
        px = offx + (x - minx) * scale
        py = box - (offy + (y - miny) * scale)   # SVG y grows downward
        pts.append(f"{px:.1f},{py:.1f}")
    return "M" + "L".join(pts) + "Z"


def parse_path(path):
    """SVG 'M x,y L x,y ... Z' -> [(x,y)]."""
    body = path.strip()[1:].rstrip("Zz")
    return [tuple(float(v) for v in seg.split(",")) for seg in body.split("L") if seg]


def row_widths(pts, box=1000, rows=3000):
    """Total x-extent of the polygon inside each horizontal 1-px row (ray casting)."""
    widths = []
    for r in range(rows):
        y = (r + 0.5) * box / rows
        xs = []
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]; x2, y2 = pts[(i + 1) % n]
            if (y1 <= y < y2) or (y2 <= y < y1):
                t = (y - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))
        xs.sort()
        w = sum(xs[i + 1] - xs[i] for i in range(0, len(xs) - 1, 2))
        widths.append(w)
    return widths


def coverage_bands(path, fractions, box=1000, rows=3000):
    """For each coverage fraction, the horizontal band [y0,y1] whose intersection with the
    reservoir polygon is exactly that fraction of the reservoir's area.

    Without this the shaded band is only a geometric guess: on a branched reservoir like Mead
    a band across the middle covers a wildly different share of the water than its height
    suggests, so the picture would overstate what a few percent of coverage looks like.
    """
    pts = parse_path(path)
    w = row_widths(pts, box, rows)
    total = sum(w)
    if total <= 0:
        return [[box / 2, box / 2] for _ in fractions]
    # grow outward from the area-weighted centre row
    cum = 0.0; centre = rows // 2
    for i, wi in enumerate(w):
        cum += wi
        if cum >= total / 2:
            centre = i; break
    rh = box / rows            # height of one scan row, in viewBox units
    bands = []
    for f in fractions:
        target = f * total
        lo = hi = centre
        got = w[centre]
        last_side, last_w = None, w[centre]
        while got < target and (lo > 0 or hi < rows - 1):
            # extend toward whichever side still has water
            down = w[lo - 1] if lo > 0 else -1
            up = w[hi + 1] if hi < rows - 1 else -1
            if up >= down and hi < rows - 1:
                hi += 1; got += w[hi]; last_side, last_w = "hi", w[hi]
            elif lo > 0:
                lo -= 1; got += w[lo]; last_side, last_w = "lo", w[lo]
            else:
                break
        y0, y1 = lo * rh, (hi + 1) * rh
        # Trim the last row back by the overshoot so the band's area matches the target
        # exactly. Whole-row steps alone are too coarse on narrow reservoirs like Blue Mesa.
        if last_side and last_w > 0 and got > target:
            trim = min(rh, (got - target) / last_w * rh)
            if last_side == "hi":
                y1 -= trim
            else:
                y0 += trim
        bands.append([round(y0, 2), round(y1, 2)])
    return bands


def main():
    out = {}
    fractions = [round(i * 0.0025, 4) for i in range(101)]   # 0 .. 25% in 0.25% steps
    for display, bbox in RESERVOIRS.items():
        print(f"{display} ...", flush=True)
        ring = fetch_polygon(display, bbox)
        if not ring:
            print("  NO POLYGON")
            continue
        area = geo_area_km2(ring)
        # simplify to a few hundred points: enough to stay recognisable, small enough to inline
        eps = 0.0006
        simp = rdp(ring, eps)
        while len(simp) > 420 and eps < 0.02:
            eps *= 1.5
            simp = rdp(ring, eps)
        svg_path = to_svg(simp)
        out[display] = {
            # simplified ring in lon/lat, so Earth Engine can measure water INSIDE each
            # reservoir's real footprint instead of inside a bounding box (Lake Mead's box
            # otherwise swallows the head of Lake Mohave below Hoover Dam)
            "ring_lonlat": [[round(x, 5), round(y, 5)] for x, y in simp],
            "path": svg_path,
            "viewBox": "0 0 1000 1000",
            "n_points": len(simp),
            "area_km2_osm": round(area, 1),
            "cov_step": 0.0025,
            "cov_bands": coverage_bands(svg_path, fractions),
            "source": "OpenStreetMap (Overpass), natural=water polygon; simplified (RDP)",
        }
        print(f"  {len(ring)} pts -> {len(simp)}, OSM area {area:.0f} km2")
        time.sleep(3)
    (OUT / "reservoir_outlines.json").write_text(json.dumps(out, indent=1))
    print(f"\nWROTE outputs/reservoir_outlines.json ({len(out)} reservoirs)")


if __name__ == "__main__":
    main()
