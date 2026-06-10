# -*- coding: utf-8 -*-
"""
UAT — Doubly-Reinforced Beam · CONTINUOUS / CANTILEVER (compression steel · 2026-06-10)

ขยาย doubly จาก single-span (uat_doubly.py · PR #27) → คานต่อเนื่อง/คานยื่น ผ่าน flexure core
ที่ใช้ร่วม (_safe_flexure_design → _doubly_design_for_moment · New Module · design_beam ไม่แตะ).

Ground truth หลัก = **parity กับ single-span design_beam** (verified vs DRMK Ex 3.10) สำหรับ
(section, |M|) เดียวกัน → ผลต้องตรงเป๊ะ เพราะสูตร flexure เป็น face-agnostic
(d = h − ระยะหุ้มเหล็กดึง · d′ = ระยะหุ้มเหล็กอัด เท่ากันทั้ง +M/−M · DRMK Ex 3.10).

ที่มา: [[Formula - RC Doubly-Reinforced Beam Design (RC-SDM)]] · DRMK p70/p75-85.
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

def _bars(rb):
    return calc._fmt_main_bars(rb)

# ----------------------------------------------------------------------------
print("=" * 64)
print(" A · Face-agnostic: core(−M) == core(+M) (เฉพาะหน้าวางต่าง)")
print("=" * 64)
# b=30 h=48 · Mu=42 t.m → เกิน singly ที่ ρmax → doubly
M_kNm = 42.0 / calc.KNM_TO_TONM
top = calc._safe_flexure_design(M_kNm, 30, 48, 240, 4000, 3.0, 0.9, 1.6, comp_on_top=False)  # −M
bot = calc._safe_flexure_design(M_kNm, 30, 48, 240, 4000, 3.0, 0.9, 1.6, comp_on_top=True)   # +M
chk_true("A1 −M triggers doubly", bool(top.get("is_doubly")))
chk_true("A2 +M triggers doubly", bool(bot.get("is_doubly")))
chk_true("A3 −M comp_on_top=False (เหล็กอัดล่าง)", top.get("comp_on_top") is False)
chk_true("A4 +M comp_on_top=True (เหล็กอัดบน)", bot.get("comp_on_top") is True)
chk("A5 As (tension) เท่ากันสองหน้า", top["As_required"], bot["As_required"], tol=1e-6)
chk("A6 As' (comp) เท่ากันสองหน้า", top["As_prime_required"], bot["As_prime_required"], tol=1e-6)
chk_true("A7 เหล็กดึงชุดเดียวกัน", _bars(top["rebar"]) == _bars(bot["rebar"]), _bars(top["rebar"]))
chk_true("A8 เหล็กอัดชุดเดียวกัน",
         _bars(top["rebar_compression"]) == _bars(bot["rebar_compression"]), _bars(top["rebar_compression"]))
chk_true("A9 ทั้งคู่ผ่าน (φMn≥Mu · ductile)", top.get("passes") and bot.get("passes"))

print("\n" + "=" * 64)
print(" B · Parity vs single-span design_beam (ground truth · DRMK Ex 3.10)")
print("=" * 64)
# single-span simply-supported · same section · +M = M_kNm via M=wL²/8
b, h, fc, fy, L = 30, 48, 240, 4000, 5.0
w = 8.0 * M_kNm / L ** 2
sb = calc.design_beam(calc.BeamInput(b=b, h=h, L=L, fc=fc, fy=fy, cover=3.0,
                                     db_assume=1.6, d_stirrup=0.9, DL=w / 1.4, LL=0.0,
                                     load_combo=calc.LoadCombo.ACI_LEGACY))
chk_true("B0 design_beam +M ≈ target", abs(sb.Mu * calc.KNM_TO_TONM - 42.0) < 0.5,
         f"Mu={sb.Mu*calc.KNM_TO_TONM:.2f} t.m")
chk_true("B1 single-span doubly", bool(sb.is_doubly))
chk("B2 As parity (continuous-core vs single-span)", bot["As_required"], sb.As_required, tol=1e-6)
chk("B3 As' parity", bot["As_prime_required"], sb.As_prime_required, tol=1e-6)
chk_true("B4 เหล็กดึงชุดเดียวกับ single-span", _bars(bot["rebar"]) == _bars(sb.rebar), _bars(sb.rebar))
chk_true("B5 เหล็กอัดชุดเดียวกับ single-span",
         _bars(bot["rebar_compression"]) == _bars(sb.rebar_compression), _bars(sb.rebar_compression))

print("\n" + "=" * 64)
print(" C · Continuous beam — interior support −M → doubly (end-to-end)")
print("=" * 64)
# b=25 h=50 · 2 spans heavy → interior support −M เกิน singly
inp = calc.ContinuousBeamInput(b=25, h=50, fc=240, fy=4000,
    spans=[calc.SpanInput(L=7.0, DL=24, LL=18), calc.SpanInput(L=7.0, DL=24, LL=18)],
    load_combo=calc.LoadCombo.ACI_LEGACY)
out = calc.design_continuous_beam_exact(inp)
supB = next(s for s in out["supports"] if s["label"] == "B")
tB = supB["top"]
chk_true("C1 หัวเสา B เป็น doubly", bool(supB.get("is_doubly")) and bool(tB.get("is_doubly")))
chk_true("C2 หัวเสา B ผ่าน (φMn≥Mu)", bool(tB.get("passes")), f"Mneg={supB['M_neg_tonm']:.2f} t.m")
chk_true("C3 comp_bars โชว์เหล็กอัด (≠ —)", supB.get("comp_bars") not in (None, "—"), supB.get("comp_bars"))
chk_true("C4 เหล็กดึง(บน) ≠ เหล็กอัด(ล่าง)", supB.get("top_bars") != supB.get("comp_bars"))
# parity: หัวเสา B vs single-span เดียวกัน
mB = tB["Mu_kNm"]
sbB = calc.design_beam(calc.BeamInput(b=25, h=50, L=5.0, fc=240, fy=4000, cover=3.0,
                                      db_assume=1.6, d_stirrup=0.9,
                                      DL=(8.0 * mB / 25.0) / 1.4, LL=0.0,
                                      load_combo=calc.LoadCombo.ACI_LEGACY))
chk("C5 As' หัวเสา parity single-span", tB["As_prime_required"], sbB.As_prime_required, tol=1e-6)

print("\n" + "=" * 64)
print(" D · Cantilever overhang −M → doubly (top tension, comp bottom)")
print("=" * 64)
# overhang ยาว+โหลดหนัก บนหน้าตัดจำกัด → −M เกิน singly
inp2 = calc.ContinuousBeamInput(b=25, h=45, fc=240, fy=4000,
    spans=[calc.SpanInput(L=6.0, DL=12, LL=8), calc.SpanInput(L=6.0, DL=12, LL=8)],
    right_cantilever={"L": 2.6, "DL": 30, "LL": 22, "point_loads": []},
    load_combo=calc.LoadCombo.ACI_LEGACY)
out2 = calc.design_continuous_beam_exact(inp2)
cants = out2.get("cantilevers", [])
chk_true("D1 มี cantilever row", len(cants) >= 1)
if cants:
    c = cants[0]
    isd = bool(c.get("is_doubly"))
    chk_true("D1b คานยื่น −M เกิน → doubly", isd, f"Mu={c.get('Mu_tonm')} t.m bars={c.get('top_bars')}")
    if isd:
        chk_true("D2 คานยื่น comp_bars โชว์ (เหล็กอัดล่าง)", c.get("comp_bars") not in (None, "—"), c.get("comp_bars"))
        chk_true("D3 คานยื่น top ผ่าน flexure", bool(c["top"].get("passes")))

print("\n" + "=" * 64)
print(" E · Zero-reg sanity — realistic continuous = singly ทั้งหมด (ไม่ doubly)")
print("=" * 64)
inp3 = calc.ContinuousBeamInput(b=30, h=55, fc=240, fy=4000,
    spans=[calc.SpanInput(L=7.0, DL=22, LL=16), calc.SpanInput(L=7.0, DL=22, LL=16)],
    load_combo=calc.LoadCombo.ACI_LEGACY)
out3 = calc.design_continuous_beam_exact(inp3)
any_doubly = any(s.get("is_doubly") for s in out3["supports"]) or any(s.get("is_doubly") for s in out3["spans"])
chk_true("E1 realistic = ไม่มี doubly (singly ปกติ)", not any_doubly)
chk_true("E2 realistic ทุก element ผ่าน", bool(out3["passes"]))
chk_true("E3 ช่วงยังโชว์ comp_bars = — (ไม่ doubly)",
         all(s.get("comp_bars", "—") == "—" for s in out3["spans"]))

print("\n" + "=" * 64)
print(" F · Ductility / fail-conservative — section เล็กเกินแม้ doubly")
print("=" * 64)
# b เล็กมาก + โหลดมหาศาล → แม้ doubly ก็ไม่พอ → fail (ไม่ crash · ไม่ false-pass)
huge = calc._safe_flexure_design(120.0 / calc.KNM_TO_TONM, 20, 35, 240, 4000,
                                 3.0, 0.9, 1.6, comp_on_top=False)
chk_true("F1 section เล็กเกิน → ไม่ผ่าน (fail-conservative)", not huge.get("passes"))
chk_true("F2 ไม่ crash (คืน dict)", isinstance(huge, dict))

print("\n" + "=" * 64)
print(" G · _over_reinforced marker ไม่กระทบ singly ปกติ (zero-reg flag)")
print("=" * 64)
ok = calc._flexure_design_for_moment(80.0, 30, 55, 240, 4000, 3.0, 0.9, 1.6)
chk_true("G1 singly ปกติ marker=False", ok.get("_over_reinforced") is False)
chk_true("G2 singly ปกติ ผ่าน", bool(ok.get("passes")))

# ----------------------------------------------------------------------------
print("\n" + "=" * 64)
print(f" RESULT: {len(PASS)} PASS · {len(FAIL)} FAIL")
if FAIL:
    print(" FAILED:", ", ".join(FAIL))
print("=" * 64)
sys.exit(1 if FAIL else 0)
