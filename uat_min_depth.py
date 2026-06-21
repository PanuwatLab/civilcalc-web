# -*- coding: utf-8 -*-
"""UAT · ความลึกน้อยที่สุด (min-depth / serviceability · DRMK ตาราง 3.1)

ยืนยันค่าจาก DRMK ตารางที่ 3.1 (p55 · ACI Table 9.5(a) / ว.ส.ท.) · คาน:
  ช่วงเดียว L/16 · ต่อเนื่องปลายเดียว(ริม) L/18.5 · ต่อเนื่องสองด้าน(ใน) L/21 · ยื่น L/8
  footnote: fy ≠ 4,000 → × (0.4 + fy/7,000)
หลักการ (ตัวเลือก ก): ไม่ผ่าน min-depth = advisory (เตือน) · ไม่เปลี่ยน passes (กำลัง).
"""
import sys
import calc

P = F = 0
def chk(name, cond, detail=""):
    global P, F
    ok = bool(cond)
    P += ok; F += (not ok)
    print(("  PASS " if ok else "  FAIL ") + name + ("" if ok else "  >> " + detail))

SI = calc.SpanInput
def single(b, h, L, fy=4000, DL=20, LL=8):
    return calc.design_beam(calc.BeamInput(b=b, h=h, L=L, fc=240, fy=fy, DL=DL, LL=LL))
def cont(b, h, L, n, fy=4000, DL=18, LL=8):
    return calc.design_continuous_beam_exact(
        calc.ContinuousBeamInput(b=b, h=h, fc=240, fy=fy,
                                 spans=[SI(L=L, DL=DL, LL=LL) for _ in range(n)]))

print("=" * 60)
print(" UAT · min-depth (DRMK ตาราง 3.1)")
print("=" * 60)

# ── helper values (single source of truth) ──
print("\n[A] helper min_beam_depth ตรงตาราง 3.1")
chk("simple L/16", abs(calc.min_beam_depth(8.0, "simple", 4000) - 800/16) < 1e-6, str(calc.min_beam_depth(8.0,"simple",4000)))
chk("one_end L/18.5", abs(calc.min_beam_depth(8.0, "one_end", 4000) - 800/18.5) < 1e-6)
chk("both_ends L/21", abs(calc.min_beam_depth(8.0, "both_ends", 4000) - 800/21) < 1e-6)
chk("cantilever L/8", abs(calc.min_beam_depth(8.0, "cantilever", 4000) - 800/8) < 1e-6)
# fy modifier (footnote): SD30 fy=3000 · SD50 fy=5000
chk("fy modifier SD30 (×0.4+3000/7000)", abs(calc.min_beam_depth(9.0, "simple", 3000) - 900/16*(0.4+3000/7000)) < 1e-6)
chk("fy modifier SD50 (×0.4+5000/7000)", abs(calc.min_beam_depth(9.0, "simple", 5000) - 900/16*(0.4+5000/7000)) < 1e-6)
chk("fy=4000 → ×1.0", abs(calc.min_beam_depth(9.0, "simple", 4000) - 900/16) < 1e-6)

# ── single-span ──
print("\n[B] คานช่วงเดียว L/16")
o = single(25, 50, 9)   # h=50 < 900/16=56.2 → ไม่ผ่าน
chk("25×50 L9 → min_depth_ok=False", o.min_depth_ok is False, "h_min=%.1f" % o.h_min_cm)
chk("25×50 L9 → h_min=56.2", abs(o.h_min_cm - 56.25) < 0.1, "%.1f" % o.h_min_cm)
chk("25×50 L9 → มี warning ตื้นเกิน", any("ตื้นเกิน" in w for w in o.warnings))
chk("25×50 L9 → passes ไม่ถูกแตะ (ยังเป็น strength result)", o.passes is True, "passes=%s" % o.passes)
o2 = single(25, 70, 9)  # h=70 > 56.2 → ผ่าน
chk("25×70 L9 → min_depth_ok=True (ลึกพอ)", o2.min_depth_ok is True, "h_min=%.1f" % o2.h_min_cm)
chk("25×70 L9 → ไม่มี warning ตื้นเกิน", not any("ตื้นเกิน" in w for w in o2.warnings))
o3 = single(30, 55, 4.5)  # baseline ปกติ → ผ่าน
chk("30×55 L4.5 (baseline) → min_depth_ok=True", o3.min_depth_ok is True, "h_min=%.1f" % o3.h_min_cm)

# ── continuous ──
print("\n[C] คานต่อเนื่อง — ริม L/18.5 · ใน L/21")
c2 = cont(25, 50, 10, 2)   # 2 ช่วง · ทั้งคู่เป็นริม (one_end) · L10 → h_min=54.1 > 50 → ไม่ผ่าน
chk("2-span L10 h50 → min_depth_ok=False", c2["min_depth_ok"] is False)
chk("2-span → ทุกช่วง kind=one_end (L/18.5)", all(s["md_kind"] == "one_end" for s in c2["spans"]))
chk("2-span → h_min=54.1 (L/18.5)", all(abs(s["h_min_cm"] - 1000/18.5) < 0.2 for s in c2["spans"]))
chk("2-span → จำนวน warning = 2", len(c2["min_depth_warnings"]) == 2)

c3 = cont(25, 45, 9, 3)    # 3 ช่วง · ริม one_end(L/18.5=48.6>45 ไม่ผ่าน) · ใน both_ends(L/21=42.9<45 ผ่าน)
sp = c3["spans"]
chk("3-span → ช่วงริม(0,2) kind=one_end", sp[0]["md_kind"] == "one_end" and sp[2]["md_kind"] == "one_end")
chk("3-span → ช่วงใน(1) kind=both_ends", sp[1]["md_kind"] == "both_ends")
chk("3-span L9 h45 → ริมไม่ผ่าน (48.6>45)", sp[0]["md_ok"] is False and sp[2]["md_ok"] is False)
chk("3-span L9 h45 → ในผ่าน (42.9<45 · ตื้นกว่าได้)", sp[1]["md_ok"] is True)
chk("3-span → min_depth_ok=False (ริมไม่ผ่าน)", c3["min_depth_ok"] is False)
c3b = cont(25, 55, 9, 3)   # h=55 > 48.6 → ผ่านหมด
chk("3-span L9 h55 → min_depth_ok=True (ลึกพอทุกช่วง)", c3b["min_depth_ok"] is True)

print("\n" + "=" * 60)
print(" RESULT: %d PASS / %d FAIL  %s" % (P, F, "ALL GREEN" if F == 0 else "FAIL"))
print("=" * 60)
sys.exit(1 if F else 0)
