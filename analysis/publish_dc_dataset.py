#!/usr/bin/env python3
"""Publish the data-centre scoreboard's underlying data to the public repo.

The site's nav says "Data & code" and the scoreboard's methods section says every figure is either
linked to a primary source or is a labelled estimate built on a stated method. But all 31 sites,
their costed projects, water models and permit matches came from research/dc_out/, which is
gitignored by design and had never been published. A reader could not check any of it.

What is published: the dataset and every derived file the page actually renders.
What is not, and why:
  ideas_*.md      per-operator project menus. The page renders the five headlines from each; the
                  bodies are business-development material, not analysis.
  costing_raw/    intermediate per-site scratch, superseded by costing.json.
  email addresses stripped from sewer_permits.json. They are public agency intake mailboxes
                  rather than personal addresses, but this repo does not publish contact details
                  anywhere else and there is no reason to start here.

Run: python3 analysis/publish_dc_dataset.py
Output: ../colorado-river-public/data/dc/*.json
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "research" / "dc_out"
DEST = ROOT.parent / "colorado-river-public" / "data" / "dc"

PUBLISH = ["dc_dataset.json", "costing.json", "water_model.json", "water_verify.json",
           "echo_permits.json", "sewer_permits.json", "coords_final.json", "water_geo.json"]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

if not SRC.exists():
    raise SystemExit(f"[dc-publish] {SRC} not found; nothing to publish")
DEST.mkdir(parents=True, exist_ok=True)

redacted_total, written = 0, []
for name in PUBLISH:
    src = SRC / name
    if not src.exists():
        print(f"[dc-publish] SKIP {name}: not present", file=sys.stderr)
        continue
    blob = src.read_text()
    n = len(EMAIL.findall(blob))
    if n:
        blob = EMAIL.sub("[email removed]", blob)
        redacted_total += n
    # reparse, so a redaction can never ship a file that is no longer valid JSON
    json.loads(blob)
    (DEST / name).write_text(blob)
    written.append((name, len(blob) // 1024, n))

manifest = {
    "what": "Underlying data for the Colorado River data-centre site scoreboard "
            "(site/data-center-sites.html)",
    "generated_by": "analysis/publish_dc_dataset.py",
    "files": {n: {"kb": kb, "emails_redacted": e} for n, kb, e in written},
    "withheld": {
        "ideas_*.md": "per-operator project menus; the page renders the five headlines from each, "
                      "the bodies are business-development material rather than analysis",
        "costing_raw/": "intermediate per-site scratch, superseded by costing.json"},
    "note": "Email addresses are stripped. They were public agency intake mailboxes, not personal "
            "addresses; this repository does not publish contact details anywhere else."}
(DEST / "README.json").write_text(json.dumps(manifest, indent=2))

for n, kb, e in written:
    print(f"[dc-publish] {n:24} {kb:>4} KB" + (f"  ({e} emails redacted)" if e else ""))
print(f"[dc-publish] wrote {len(written)} files + README.json to {DEST}, "
      f"{redacted_total} email addresses redacted")
