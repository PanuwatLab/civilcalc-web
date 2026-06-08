# -*- coding: utf-8 -*-
"""
UAT — Doubly-Reinforced Beam (compression steel · 2026-06-08)
Verifies calc.py doubly-reinforced path against DRMK SDM 3 Bending (book p70 · Ex 3.10)
+ end-to-end design_beam + boundary (singly↔doubly) + ductility-by-construction.

ที่มา: [[Formula - RC Doubly-Reinforced Beam Design (RC-SDM)]] · DRMK ALL_SDM_BasicBOOK_DRMK.pdf p75-85.
"""
import sys, io, importlib.util
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_CALC = Path(__file__).resolve().parent / "calc.py"
spec = importlib.util.spec_from_file_location("calc", str(_CALC))
calc = importlib.util.module_from_spec(spec); sys.modules["calc"] = calc
spec.loader.exec_module(calc)

PASS, FAIL = [], []

def chk(name, got, exp, tol=0.02, abs_tol=None):
    ok = (abs(got - exp) <= abs_tol) if abs_tol is not None else (
        abs(got - exp) <= tol * abs(exp) if exp else abs(got) <= tol)
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got:.4f} exp={exp:.4f}")

def chk_true(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")

beta1_280 = calc.compute_beta1(280)
rho_max_280 = calc.compute_rho_max(calc.compute_rho_b(280, 4000, beta1_280))

print("=" * 60)
print(" A · DRMK Example 3.10 (design · book p70)")
print("=" * 60)
# Mu=90 t.m, b=40, d=54, d'=6, f'c=280, fy=4000
dr = calc.compute_doubly_reinforced(90 * 100000.0, 40, 54, 6, 280, 4000, beta1_280, rho_max_280)
chk("Ex3.10 As1", dr["As1"], 49.46, tol=0.01)
chk("Ex3.10 As2", dr["As2"], 7.15, tol=0.03)
chk("Ex3.10 As total", dr["As"], 56.61, tol=0.01)
chk("Ex3.10 a (stress block)", dr["a"], 20.78, tol=0.01)
chk("Ex3.10 c (neutral axis)", dr["c"], 24.45, tol=0.01)
chk_true("Ex3.10 compression steel yields", dr["yields"])
chk("Ex3.10 fs' = fy (yielded)", dr["fs_prime"], 4000, tol=0.001)

print("\n" + "=" * 60)
print(" B · analyze_doubly_capacity round-trip (DRMK Ex 3.8 method)")
print("=" * 60)
Mn, a, fsp = calc.analyze_doubly_capacity(56.61, 7.15, 40, 54, 6, 280, 4000, beta1_280)
# provided steel ≈ design → Mn ≈ Mu/φ = 90/0.9 = 100 t.m = 1e7 kg.cm
chk("analyze Mn ≈ Mu/φ", Mn, 1.0e7, tol=0.01)

print("\n" + "=" * 60)
print(" C · end-to-end design_beam — doubly triggers + passes")
print("=" * 60)
# narrow heavy beam → over-reinforced singly → doubly
inp = calc.BeamInput(b=20, h=40, L=8.0, fc=240, fy=4000, cover=3.0,
                     db_assume=1.6, d_stirrup=0.9, DL=10.0, LL=8.0,
                     load_combo=calc.LoadCombo.ACI_LEGACY)
out = calc.design_beam(inp)
chk_true("C doubly triggered (is_doubly)", out.is_doubly)
chk_true("C tension rebar selected", out.rebar is not None,
         f"As_prov={out.rebar.As_provided if out.rebar else None}")
chk_true("C compression rebar selected", out.rebar_compression is not None,
         f"As'_prov={out.rebar_compression.As_provided if out.rebar_compression else None}")
chk_true("C As' required > 0", out.As_prime_required > 0, f"As'={out.As_prime_required:.2f}")
chk_true("C passes_flexure (φMn≥Mu)", out.passes_flexure,
         f"φMn={out.phi_Mn:.0f} Mu={out.Mu_kg_cm:.0f}")
chk_true("C As = As1 + As2", abs(out.As_required - (out.As1 + out.As2)) < 1e-6)
chk_true("C As_provided ≥ As_required", out.rebar.As_provided >= out.As_required - 1e-6)

print("\n" + "=" * 60)
print(" D · ductility by construction — (ρ − ρ'·fs'/fy) ≈ ρmax")
print("=" * 60)
b, d = inp.b, out.d_actual
rho = out.As_required / (b * d)
rho_p = out.As_prime_required / (b * d)
net = rho - rho_p * (out.fs_prime_ksc / inp.fy)
chk("D net tension ratio ≈ ρmax", net, out.rho_max, tol=0.001)

print("\n" + "=" * 60)
print(" E · boundary — singly stays singly (zero-reg sanity)")
print("=" * 60)
# light beam → singly
inp2 = calc.BeamInput(b=30, h=55, L=4.0, fc=240, fy=4000, cover=3.0,
                      db_assume=1.6, d_stirrup=0.9, DL=3.0, LL=2.0,
                      load_combo=calc.LoadCombo.ACI_LEGACY)
out2 = calc.design_beam(inp2)
chk_true("E light beam stays singly", not out2.is_doubly)
chk_true("E light beam passes", out2.passes_flexure)
chk_true("E singly: no compression rebar", out2.rebar_compression is None)

print("\n" + "=" * 60)
print(" F · graceful fail — section too small even for doubly (no exception)")
print("=" * 60)
inp3 = calc.BeamInput(b=20, h=30, L=10.0, fc=210, fy=4000, cover=3.0,
                      db_assume=1.6, d_stirrup=0.9, DL=15.0, LL=12.0,
                      load_combo=calc.LoadCombo.ACI_LEGACY)
try:
    out3 = calc.design_beam(inp3)
    chk_true("F returns result (no exception)", True)
    chk_true("F fails gracefully (passes=False)", not out3.passes,
             f"is_doubly={out3.is_doubly} passes={out3.passes}")
except Exception as e:
    chk_true("F returns result (no exception)", False, f"raised {type(e).__name__}")

print("\n" + "=" * 60)
print(" G · cantilever over-reinforced → NOT doubly (gated · Codex P1 #27)")
print("=" * 60)
# cantilever fixed-end −M: tension TOP / compression BOTTOM (สลับด้าน) → doubly ต้องไม่ทำงาน
# Mu = Wu·L²/2 (cantilever) สูง → เกิน ρmax → ต้อง raise OverReinforcedError เหมือนเดิม (ไม่ใช่ is_doubly wrong-face)
inpC = calc.BeamInput(b=20, h=35, L=4.0, fc=210, fy=4000, cover=3.0,
                      db_assume=1.6, d_stirrup=0.9, DL=8.0, LL=8.0,
                      support=calc.SupportType.CANTILEVER,
                      load_combo=calc.LoadCombo.ACI_LEGACY)
try:
    outC = calc.design_beam(inpC)
    chk_true("G cantilever over-reinforced NOT routed to doubly", not outC.is_doubly,
             f"is_doubly={outC.is_doubly} passes={outC.passes}")
except (calc.OverReinforcedError, calc.SectionTooSmallError) as e:
    chk_true("G cantilever over-reinforced NOT routed to doubly", True,
             f"raised {type(e).__name__} (เดิม · ถูกต้อง)")

print("\n" + "=" * 60)
n_pass, n_fail = len(PASS), len(FAIL)
print(f" RESULT: {n_pass} PASS / {n_fail} FAIL  {'ALL GREEN' if not n_fail else 'SEE FAILURES'}")
print("=" * 60)
sys.exit(1 if n_fail else 0)
