# -*- coding: utf-8 -*-
"""
UAT — Torsion (การบิด · New Module · 2026-06-22)
Verifies calc.py compute_torsion / compute_torsion_tmd against DRMK SDM Ch.9.

ที่มา: [[Formula - RC Beam Torsion Design (RC-SDM)]] · ALL_SDM_BasicBOOK_DRMK.pdf p233-256.
ตัวอย่างยืนยัน:
  Ex 9.1 (p238) — threshold คานยื่นรูปสี่เหลี่ยม (Tu < φTcr/4 → ไม่ต้องคิดบิด)
  Ex 9.2 (p244) — full chain (web-section · A0h ใช้เส้นปลอกเหมือน rectangular → ตรงเป๊ะ)
  TMD รูป 9.21 — t·L/2 ที่ผิวเสา · ลดที่ระยะ d
หมายเหตุ: Ex 9.2/9.3 textbook ใช้ Acp รวมปีกพื้น (T/L) → ค่า threshold ต่างจากสี่เหลี่ยม
  แต่ section-adequacy/At-s/combine/Al ใช้ A0h เส้นปลอก (= web) จึงตรงเป๊ะกับโมดูลสี่เหลี่ยม.
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

print("=" * 64)
print(" A · DRMK Example 9.1 (threshold · คานยื่นสี่เหลี่ยม · p238)")
print("=" * 64)
# b=30, h=60, f'c=240 · Tu = 3 ton × 0.15 m = 0.45 ตัน·ม
r1 = calc.compute_torsion(Tu_tonm=0.45, Vu_ton=3.0, b_cm=30, h_cm=60, fc_ksc=240)
chk("Ex9.1 Tcr", r1["Tcr_tonm"], 3.07, tol=0.01)
chk("Ex9.1 threshold φTcr/4", r1["threshold_tonm"], 0.65, tol=0.02)
chk_true("Ex9.1 applicable=False (Tu<φTcr/4 → ไม่ต้องคิดบิด)", r1["applicable"] is False,
         f"(applicable={r1['applicable']})")

print("=" * 64)
print(" B · DRMK Example 9.2 (full design · web-section · p244-246)")
print("=" * 64)
# b=30, h=60, d=54, cover-center=4, f'c=280, fyt=fyl=4000 · Tu=3.3 ตัน·ม · Vu=13.5 ตัน
r2 = calc.compute_torsion(Tu_tonm=3.3, Vu_ton=13.5, b_cm=30, h_cm=60, fc_ksc=280,
                          d_cm=54, cover_cm=4, fyt_ksc=4000, fyl_ksc=4000)
chk_true("Ex9.2 applicable=True (Tu > φTcr/4)", r2["applicable"] is True)
# geometry เส้นปลอก
chk("Ex9.2 x0", r2["x0"], 22.0, abs_tol=0.1)
chk("Ex9.2 y0", r2["y0"], 52.0, abs_tol=0.1)
chk("Ex9.2 A0h = x0·y0", r2["A0h"], 1144.0, tol=0.01)
chk("Ex9.2 A0 = 0.85·A0h", r2["A0"], 972.4, tol=0.01)
chk("Ex9.2 ph", r2["ph"], 148.0, tol=0.01)
# section-adequacy (Eq 9.17 · ksc) — textbook 0.0235 ≤ 0.0374 ton/cm² = 23.5 ≤ 37.4 ksc
chk("Ex9.2 τ_combined (ksc)", r2["tau_combined_ksc"], 23.48, tol=0.02)
chk("Ex9.2 τ_limit (ksc)", r2["tau_limit_ksc"], 37.40, tol=0.02)
chk_true("Ex9.2 section_ok (หน้าตัดพอ)", r2["section_ok"] is True)
# At/s · combine · Al
chk("Ex9.2 At/s (per leg · Eq 9.21)", r2["At_s"], 0.0499, tol=0.02)
chk("Ex9.2 (Av+2At)/s combine (Eq 9.23)", r2["Avt_s"], 0.107, tol=0.03)
chk("Ex9.2 Al longitudinal (Eq 9.25)", r2["Al_cm2"], 7.39, tol=0.03)
chk("Ex9.2 s_max = min(ph/8,30)", r2["s_max_cm"], 18.5, tol=0.02)

print("=" * 64)
print(" C · TMD (แผนภูมิโมเมนต์บิด · รูป 9.21) · Ex 9.2 distributed torque")
print("=" * 64)
# t = w·e = 1.266 ton/m × 0.75 m = 0.9495 ตัน·ม/ม · L=8 m · d=54 cm
tmd = calc.compute_torsion_tmd(t_tonm_per_m=1.266 * 0.75, L_m=8.0, d_cm=54)
chk("TMD Tu ผิวเสา = t·L/2", tmd["Tu_support_tonm"], 3.80, tol=0.02)
chk("TMD Tu ที่ระยะ d (วิกฤตออกแบบ)", tmd["Tu_at_d_tonm"], 3.29, tol=0.03)
chk_true("TMD รูปสามเหลี่ยม", tmd["shape"] == "triangular")

print("=" * 64)
print(" D · Compatibility torsion → ลด Tu เหลือ φTcr (Eq 9.27)")
print("=" * 64)
# เลือกหน้าตัดที่ Tu > φTcr → compat ต้องลดเหลือ φTcr · equilibrium รับเต็ม
r_eq = calc.compute_torsion(Tu_tonm=8.0, Vu_ton=5.0, b_cm=40, h_cm=70, fc_ksc=280,
                            d_cm=63, cover_cm=4, is_compatibility=False)
r_co = calc.compute_torsion(Tu_tonm=8.0, Vu_ton=5.0, b_cm=40, h_cm=70, fc_ksc=280,
                            d_cm=63, cover_cm=4, is_compatibility=True)
phiTcr = 0.85 * r_eq["Tcr_tonm"]
chk_true("compat: Tu_design ลดลง (< equilibrium)", r_co["Tu_design_tonm"] < r_eq["Tu_design_tonm"])
chk("compat: Tu_design = φTcr", r_co["Tu_design_tonm"], phiTcr, tol=0.02)
chk("equilibrium: Tu_design = Tu เต็ม", r_eq["Tu_design_tonm"], 8.0, tol=0.001)

print("=" * 64)
print(" E · section-too-small (แรงบิดสูงบนหน้าตัดเล็ก → adequacy fail)")
print("=" * 64)
threw = False
try:
    calc.compute_torsion(Tu_tonm=15.0, Vu_ton=20.0, b_cm=20, h_cm=30, fc_ksc=240, d_cm=24)
except calc.SectionTooSmallForShearError:
    threw = True
chk_true("section-adequacy เกิน limit → raise SectionTooSmallForShearError", threw)

print("=" * 64)
print(" F · integration · design_beam wiring (zero-reg เมื่อ Tu=0)")
print("=" * 64)
BI = calc.BeamInput
# Tu=0 → torsion None (zero-reg · พฤติกรรมเดิม)
o0 = calc.design_beam(BI(b=30, h=60, L=6, fc=280, fy=4000, DL=2, LL=1))
chk_true("design_beam Tu=0 → out.torsion is None (zero-reg)", o0.torsion is None)
chk_true("design_beam Tu=0 → ผ่านปกติ", o0.passes is True, f"(passes={o0.passes})")
# Tu สูง (>threshold) → torsion applicable + มี At/s, Al · flexure As ไม่เปลี่ยน
oT = calc.design_beam(BI(b=30, h=60, L=6, fc=280, fy=4000, DL=2, LL=1, Tu_tonm=3.3))
chk_true("design_beam Tu=3.3 → out.torsion applicable", bool(oT.torsion and oT.torsion.get("applicable")))
chk_true("design_beam Tu=3.3 → At/s > 0", bool(oT.torsion and oT.torsion.get("At_s", 0) > 0),
         f"(At_s={oT.torsion.get('At_s') if oT.torsion else None})")
chk_true("design_beam Tu=3.3 → Al > 0", bool(oT.torsion and oT.torsion.get("Al_final_cm2", 0) > 0))
chk_true("design_beam Tu=3.3 → flexure As เท่าเดิม (torsion ไม่แตะดัด · zero-reg)",
         abs(oT.As_required - o0.As_required) < 1e-6,
         f"(As Tu0={o0.As_required:.3f} · TuX={oT.As_required:.3f})")
# Tu ต่ำกว่า threshold → applicable=False (ไม่คิดบิด · ไม่กระทบ passes)
oL = calc.design_beam(BI(b=30, h=60, L=6, fc=280, fy=4000, DL=2, LL=1, Tu_tonm=0.3))
chk_true("design_beam Tu=0.3 (<threshold) → torsion applicable=False",
         bool(oL.torsion is not None and oL.torsion.get("applicable") is False))
chk_true("design_beam Tu=0.3 → ยังผ่าน (บิดน้อย)", oL.passes is True)
# to_dict serialize torsion ไป JS ได้
chk_true("design_beam to_dict() มี key torsion (serialize ไป JS)", "torsion" in oT.to_dict())

print("=" * 64)
n_pass, n_fail = len(PASS), len(FAIL)
print(f" RESULT: {n_pass}/{n_pass + n_fail} passed" + (f" · FAILED: {FAIL}" if FAIL else " · ALL PASS ✓"))
print("=" * 64)
sys.exit(1 if FAIL else 0)
