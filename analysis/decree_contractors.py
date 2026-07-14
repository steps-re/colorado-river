#!/usr/bin/env python3
"""Full contractor-level consumptive-use table from the LC Decree Accounting Reports (2020-2024).
Walks each state table (Arizona/California/Nevada), tracks each water user, and captures the annual
Consumptive Use for every contractor. Output: outputs/decree_contractors.csv + .json"""
import re,json,csv,os
from pathlib import Path
import pdfplumber
ROOT=Path(__file__).resolve().parent.parent; OUT=ROOT/"outputs"
years=[2020,2021,2022,2023,2024]
ROWKW=("Diversion","Measured Returns","Unmeasured Returns","Consumptive Use","Delivery","Sum of",
       "Diverted from","Pumped from","Total ","Net ","Less","Plus","Adjustment","Storage")
def lastnum(s):
    # last numeric token, handle (neg) and commas
    toks=re.findall(r'\(?-?[\d,]+\)?',s)
    vals=[]
    for t in toks:
        neg=t.startswith("(")
        t2=t.strip("()").replace(",","")
        if t2.isdigit(): vals.append(-int(t2) if neg else int(t2))
    return vals[-1] if vals else None
def is_user_header(ln):
    s=ln.strip()
    if not s or len(s)<3: return False
    if any(s.startswith(k) for k in ROWKW): return False
    if re.match(r'^(Table|WATER USER|Footnotes|State of|\d+$)',s): return False
    # header = mostly letters, ends without a big number column
    letters=sum(c.isalpha() for c in s)
    if letters<3: return False
    # a header line typically has no 4+ digit numbers
    if re.search(r'\d{4,}',s): return False
    return True
rows={}  # (state,user) -> {year: cu}
for y in years:
    fp=ROOT/f"data/lcras/decree/{y}.pdf"
    if not fp.exists(): continue
    state=None; user=None
    with pdfplumber.open(fp) as pdf:
        for p in pdf.pages:
            t=p.extract_text() or ""
            m=re.search(r'State of (Arizona|California|Nevada)',t)
            for ln in t.splitlines():
                sm=re.search(r'Table \d+\.\s*State of (Arizona|California|Nevada)',ln)
                if sm: state=sm.group(1); user=None; continue
                if state is None: continue
                low=ln.lower()
                # state totals line
                if re.match(rf'\s*{state} Totals',ln) or ln.strip()==f"{state} Totals":
                    user=f"** {state} TOTAL **"; continue
                if is_user_header(ln):
                    user=ln.strip(); continue
                # capture Consumptive Use annual
                if ("consumptive use" in low) and user:
                    # "Total X Consumptive Use" -> use X as the user label
                    tm=re.search(r'Total (.+?) Consumptive Use',ln)
                    label=("Total "+tm.group(1)).strip() if tm else user
                    v=lastnum(ln.split("Consumptive Use")[-1])
                    if v is not None and abs(v)>0:
                        key=(state,label)
                        rows.setdefault(key,{})[y]=v
# write outputs
recs=[]
for (state,user),ys in sorted(rows.items(),key=lambda x:(x[0][0],-max(x[1].values()))):
    if max(abs(v) for v in ys.values())<50: continue   # drop trivial noise
    recs.append({"state":state,"user":user,**{str(y):ys.get(y,"") for y in years}})
with open(OUT/"decree_contractors.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["state","user"]+[str(y) for y in years]); w.writeheader()
    for r in recs: w.writerow(r)
(OUT/"decree_contractors.json").write_text(json.dumps(recs,indent=2))
print(f"extracted {len(recs)} contractor rows across {len(years)} years")
# show the big ones per state
for st in ["Arizona","California","Nevada"]:
    print(f"\n== {st} — top users by 2023 CU ==")
    sub=[r for r in recs if r["state"]==st and r["2023"] not in ("",None)]
    for r in sorted(sub,key=lambda r:-(r["2023"] if isinstance(r["2023"],int) else 0))[:12]:
        print(f"   {r['user'][:44]:44} {r.get('2023',''):>10}")

# ---- CLEAN PASS: drop accounting artifacts, dedup, reconcile to state totals ----
EXCLUDE=re.compile(r'conserved water|system conservation|lower division|mod return|^return|adjustment|'
                   r'delivery from|storage|^net |^less|^plus|intentionally created|ics|bank',re.I)
state_tot={}
for r in recs:
    if r["user"].startswith("** ") :
        for y in years:
            if isinstance(r.get(str(y)),int): state_tot[(r["state"],y)]=r[str(y)]
clean=[]
for r in recs:
    u=r["user"]
    if u.startswith("** "): clean.append(r); continue
    if EXCLUDE.search(u): continue
    # drop cross-contaminated rows (>= state total) and require plausible magnitude
    keep=dict(r); ok=False
    for y in years:
        v=r.get(str(y))
        if isinstance(v,int):
            st=state_tot.get((r["state"],y))
            if st and abs(v)>=0.98*st: keep[str(y)]=""   # contamination
            elif abs(v)>=50: ok=True
    if ok: clean.append(keep)
# dedup: if "Total X" and "X" both present, keep Total X
bytotal={}
for r in clean:
    base=re.sub(r'^Total ','',r["user"]).strip()
    bytotal.setdefault((r["state"],base),[]).append(r)
final=[]
for (st,base),grp in bytotal.items():
    if len(grp)>1:
        tot=[g for g in grp if g["user"].startswith("Total ")]
        final.append(tot[0] if tot else max(grp,key=lambda g:max((v for v in [g.get(str(y)) for y in years] if isinstance(v,int)),default=0)))
    else: final.append(grp[0])
final.sort(key=lambda r:(r["state"],-(r["2023"] if isinstance(r.get("2023"),int) else 0)))
with open(OUT/"decree_contractors_clean.csv","w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["state","user"]+[str(y) for y in years]); w.writeheader()
    for r in final: w.writerow({k:r.get(k,"") for k in ["state","user"]+[str(y) for y in years]})
# reconcile
print("\n=== RECONCILIATION: sum of cleaned contractors vs state total (2023) ===")
for st in ["Arizona","California","Nevada"]:
    s=sum(r["2023"] for r in final if r["state"]==st and isinstance(r.get("2023"),int) and not r["user"].startswith("** "))
    tot=state_tot.get((st,2023))
    print(f"  {st}: contractors sum {s:,} vs total {tot:,}  ({100*s/tot:.0f}%)  [{sum(1 for r in final if r['state']==st and not r['user'].startswith('** '))} users]")
print(f"\n[done] outputs/decree_contractors_clean.csv ({sum(1 for r in final if not r['user'].startswith('** '))} contractors)")
