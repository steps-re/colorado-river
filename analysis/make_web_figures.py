#!/usr/bin/env python3
"""Downscale figures for inline display, keeping the originals for click-to-expand.

The site embedded every figure as base64 at full render resolution, so the homepage carried
3.1 MB of images for 9,000 words and nothing cached between pages. Figures are rendered up to
2,374 px wide and displayed at about 840, so most of those bytes were never visible.

This writes a display-size copy to figures/web/. Pages reference the web copy inline and link the
original for the lightbox, so detail is still one click away rather than lost.

Outputs: figures/web/*.png (and .webp where it wins)
"""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
WEB = FIG / "web"
WEB.mkdir(exist_ok=True)

# Displayed at ~840 px in an 840-960 px column. 1,400 px keeps a retina-sharp 1.5x without
# carrying the full render.
TARGET_W = 1400


def encode_best(im, stem):
    """Try several encodings and keep the smallest. Matplotlib already palette-optimises line
    charts, so a naive RGB re-encode makes them BIGGER. Charts quantise well to a palette;
    map rasters do better as lossy WebP. Rather than guess per file, try both and measure."""
    cands = []

    # palette PNG: excellent for line art, terrible for photographic rasters
    try:
        q = im.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)
        f = WEB / f"{stem}.png"
        q.save(f, "PNG", optimize=True)
        cands.append((f.stat().st_size, f, "png256"))
    except Exception:
        pass

    # lossless webp: usually beats PNG on charts
    f = WEB / f"{stem}.webp"
    im.convert("RGB").save(f, "WEBP", lossless=True, quality=100, method=6)
    cands.append((f.stat().st_size, f, "webp-lossless"))

    # lossy webp at high quality: wins big on anything map-like
    f2 = WEB / f"{stem}.q90.webp"
    im.convert("RGB").save(f2, "WEBP", quality=90, method=6)
    cands.append((f2.stat().st_size, f2, "webp-q90"))

    cands.sort()
    best_size, best_file, kind = cands[0]
    final = WEB / f"{stem}{best_file.suffix}"
    if best_file != final:
        best_file.replace(final)
    for _, f, _k in cands:                       # drop the losers
        if f.exists() and f != final:
            f.unlink()
    return final, best_size, kind


def main():
    rows = []
    for src in sorted(FIG.glob("*.png")):
        im = Image.open(src)
        w, h = im.size
        if w > TARGET_W:
            im = im.resize((TARGET_W, round(h * TARGET_W / w)), Image.LANCZOS)
        out, after, kind = encode_best(im, src.stem)
        before = src.stat().st_size
        rows.append((src.name, before, after, w, im.size[0], out.name, kind))

    tb = sum(r[1] for r in rows); ta = sum(r[2] for r in rows)
    import json
    (WEB / "manifest.json").write_text(json.dumps(
        {r[0]: r[5] for r in rows}, indent=1))
    print(f"{'figure':34} {'was':>7} {'now':>7} {'px':>12}  encoding")
    for n, b, a, w0, w1, on, kind in sorted(rows, key=lambda r: -r[1])[:12]:
        print(f"  {n[:32]:32} {b//1024:>5}K {a//1024:>5}K {w0:>5}->{w1:<5} {kind}")
    print(f"\n{len(rows)} figures: {tb//1024:,} KB -> {ta//1024:,} KB "
          f"({100 - ta * 100 // max(tb, 1)}% smaller)")
    print("originals kept in figures/ for click-to-expand; manifest at figures/web/manifest.json")


if __name__ == "__main__":
    main()
