# -*- coding: utf-8 -*-
"""UAT for continuous-beam EXACT analysis (Three-Moment + point loads · Session 3C).
Coefficient (3A) method removed per Nu 2026-05-29 → exact analysis only.
Ground truth (closed-form):
  2 equal spans UDL  -> M_B = -wL²/8 · R_A=3wL/8 · R_B=5wL/4 · +M=9wL²/128
  3 equal spans UDL  -> M_int = -wL²/10
  2 equal spans, central P each span -> M_B = -3PL/16
"""
import sys, io, importlib.util
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
_CALC_PATH = Path(__file__).resolve().parent / "calc.py"
spec = importlib.util.spec_from_file_location("calc", str(_CALC_PATH))
calc = importlib.util.module_from_spec(spec); sys.modules["calc"] = calc; spec.loader.exec_module(calc)
SI, PL = calc.SpanInput, calc.PointLoad

PASS, FAIL = [], []
def chk(name, got, exp, tol):
    ok = abs(got-exp) <= tol; (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got:.4f} exp={exp:.4f}")
def chk_true(name, c, d=""):
    (PASS if c else FAIL).append(name); print(f"  [{'PASS' if c else 'FAIL'}] {name} {d}")

L, w = 5.0, 40.0
print("="*64); print("A · solver vs textbook closed-form"); print("="*64)
chk("2span UDL M_B=-wL²/8", calc.solve_three_moment([L,L],[w,w])[1], -w*L*L/8, 0.01)
m3 = calc.solve_three_moment([L,L,L],[w,w,w])
chk("3span UDL M_int=-wL²/10", m3[1], -w*L*L/10, 0.01)
Pp = 30.0
ms = calc.solve_continuous_moments([L,L],[0,0],[[(Pp,L/2)],[(Pp,L/2)]])
chk("2span central P each -> M_B=-3PL/16", ms[1], -3*Pp*L/16, 0.01)

print("="*64); print("B · full design + reactions + diagram"); print("="*64)
DL = w/1.2
o = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30,h=60,fc=240,fy=4000,
    spans=[SI(L,DL,0,[]),SI(L,DL,0,[])]))
chk("2span R_A=3wL/8", o["reactions"][0]["R_kN"], 3*w*L/8, 0.1)
chk("2span R_B=5wL/4", o["reactions"][1]["R_kN"], 5*w*L/4, 0.1)
chk("2span +M=9wL²/128", o["spans"][0]["M_pos_kNm"], 9*w*L*L/128, 0.1)
chk_true("diagram arrays present (x/V/M)",
         len(o["diagram"]["x"])>40 and len(o["diagram"]["V_ton"])==len(o["diagram"]["x"])
         and len(o["diagram"]["M_tonm"])==len(o["diagram"]["x"]),
         f"({len(o['diagram']['x'])} samples)")
chk_true("node_x + span_loads present", len(o["node_x"])==3 and len(o["span_loads"])==2)
chk_true("passes", o["passes"])

print("="*64); print("C · point loads + unequal spans"); print("="*64)
ou = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30,h=60,fc=240,fy=4000,
    spans=[SI(6.0,DL,0,[]), SI(3.0,DL,0,[PL("LL",50.0,1.5)]), SI(5.0,DL,0,[])]))
chk_true("unequal+point solves (4 support moments)", len(ou["support_moments_tonm"])==4,
         f"(M t·m={ou['support_moments_tonm']})")
chk_true("point load reflected in span_loads",
         any(sl["points"] for sl in ou["span_loads"]),
         f"(span_loads={[len(s['points']) for s in ou['span_loads']]})")
chk_true("notation count×size (no '@')",
         all("@" not in s["bottom_bars"] for s in ou["spans"]))

print("="*64); print("D · guard <2 spans"); print("="*64)
try:
    calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30,h=60,fc=240,fy=4000,spans=[SI(5,DL,0,[])]))
    chk_true("guard <2 spans", False, "(no raise)")
except calc.ContinuousConditionError:
    chk_true("guard <2 spans raises", True)

print("="*64); print("E · cantilever (overhang) · closed-form"); print("="*64)
KNM, KN = calc.KNM_TO_TONM, calc.KN_TO_TON
Lc, wc = 2.0, 30.0; DLc = wc/1.2
# E1 · LEFT overhang UDL → M_A = -w·Lc²/2 (known boundary · exact)
oL = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30,h=60,fc=240,fy=4000,
    spans=[SI(L,DL,0,[]),SI(L,DL,0,[])],
    left_cantilever={"L":Lc,"DL":DLc,"LL":0,"point_loads":[]}))
chk("cantL UDL: M_A=-wLc²/2", oL["support_moments_tonm"][0], -wc*Lc*Lc/2*KNM, 0.02)
chk("cantL UDL: Vu_face=w·Lc", oL["cantilevers"][0]["Vu_face_ton"], wc*Lc*KN, 0.02)
chk_true("cantL: 1 row + เหล็กบน", len(oL["cantilevers"])==1 and oL["cantilevers"][0]["top_bars"]!="—",
         f"({oL['cantilevers'][0]['top_bars']})")
chk_true("cantL: diagram x extends negative (overhang)", min(oL["diagram"]["x"]) <= -Lc+0.01,
         f"(x_min={min(oL['diagram']['x'])})")
# E2 · LEFT overhang single point @ tip → M_A = -Pu·Lc · Vu=Pu
Praw = 40.0; Pu = 1.2*Praw
oP = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30,h=60,fc=240,fy=4000,
    spans=[SI(L,DL,0,[]),SI(L,DL,0,[])],
    left_cantilever={"L":Lc,"DL":0,"LL":0,"point_loads":[{"kind":"DL","P":Praw,"x":Lc}]}))
chk("cantL point@tip: M_A=-Pu·Lc", oP["support_moments_tonm"][0], -(Pu*Lc)*KNM, 0.02)
chk("cantL point@tip: Vu_face=Pu", oP["cantilevers"][0]["Vu_face_ton"], Pu*KN, 0.02)
# E3 · RIGHT overhang UDL → M at last support = -w·Lc²/2 (symmetry)
oR = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30,h=60,fc=240,fy=4000,
    spans=[SI(L,DL,0,[]),SI(L,DL,0,[])],
    right_cantilever={"L":Lc,"DL":DLc,"LL":0,"point_loads":[]}))
chk("cantR UDL: M_C=-wLc²/2", oR["support_moments_tonm"][-1], -wc*Lc*Lc/2*KNM, 0.02)
chk_true("cantR: diagram x extends past total_L", max(oR["diagram"]["x"]) >= oR["total_L"]+Lc-0.01,
         f"(x_max={max(oR['diagram']['x'])}, total_L={oR['total_L']})")
# E4 · equilibrium ΣR = ΣW (spans UDL + cantilever UDL)
sumR = sum(r["R_kN"] for r in oL["reactions"]); sumW = w*L*2 + wc*Lc
chk("cantL equilibrium ΣR=ΣW", sumR, sumW, 0.5)
# E5 · regression: no-cantilever case unchanged (empty list + flag False)
chk_true("no-cant: empty cantilevers + flag False", len(o["cantilevers"])==0 and o["has_cantilever"] is False)
# E6 · deep cantilever → min-depth Lc/8 advisory fires (h=60 < 6.0/8·100=75)
oMD = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30,h=60,fc=240,fy=4000,
    spans=[SI(L,DL,0,[]),SI(L,DL,0,[])],
    left_cantilever={"L":6.0,"DL":DLc,"LL":0,"point_loads":[]}))
chk_true("cantL deep: min_depth_ok=False (h<Lc/8)", oMD["cantilevers"][0]["min_depth_ok"] is False,
         f"(h_min={oMD['cantilevers'][0]['h_min_cm']})")
# E7 · Ld helper validated vs DRMK Ex 8.2 (DB25 top, f'c=240, fy=4000 → 159.4 cm)
chk("Ld DRMK Ex8.2 (DB25 top)", calc.dev_length_top_tension_cm(2.5, 4000, 240), 159.4, 0.6)

print("\n" + "="*64)
print(f"RESULT: {len(PASS)} PASS / {len(FAIL)} FAIL", "| ALL GREEN" if not FAIL else "| FAIL: "+", ".join(FAIL))
print("="*64)

sys.exit(1 if FAIL else 0)
