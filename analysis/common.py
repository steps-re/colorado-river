#!/usr/bin/env python3
"""Shared chrome for every page: one navigation bar, one figure treatment, one lightbox.

Three conventions had drifted across the site. Ten pages carried a nav bar, six a breadcrumb, and
five nothing at all, so a reader arriving from search on one of those five had no way in. Figures
were base64-embedded at full render resolution, which put 3.1 MB of images on a 9,000-word
homepage and meant nothing cached between pages.

This module is the single definition of both. Import it from every build_*.py.

    from common import nav, figure, HEAD_EXTRA

Figures reference a downscaled copy in figures/web/ (see analysis/make_web_figures.py) and link
the full-resolution original, so clicking any figure opens it at full detail.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "figures" / "web"
_MANIFEST = json.loads((WEB / "manifest.json").read_text()) if (WEB / "manifest.json").exists() else {}

GH = "https://github.com/steps-re/colorado-river"

# ---------------------------------------------------------------------------
# Navigation. Six destinations, not twenty-one links. Each group's siblings are
# surfaced by section() on the pages that belong to it, so the bar stays scannable
# while nothing becomes unreachable.
# ---------------------------------------------------------------------------
SECTIONS = [
    ("evidence", "The evidence", "technical.html", [
        ("technical.html", "Methodology"),
        ("records.html", "The priced record"),
        ("ee-measured.html", "Measured from orbit"),
        ("measured-conservation.html", "Measured conservation"),
        ("stakeholders.html", "Who is affected"),
    ]),
    ("fix", "The fix", "proposal.html", [
        ("proposal.html", "The proposal"),
        ("governance.html", "Law of the River"),
        ("post-2026.html", "After 2026"),
        ("manufactured-water.html", "Making water"),
        ("objections.html", "Objections answered"),
    ]),
    ("pays", "Who pays", "water-capital.html", [
        ("water-capital.html", "Where capital can go"),
        ("funders.html", "Who pays now"),
        ("data-centers.html", "Data centres"),
        ("aws.html", "The hyperscaler overlap"),
        ("coalition.html", "The coalition"),
    ]),
    ("solar", "Reservoir solar", "reservoir-solar-explorer.html", [
        ("reservoir-solar-explorer.html", "Coverage explorer"),
        ("reservoir-solar.html", "What the numbers say"),
        ("reservoir-solar-paper.html", "Technical paper"),
        ("reservoir-solar-method.html", "Methods and review"),
    ]),
]
_PAGE_SECTION = {p: sec for sec, _t, _l, pages in SECTIONS for p, _n in pages}


def nav(current=""):
    """The single navigation bar. `current` is a filename, used to mark the active section."""
    sec_of = _PAGE_SECTION.get(current, "")
    items = ['<a href="index.html" class="nb-home">Colorado River</a>',
             '<a href="start.html" class="nb-start">Start here</a>']
    for key, title, lead, _pages in SECTIONS:
        cls = ' class="on"' if key == sec_of else ""
        items.append(f'<a href="{lead}"{cls}>{title}</a>')
    items.append(f'<a href="{GH}" target="_blank" rel="noopener">Data &amp; code</a>')
    return ('<nav class="sitenav" aria-label="Site"><div class="nbwrap">'
            + "".join(items) + "</div></nav>")


def section(current):
    """The sibling strip for whichever section this page belongs to. Keeps every page one click
    from its neighbours without putting twenty-one links in the bar."""
    key = _PAGE_SECTION.get(current)
    if not key:
        return ""
    title, pages = next((t, p) for k, t, _l, p in SECTIONS if k == key)
    links = "".join(
        f'<a href="{href}"{" class=here" if href == current else ""}>{name}</a>'
        for href, name in pages)
    return f'<div class="secstrip"><span class="secttl">{title}</span>{links}</div>'


def figure(png, alt, caption="", cls=""):
    """A figure that loads light and expands to full resolution on click."""
    web = _MANIFEST.get(png, png)
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return (f'<figure class="fig {cls}">'
            f'<a href="figures/{png}" class="zoom" aria-label="Open full-resolution figure">'
            f'<img src="figures/web/{web}" alt="{alt}" loading="lazy" decoding="async">'
            f'<span class="zoomhint">Click to enlarge</span></a>{cap}</figure>')


HEAD_EXTRA = """
<style>
/* ---- shared chrome: navigation ---- */
.sitenav{position:sticky;top:0;z-index:40;background:var(--deep,#123137);
-webkit-backdrop-filter:saturate(140%) blur(6px);backdrop-filter:saturate(140%) blur(6px)}
.nbwrap{max-width:1100px;margin:0 auto;padding:0 16px;display:flex;flex-wrap:wrap;
align-items:center;gap:2px}
.sitenav a{display:inline-block;padding:11px 12px;color:#CFE0E2;text-decoration:none;
font-size:13.5px;line-height:1;border-bottom:2px solid transparent}
.sitenav a:hover{color:#fff;border-bottom-color:#3E8E9C}
.sitenav a.on{color:#fff;border-bottom-color:var(--rust,#A8432B);font-weight:600}
.sitenav a.nb-home{font-weight:700;color:#fff;padding-left:0}
.sitenav a.nb-start{color:#F0B49A}
.sitenav a:focus-visible{outline:2px solid #8FD3DE;outline-offset:-2px}
@media(max-width:640px){.sitenav a{padding:9px 8px;font-size:12.5px}}

/* ---- shared chrome: section strip ---- */
.secstrip{max-width:1100px;margin:0 auto;padding:9px 16px;display:flex;flex-wrap:wrap;
align-items:baseline;gap:4px 14px;border-bottom:1px solid var(--line,#C6BBA4);
background:var(--stone,#E7E1D4)}
.secttl{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted,#5B6A6A);
font-weight:700;margin-right:4px}
.secstrip a{font-size:13px;color:var(--water,#2C7A87);text-decoration:none}
.secstrip a:hover{text-decoration:underline}
.secstrip a.here{color:var(--deep,#123137);font-weight:700}

/* ---- shared chrome: figures ---- */
figure.fig{margin:1.5em 0;background:#fff;border:1px solid var(--line,#C6BBA4);
border-radius:6px;padding:10px}
figure.fig .zoom{display:block;position:relative;cursor:zoom-in}
figure.fig img{width:100%;max-width:100%;height:auto;display:block;border-radius:3px}
figure.fig .zoomhint{position:absolute;right:8px;bottom:8px;background:rgba(18,49,55,.82);
color:#fff;font-size:10.5px;letter-spacing:.04em;padding:3px 8px;border-radius:3px;opacity:0;
transition:opacity .15s;pointer-events:none}
figure.fig .zoom:hover .zoomhint,figure.fig .zoom:focus-visible .zoomhint{opacity:1}
figure.fig figcaption{font-size:12.5px;color:var(--muted,#5B6A6A);margin-top:8px;line-height:1.5}

/* ---- shared chrome: lightbox ---- */
#lbox{position:fixed;inset:0;z-index:100;background:rgba(10,22,25,.93);display:none;
align-items:center;justify-content:center;padding:24px;cursor:zoom-out}
#lbox.open{display:flex}
#lbox img{max-width:100%;max-height:100%;object-fit:contain;border-radius:4px;
box-shadow:0 12px 48px rgba(0,0,0,.5)}
#lbox .lbclose{position:absolute;top:14px;right:18px;color:#fff;background:none;border:0;
font-size:30px;line-height:1;cursor:pointer;padding:6px 12px}
#lbox .lbclose:focus-visible{outline:2px solid #8FD3DE}
@media (prefers-reduced-motion:reduce){figure.fig .zoomhint{transition:none}}
</style>
<script>
/* Click any figure to open the full-resolution original. Escape or click closes. */
document.addEventListener('DOMContentLoaded',function(){
  var box=document.createElement('div'); box.id='lbox';
  box.innerHTML='<button class="lbclose" aria-label="Close">&times;</button><img alt="">';
  document.body.appendChild(box);
  var img=box.querySelector('img');
  function close(){box.classList.remove('open');img.src='';document.body.style.overflow='';}
  box.addEventListener('click',close);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')close();});
  document.querySelectorAll('a.zoom').forEach(function(a){
    a.addEventListener('click',function(e){
      e.preventDefault();
      img.src=a.getAttribute('href');
      img.alt=(a.querySelector('img')||{}).alt||'';
      box.classList.add('open'); document.body.style.overflow='hidden';
      box.querySelector('.lbclose').focus();
    });
  });
});
</script>
"""
