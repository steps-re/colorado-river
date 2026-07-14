#!/usr/bin/env python3
"""Basin 2.0 visuals folding in the Kloos framing: water batteries, the ~4 MAF portfolio,
the 0.1% insurance premium, and the coastal desal exchange. Output: figures/*.png"""
import os,sys,numpy as np
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from crstyle import apply,WATER,RUST,DEEP,SAND,STONE,PAPER,INK,LINE; apply()
FIG=Path(__file__).resolve().parent.parent/"figures"

# 1) WATER BATTERIES ---------------------------------------------------------
fig,ax=plt.subplots(figsize=(9,4.6))
bats=[("Lake Powell","24.3 MAF full",33),("Lake Mead","26.1 MAF full",34),
      ("Basin aquifers","-28 MAF since 2002",100)]  # aquifers: draw as draining
y=[2.4,1.2,0.0]; H=0.62
for (name,cap,pct),yy in zip(bats,y):
    ax.add_patch(FancyBboxPatch((0,yy),6,H,boxstyle="round,pad=0.02,rounding_size=0.06",
                 lw=1.4,ec=INK,fc="none",zorder=3))
    ax.add_patch(plt.Rectangle((6.02,yy+H*0.28),0.16,H*0.44,fc=INK,zorder=3))  # battery nub
    if name!="Basin aquifers":
        ax.add_patch(plt.Rectangle((0.06,yy+0.03),6*pct/100-0.06,H-0.06,
                     fc=RUST if pct<40 else WATER,alpha=.85,zorder=2))
        ax.text(6*pct/100+0.15,yy+H/2,f"{pct}% full",va="center",fontsize=10,color=RUST,fontweight="bold")
    else:
        for k in range(9):  # hatched draining
            ax.add_patch(plt.Rectangle((0.06+k*0.66,yy+0.03),0.5,H-0.06,fc=SAND,alpha=.30,zorder=2))
        ax.text(3.0,yy+H/2,"depleting — a slow drain on river flow",va="center",ha="center",fontsize=9.5,color="#7C5E19",fontweight="bold")
    ax.text(-0.15,yy+H/2,name,va="center",ha="right",fontsize=11,fontweight="bold",color=DEEP)
    ax.text(-0.15,yy-0.02,cap,va="top",ha="right",fontsize=7.5,color="#5B6A6A")
ax.set_xlim(-2.6,7.6); ax.set_ylim(-0.5,3.3); ax.axis("off")
ax.set_title("The water batteries are running low",fontsize=14,fontweight="bold",color=DEEP,loc="left")
ax.text(-2.6,-0.42,"Basin 2.0 goal: stop draining them, and intentionally rebuild the buffer.",fontsize=9,color="#5B6A6A")
plt.tight_layout(); plt.savefig(FIG/"water_batteries.png",dpi=140); plt.close()

# 2) THE ~4 MAF PORTFOLIO (levers stacked to Kloos's stabilization target) ----
levers=[("Compensated ag fallowing",1.30,400),("Ag efficiency / deficit irrig.",0.45,600),
        ("Municipal turf + leak reduction",0.40,700),("Advanced reuse (OCWD model)",0.80,1500),
        ("Brackish desal",0.35,1000),("Groundwater mgmt / ASR banking",0.40,500),
        ("Coastal seawater exchange",0.90,2800)]
names=[l[0] for l in levers]; vols=[l[1] for l in levers]; costs=[l[2] for l in levers]
fig,ax=plt.subplots(figsize=(10,5.2))
left=0
import matplotlib.colors as mc
cmap=mc.LinearSegmentedColormap.from_list("c",[WATER,SAND,RUST])
norm=mc.Normalize(300,3000)
for n,v,c in levers:
    ax.barh(0,v,left=left,color=cmap(norm(c)),ec="white",height=.6)
    if v>0.35: ax.text(left+v/2,0,f"{n}\n{v} MAF · ~${c}/AF",ha="center",va="center",fontsize=7.2,color="white" if c>1200 else INK)
    left+=v
ax.axvline(4.0,color=DEEP,ls="--",lw=1.4)
ax.text(4.0,0.42,"~4 MAF: full basin stabilization (Kloos)",ha="center",fontsize=8.5,color=DEEP)
ax.set_xlim(0,4.7); ax.set_ylim(-0.5,0.6); ax.set_yticks([])
ax.set_xlabel("Cumulative water freed or made (MAF/yr)")
ax.set_title(f"No single sector fixes it: a coordinated portfolio to ~4 MAF, avg ~$250–500/AF where it starts",fontsize=12,fontweight="bold",color=DEEP,loc="left")
sm=plt.cm.ScalarMappable(cmap=cmap,norm=norm); sm.set_array([])
cb=plt.colorbar(sm,ax=ax,orientation="horizontal",fraction=.05,pad=.28); cb.set_label("$ / acre-foot",fontsize=8)
plt.tight_layout(); plt.savefig(FIG/"portfolio_4maf.png",dpi=140); plt.close()

# 3) 0.1% INSURANCE PREMIUM ---------------------------------------------------
fig,ax=plt.subplots(figsize=(9,3.2))
ax.barh(0,1500,color=STONE,ec=INK,lw=1,height=.5)
ax.barh(0,1.5,color=RUST,ec=INK,lw=1,height=.5)
ax.text(1500/2,0,"$1.5 trillion / yr — basin economy, 16M jobs",ha="center",va="center",fontsize=11,color=INK,fontweight="bold")
ax.annotate("$1–2B / yr to stabilize\n(≈ 0.1% — an insurance premium)",xy=(2,0.02),xytext=(120,0.55),
            fontsize=10,color=RUST,fontweight="bold",ha="left",
            arrowprops=dict(arrowstyle="->",color=RUST,lw=1.4))
ax.set_xlim(-20,1560); ax.set_ylim(-0.6,0.9); ax.axis("off")
ax.set_title("Stabilizing the river costs about 0.1% of what it protects",fontsize=13,fontweight="bold",color=DEEP,loc="left")
plt.tight_layout(); plt.savefig(FIG/"insurance_premium.png",dpi=140); plt.close()

# 4) COASTAL DESAL EXCHANGE ---------------------------------------------------
fig,ax=plt.subplots(figsize=(10,3.4))
def box(x,y,w,h,txt,fc):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.02,rounding_size=0.05",fc=fc,ec=INK,lw=1.2,zorder=2))
    ax.text(x+w/2,y+h/2,txt,ha="center",va="center",fontsize=8.6,color=INK if fc!=DEEP else "white",zorder=3)
box(0.2,1.0,2.2,0.9,"Coalition + partners\nfund coastal desal\n(from outside CA)",PAPER)
box(3.0,1.0,2.2,0.9,"Seawater desal on\nCA / Baja coast\n1–2 MAF/yr",WATER)
box(5.8,1.0,2.2,0.9,"CA coastal cities\ntake desal water,\ncut river diversion",PAPER)
box(8.0,1.0,1.8,0.9,"Freed Colorado\nRiver water stays\nin Mead / AZ+NV",DEEP)
for x0,x1 in [(2.4,3.0),(5.2,5.8),(8.0,8.0-0.0)]:
    pass
for x0,x1 in [(2.4,3.0),(5.2,5.8),(8.0,8.0)]:
    ax.add_patch(FancyArrowPatch((x0,1.45),(x1,1.45),arrowstyle="-|>",mutation_scale=16,color=RUST,lw=1.6,zorder=4))
ax.add_patch(FancyArrowPatch((7.8,1.45),(8.0,1.45),arrowstyle="-|>",mutation_scale=16,color=RUST,lw=1.6))
ax.set_xlim(0,10); ax.set_ylim(0.4,2.4); ax.axis("off")
ax.set_title("The desal exchange: fund the coast, free the river",fontsize=13,fontweight="bold",color=DEEP,loc="left")
ax.text(0.2,0.55,"A dollar of coastal desalination funded from outside California frees an acre-foot of Colorado River water inland.",fontsize=8.5,color="#5B6A6A")
plt.tight_layout(); plt.savefig(FIG/"desal_exchange.png",dpi=140); plt.close()

print("wrote: water_batteries, portfolio_4maf, insurance_premium, desal_exchange")
