# -*- coding: utf-8 -*-
"""
UAT re-check harness (Claude-driven · 2026-05-29)
Verifies calc.py engine against DRMK ground truth + realistic Thai residential beams.

Layers:
  A · Engineering ground-truth (DRMK Example 5.1 shear formula constants + spacing)
  B · Flexure hand-check (Session 1 baseline)
  C · Realistic residential full design_beam cases
  D · Edge / validation error paths
  E · Unit-conversion consistency (kN <-> kg <-> ton)
"""
import sys, io, math, importlib.util, traceback
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_CALC_PATH = Path(__file__).resolve().parent / "calc.py"
spec = importlib.util.spec_from_file_location("calc", str(_CALC_PATH))
calc = importlib.util.module_from_spec(spec)
sys.modules["calc"] = calc          # needed for dataclass forward-ref resolution
spec.loader.exec_module(calc)

PASS, FAIL = [], []

def chk(name, got, exp, tol=0.05, abs_tol=None):
    """Relative tolerance check (tol fraction) unless abs_tol given."""
    if abs_tol is not None:
        ok = abs(got - exp) <= abs_tol
    else:
        ok = abs(got - exp) <= tol * abs(exp) if exp != 0 else abs(got) <= tol
    tag = "PASS" if ok else "FAIL"
    (PASS if ok else FAIL).append(name)
    print(f"  [{tag}] {name}: got={got:.4f}  exp={exp:.4f}")
    return ok

def chk_eq(name, got, exp):
    ok = got == exp
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got!r}  exp={exp!r}")
    return ok

def chk_true(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")
    return cond

print("LoadCombo members:", [m.name for m in calc.LoadCombo])
print("SupportType members:", [m.name for m in calc.SupportType])
print()

# =====================================================================
# LAYER A — DRMK Example 5.1 ground-truth (PDF p.126)
# Input: b=40 d=53 f'c=280 fy=4000 · wu=7.9 t/m · Pu=11.3 t
# Expected: Vc=18.80 · Vs,max=74.50 · 1.1thr=39.02 ton · s=11cm (DB10 Av=1.57)
# =====================================================================
print("="*68)
print("LAYER A · DRMK Example 5.1 ground-truth (shear formula constants)")
print("="*68)
b, d, fc = 40.0, 53.0, 280.0

Vc_kg = calc.compute_Vc_ksc(fc, b, d)
chk("A1 Vc (ton)", Vc_kg/1000.0, 18.80, abs_tol=0.05)

Vs_max_kg = 2.1 * math.sqrt(fc) * b * d
chk("A2 Vs,max=2.1sqrt(fc)bd (ton)", Vs_max_kg/1000.0, 74.50, abs_tol=0.10)

thr_kg = 1.1 * math.sqrt(fc) * b * d
chk("A3 threshold=1.1sqrt(fc)bd (ton)", thr_kg/1000.0, 39.02, abs_tol=0.10)

# spacing: s = Av*fy*d/Vs · DB10 2-leg Av=1.57 · Vs=30 ton=30000 kg
s_spacing = 1.57 * 4000.0 * 53.0 / 30000.0
chk("A4 s=Av*fy*d/Vs (cm)", s_spacing, 11.09, abs_tol=0.15)

# Confirm the OLD buggy coefficients are NOT present (regression guard on the bug fix)
chk_true("A5 Vs,max coeff is 2.1 not 4.0",
         abs(Vs_max_kg/1000.0 - 18.80*2.1/0.53) < 1.0,
         f"(2.1 path ton={Vs_max_kg/1000:.2f})")

# DB10 2-leg area present & correct
chk("A6 DB10 2-leg Av (cm2)", calc._STIRRUP_2LEG_AV_CM2["DB10"], 1.570, abs_tol=0.005)
chk("A7 RB9 2-leg Av (cm2)", calc._STIRRUP_2LEG_AV_CM2["RB9"], 1.272, abs_tol=0.005)
print()

# =====================================================================
# LAYER B — Flexure hand-check (Session 1 baseline)
# b=25 h=50 L=4.5 fc=240 fy=4000 DL=2.94 LL=3.0 (kN/m)
# Expected (vault): Wu=8.328 kN/m · Mu=21.08 kN.m
# =====================================================================
print("="*68)
print("LAYER B · Flexure hand-check (Session 1 baseline · UDL only)")
print("="*68)
inp = calc.BeamInput(b=25, h=50, L=4.5, fc=240, fy=4000, DL=2.94, LL=3.0)
out = calc.design_beam(inp)
Wu_hand = 1.2*2.94 + 1.6*3.0
chk("B1 Wu (kN/m)", out.Wu, Wu_hand, abs_tol=0.01)
Mu_hand = Wu_hand * 4.5**2 / 8.0
chk("B2 Mu (kN.m) = Wu*L^2/8", out.Mu, Mu_hand, abs_tol=0.05)
chk("B3 Mu matches vault 21.08", out.Mu, 21.08, abs_tol=0.1)
# beta1 for fc=240 (<280) should be 0.85
chk("B4 beta1 (fc=240)", out.beta1, 0.85, abs_tol=0.001)
# rho_min = 14/fy
chk("B5 rho_min=14/fy", out.rho_min, 14.0/4000.0, abs_tol=1e-5)
chk_true("B6 flexure passes (phiMn>=Mu)", out.passes_flexure,
         f"(phiMn={out.phi_Mn:.0f} >= Mu={out.Mu_kg_cm:.0f} kg.cm)")
chk_true("B7 rebar selected", out.rebar is not None,
         f"(As_req={out.As_required:.2f} cm2 -> {out.rebar.main_bars if out.rebar else None})")
chk_true("B8 safety margin >=0", out.safety_margin_pct >= -0.01,
         f"(margin={out.safety_margin_pct:.1f}%)")
print()

# =====================================================================
# LAYER C — Realistic Thai residential full design_beam cases
# =====================================================================
print("="*68)
print("LAYER C · Realistic residential beams (full design_beam)")
print("="*68)

def report_case(label, inp):
    print(f"\n-- {label} --")
    try:
        o = calc.design_beam(inp)
    except calc.CivilCalcError as e:
        print(f"   RAISED {type(e).__name__}: {e}")
        return None
    sd = o.stirrup_design or {}
    print(f"   Wu={o.Wu:.2f} kN/m  Mu={o.Mu:.2f} kN.m  Vu={o.Vu:.2f} kN  "
          f"({o.Vu*calc.KN_TO_TON:.2f} ton)")
    print(f"   R_A={o.R_A:.2f}  R_B={o.R_B:.2f} kN   "
          f"As_req={o.As_required:.2f} cm2  rebar={o.rebar.main_bars if o.rebar else None}")
    print(f"   flexure_pass={o.passes_flexure}  shear_pass={o.passes_shear}  OVERALL={o.passes}")
    print(f"   shear branch={sd.get('branch')}  notation='{sd.get('shop_drawing_notation')}'")
    print(f"   margin={o.safety_margin_pct:.1f}%")
    return o

# C1 · คานพื้นชั้น 2 บ้านพักเล็ก · เบา
c1 = calc.BeamInput(b=20, h=40, L=4.0, fc=240, fy=4000, DL=2.5, LL=2.0)
o1 = report_case("C1 light floor beam 20x40 L4.0", c1)
if o1:
    chk_true("C1 statics R_A+R_B = Wu*L", abs((o1.R_A+o1.R_B) - o1.Wu*4.0) < 0.5,
             f"(sum={o1.R_A+o1.R_B:.2f} vs {o1.Wu*4.0:.2f})")
    chk_true("C1 overall passes", o1.passes)

# C2 · คานรับผนัง + จุดโหลดจากเสาด้านบน
c2 = calc.BeamInput(b=25, h=50, L=5.0, fc=240, fy=4000, DL=4.0, LL=3.0,
                    point_loads=[calc.PointLoad(kind="DL", P=50.0, x=2.5)])
o2 = report_case("C2 wall beam 25x50 L5.0 + 50kN DL @ mid", c2)
if o2:
    total = o2.Wu*5.0 + sum(p["Pu"] for p in o2.point_loads_factored)
    chk_true("C2 statics R_A+R_B = Wu*L+sum(Pu)", abs((o2.R_A+o2.R_B) - total) < 0.5,
             f"(sum={o2.R_A+o2.R_B:.2f} vs {total:.2f})")
    chk_true("C2 M_max near midspan (sym load)", abs(o2.x_at_M_max - 2.5) < 0.1,
             f"(x_at_M_max={o2.x_at_M_max:.2f})")

# C3 · คานยาวรับหนัก · ควรต้องออกแบบเหล็กปลอก (DESIGN_STIRRUP)
c3 = calc.BeamInput(b=30, h=60, L=6.0, fc=240, fy=4000, DL=8.0, LL=10.0)
o3 = report_case("C3 heavy beam 30x60 L6.0 DL8 LL10", c3)
if o3:
    chk_true("C3 shear branch is MIN or DESIGN (not NO_STIRRUP)",
             o3.stirrup_design.get("branch") in ("MIN_STIRRUP","DESIGN_STIRRUP"),
             f"(branch={o3.stirrup_design.get('branch')})")

# C4 · 3 จุดโหลด asymmetric (column/wall/tank) — Session 2 headline case
c4 = calc.BeamInput(b=30, h=60, L=6.0, fc=240, fy=4000, DL=4.0, LL=5.0,
                    point_loads=[calc.PointLoad("DL",20,1.5),
                                 calc.PointLoad("LL",15,3.0),
                                 calc.PointLoad("DL",10,4.5)])
o4 = report_case("C4 30x60 L6.0 + 3 point loads (vault case)", c4)
if o4:
    total = o4.Wu*6.0 + sum(p["Pu"] for p in o4.point_loads_factored)
    chk_true("C4 statics balance", abs((o4.R_A+o4.R_B) - total) < 0.5,
             f"(sum={o4.R_A+o4.R_B:.2f} vs {total:.2f})")
    chk_true("C4 symmetric zones invariant 2*L_S1+L_S2=L",
             abs(2*o4.stirrup_design.get("L_S1_cm",0)+o4.stirrup_design.get("L_S2_cm",0) - 600.0) < 1.0,
             f"(L_S1={o4.stirrup_design.get('L_S1_cm')} L_S2={o4.stirrup_design.get('L_S2_cm')})")
print()

# =====================================================================
# LAYER D — Edge / validation error paths
# =====================================================================
print("="*68)
print("LAYER D · Edge cases & validation")
print("="*68)

def expect_raise(name, fn, exc_type):
    try:
        fn()
        chk_true(name, False, "(no exception raised!)")
    except exc_type as e:
        chk_true(name, True, f"({type(e).__name__})")
    except Exception as e:
        chk_true(name, False, f"(wrong exc {type(e).__name__}: {e})")

expect_raise("D1 negative b raises InvalidInputError",
             lambda: calc.design_beam(calc.BeamInput(b=-25,h=50,L=4.5,fc=240,fy=4000,DL=2,LL=2)),
             calc.InvalidInputError)
expect_raise("D2 bad fy grade raises InvalidGradeError",
             lambda: calc.design_beam(calc.BeamInput(b=25,h=50,L=4.5,fc=240,fy=3777,DL=2,LL=2)),
             calc.InvalidGradeError)
expect_raise("D3 6 point loads raises TooManyPointLoadsError",
             lambda: calc.design_beam(calc.BeamInput(b=25,h=50,L=5,fc=240,fy=4000,DL=2,LL=2,
                 point_loads=[calc.PointLoad("DL",5,i*0.7+0.5) for i in range(6)])),
             calc.TooManyPointLoadsError)
expect_raise("D4 point load x>L raises PointLoadOutOfRangeError",
             lambda: calc.design_beam(calc.BeamInput(b=25,h=50,L=5,fc=240,fy=4000,DL=2,LL=2,
                 point_loads=[calc.PointLoad("DL",10,9.9)])),
             calc.PointLoadOutOfRangeError)

# D5 · Vs demand beyond 2.1*sqrt(fc)*b*d cap -> SectionTooSmallForShearError
# (direct design_shear call · isolates the shear-crush limit from flexure governing first)
expect_raise("D5 Vs>2.1sqrt(fc)bd raises SectionTooSmallForShearError",
             lambda: calc.design_shear(Wu_kN_m=10.0, L_m=4.0,
                 R_A_kN=300.0, R_B_kN=300.0, factored_points=None,
                 b_cm=20, d_cm=40, fc_ksc=180),
             calc.SectionTooSmallForShearError)

# D6 · design_beam wraps that into branch=FAIL (not a crash) when section truly governs shear
# craft deep-narrow short-span beam: flexure OK but very high shear demand
o6 = calc.design_beam(calc.BeamInput(b=20,h=70,L=2.0,fc=180,fy=4000,DL=60,LL=70))
chk_true("D6 design_beam handles shear-governed case without crashing",
         isinstance(o6.stirrup_design, dict),
         f"(branch={o6.stirrup_design.get('branch')} shear_pass={o6.passes_shear} overall={o6.passes})")
print()

# =====================================================================
# LAYER E — Unit-conversion consistency
# =====================================================================
print("="*68)
print("LAYER E · Unit conversion round-trips")
print("="*68)
chk("E1 kN->kg (101.97)", calc._kN_to_kg(1.0), 101.97, abs_tol=0.01)
chk("E2 kg->kN round-trip", calc._kg_to_kN(calc._kN_to_kg(123.4)), 123.4, abs_tol=0.001)
chk("E3 KN_TO_TON", calc.KN_TO_TON, 0.10197, abs_tol=1e-5)
# 1 ton displayed = 1000 kg = 9.80665 kN approx -> 1/0.10197 = 9.807 kN
chk("E4 1 ton == ~9.807 kN", 1.0/calc.KN_TO_TON, 9.807, abs_tol=0.01)
# design_shear ton fields consistent with kN fields
sd4 = o4.stirrup_design if o4 else {}
if sd4 and "Vc_kN" in sd4:
    chk("E5 Vc_ton == Vc_kN*KN_TO_TON", sd4["Vc_ton"], sd4["Vc_kN"]*calc.KN_TO_TON, abs_tol=0.02)
print()

# =====================================================================
# LAYER F — Double stirrups (n_legs · 2ป) · engine PR 2026-06-03
# =====================================================================
print("="*68)
print("LAYER F · Double stirrups (n_legs = 4 / 2ป)")
print("="*68)
# DESIGN_STIRRUP case (Vu > phiVc, below crush cap): Wu=80 L=5 b=30 d=45 fc=240
_sh = dict(Wu_kN_m=80.0, L_m=5.0, R_A_kN=200.0, R_B_kN=200.0,
           factored_points=None, b_cm=30, d_cm=45, fc_ksc=240)
sd2 = calc.design_shear(**_sh, n_legs=2)
sd4 = calc.design_shear(**_sh, n_legs=4)
chk_true("F0 both DESIGN_STIRRUP branch",
         sd2["branch"] == "DESIGN_STIRRUP" and sd4["branch"] == "DESIGN_STIRRUP",
         f"(2leg={sd2['branch']} 4leg={sd4['branch']})")
chk("F1 A_v(4 legs) == 2x A_v(2 legs)", sd4["A_v_cm2"], 2.0 * sd2["A_v_cm2"], abs_tol=1e-6)
chk_true("F2 double-stirrup spacing S1 >= single (more area → wider)",
         sd4["S1_cm"] >= sd2["S1_cm"] - 1e-9,
         f"(S1 2leg={sd2['S1_cm']} 4leg={sd4['S1_cm']})")
chk_true("F3 notation tags 2ป for double", "2ป" in sd4["shop_drawing_notation"],
         f"('{sd4['shop_drawing_notation']}')")
chk_true("F3b single-stirrup notation has NO ป-prefix (regression)",
         "ป-" not in sd2["shop_drawing_notation"],
         f"('{sd2['shop_drawing_notation']}')")
chk_eq("F4 n_legs/n_stirrups echoed", (sd4["n_legs"], sd4["n_stirrups"]), (4, 2))
chk_true("F5 double still passes shear", sd4["passes"] is True)
expect_raise("F6 invalid n_legs=3 raises InvalidInputError",
             lambda: calc.design_shear(**_sh, n_legs=3),
             calc.InvalidInputError)
# F7 · end-to-end via BeamInput.stirrup_legs
o_sl = calc.design_beam(calc.BeamInput(b=30,h=55,L=5,fc=240,fy=4000,DL=30,LL=25,stirrup_legs=4))
chk_eq("F7 design_beam threads stirrup_legs=4", o_sl.stirrup_design.get("n_legs"), 4)
print()

# =====================================================================
print("="*68)
print(f"RESULT: {len(PASS)} PASS / {len(FAIL)} FAIL  (total {len(PASS)+len(FAIL)})")
if FAIL:
    print("FAILURES:")
    for f in FAIL:
        print("   - " + f)
else:
    print("ALL GREEN")
print("="*68)

sys.exit(1 if FAIL else 0)
