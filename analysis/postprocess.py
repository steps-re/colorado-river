#!/usr/bin/env python3
"""Apply the shared chrome to every built page, in one pass.

Editing eighteen build scripts by hand to add a nav bar and change image handling is how the
three competing conventions happened in the first place. This runs after all of them and makes
one transformation, so the site cannot drift again:

  1. base64-embedded images  ->  external files, downscaled inline, full-res behind a click
  2. whatever navigation the page had  ->  the one nav bar, plus a sibling strip for its section
  3. injects the shared stylesheet and the lightbox

Run: python3 site/postprocess.py   (after the build_*.py scripts)
"""
import base64, hashlib, json, re, sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
FIG = ROOT / "figures"
sys.path.insert(0, str(SITE))
from common import nav, section, HEAD_EXTRA, _MANIFEST  # noqa: E402

SKIP = {"bankable-water.html"}          # a redirect stub, deliberately bare


def figure_index():
    """md5 of each figure's base64 payload -> filename, so embedded images can be traced back
    to the file that produced them."""
    idx = {}
    for f in FIG.glob("*.png"):
        b64 = base64.b64encode(f.read_bytes()).decode()
        idx[hashlib.md5(b64.encode()).hexdigest()] = f.name
    return idx


IMG_RE = re.compile(
    r'<img\b([^>]*?)src=["\']data:image/(?:png|jpe?g|webp);base64,([A-Za-z0-9+/=]+)["\']([^>]*?)>',
    re.I)
NAV_RE = re.compile(r'<nav(?![^>]*class=["\']?toc)[^>]*>.*?</nav>', re.I | re.S)
CRUMB_RE = re.compile(r'<div class=["\']?crumb["\']?[^>]*>.*?</div>', re.I | re.S)


def alt_of(attrs):
    m = re.search(r'alt=["\'](.*?)["\']', attrs, re.I)
    return m.group(1) if m else ""


def process(path, idx):
    html = path.read_text(encoding="utf-8", errors="replace")
    before = len(html)
    name = path.name
    stats = {"imgs": 0, "unmatched": 0}

    # ---- 1. embedded images -> external, with click-to-expand ----
    def repl(m):
        pre, payload, post = m.group(1), m.group(2), m.group(3)
        h = hashlib.md5(payload.encode()).hexdigest()
        src = idx.get(h)
        if not src:
            stats["unmatched"] += 1
            return m.group(0)                     # leave anything we cannot trace
        stats["imgs"] += 1
        web = _MANIFEST.get(src, src)
        alt = alt_of(pre + post)
        return (f'<a href="figures/{src}" class="zoom" aria-label="Open full-resolution figure">'
                f'<img src="figures/web/{web}" alt="{alt}" loading="lazy" decoding="async">'
                f'<span class="zoomhint">Click to enlarge</span></a>')

    html = IMG_RE.sub(repl, html)

    # ---- 2. one navigation ----
    html = NAV_RE.sub("", html, count=1)          # drop whatever bar the page had
    html = CRUMB_RE.sub("", html, count=1)        # and any breadcrumb
    chrome = nav(name) + section(name)
    if re.search(r"<body[^>]*>", html, re.I):
        html = re.sub(r"(<body[^>]*>)", r"\1" + chrome, html, count=1, flags=re.I)
    else:
        html = chrome + html

    # ---- 3. shared stylesheet + lightbox ----
    if "id='lbox'" not in html and 'id="lbox"' not in html:
        if re.search(r"</head>", html, re.I):
            html = re.sub(r"</head>", HEAD_EXTRA + "</head>", html, count=1, flags=re.I)
        else:
            html = HEAD_EXTRA + html

    path.write_text(html, encoding="utf-8")
    return before, len(html), stats


def main():
    idx = figure_index()
    print(f"traced {len(idx)} source figures\n")
    tb = ta = 0
    print(f"{'page':34} {'before':>9} {'after':>9} {'saved':>7}  imgs")
    for p in sorted(SITE.glob("*.html")):
        if p.name in SKIP:
            continue
        b, a, st = process(p, idx)
        tb += b; ta += a
        pct = f"{100 - a * 100 // max(b, 1)}%" if b > a else "-"
        warn = f"  ({st['unmatched']} untraced)" if st["unmatched"] else ""
        print(f"  {p.name:32} {b//1024:>7}K {a//1024:>7}K {pct:>7}  {st['imgs']}{warn}")
    print(f"\nsite total: {tb//1024:,} KB -> {ta//1024:,} KB "
          f"({100 - ta * 100 // max(tb, 1)}% smaller)")
    print("figures now cache across pages instead of re-downloading per page")


if __name__ == "__main__":
    main()
