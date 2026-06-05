# -*- coding: utf-8 -*-
"""UAT · compute_curtailment() — ระยะหยุดเหล็กตามมาตรฐาน รูปที่ 8.32 (มงคล C8 Bond).

Verify closed-form ตามกฎ [[Formula - Bar Curtailment & Cutoff Positions (RC-SDM)]]:
  top  : cut_half = max(Ll,Lr)/4 · cut_third = max(maxL/3, cut_half+ext) · ext = max(d, 12db, Ln/16)
  bot  : cut_eighth = L/8 · into_support = 0.15 · ext = max(d, 12db)
ไม่แตะ engine core · zero-regression แยกไฟล์ (uat_recheck/uat_continuous คุม core).
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import calc

PASS = 0
FAIL = 0


def check(name, cond, got=None, exp=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} · got={got} exp={exp}")


def near(a, b, tol=0.01):
    return abs(a - b) <= tol


def design(spans, b=30, h=55, fc=240, fy=4000, cover=4, db=2.5, dstir=0.9, dl=20, ll=12):
    inp = calc.ContinuousBeamInput(
        b=b, h=h, fc=fc, fy=fy, cover=cover, db_assume=db, d_stirrup=dstir,
        spans=[calc.SpanInput(L=L, DL=dl, LL=ll, point_loads=[]) for L in spans],
        load_combo="1.4D+1.7L")
    return calc.design_continuous_beam_exact(inp)


print("=" * 60)
print(" UAT · compute_curtailment (รูปที่ 8.32 · มงคล C8)")
print("=" * 60)

# ---- Case 1 · 3-span (5,6,5) — กฎพื้นฐานทุกตัว ----
print("\nCase 1 · 3-span [5,6,5]")
c = design([5.0, 6.0, 5.0])["curtailment"]
check("มี 2 interior support (B,C) ใน top", len(c["top"]) == 2, len(c["top"]))
check("มี 3 span ใน bottom", len(c["bottom"]) == 3, len(c["bottom"]))
tB = next(t for t in c["top"] if t["support"] == "B")
check("top B cut_half = max(5,6)/4 = 1.5", near(tB["cut_half_m"], 1.5), tB["cut_half_m"], 1.5)
check("top B cut_third = max(6/3, half+ext) = 2.0", near(tB["cut_third_m"], 2.0), tB["cut_third_m"], 2.0)
check("top B ext ≥ 12db = 0.30", tB["ext_min_m"] >= 0.30 - 1e-9, tB["ext_min_m"])
bAB = next(b for b in c["bottom"] if b["span"] == "A-B")
check("bot A-B cut_eighth = 5/8 = 0.625", near(bAB["cut_eighth_m"], 0.625), bAB["cut_eighth_m"], 0.625)
check("bot A-B into_support = 0.15", near(bAB["into_support_m"], 0.15), bAB["into_support_m"], 0.15)
bBC = next(b for b in c["bottom"] if b["span"] == "B-C")
check("bot B-C cut_eighth = 6/8 = 0.75", near(bBC["cut_eighth_m"], 0.75), bBC["cut_eighth_m"], 0.75)

# ---- Case 2 · 2-span unequal (4,7) — cut_half/third ใช้ span ที่ยาวกว่า ----
print("\nCase 2 · 2-span [4,7]")
c2 = design([4.0, 7.0])["curtailment"]
check("2-span → 1 interior support (B)", len(c2["top"]) == 1, len(c2["top"]))
tB2 = c2["top"][0]
check("top B cut_half = max(4,7)/4 = 1.75", near(tB2["cut_half_m"], 1.75), tB2["cut_half_m"], 1.75)
check("top B cut_third ≥ 7/3 = 2.33", tB2["cut_third_m"] >= 7.0 / 3.0 - 0.01, tB2["cut_third_m"])
b2 = {b["span"]: b for b in c2["bottom"]}
check("bot A-B cut_eighth = 4/8 = 0.5", near(b2["A-B"]["cut_eighth_m"], 0.5), b2["A-B"]["cut_eighth_m"], 0.5)
check("bot B-C cut_eighth = 7/8 = 0.875", near(b2["B-C"]["cut_eighth_m"], 0.875), b2["B-C"]["cut_eighth_m"], 0.875)

# ---- Case 3 · shallow long span → Ln/16 governs top ext (โหลดเบาให้ผ่าน) ----
print("\nCase 3 · long shallow [9,9] h=50 โหลดเบา → Ln/16 ครอง ext (บน)")
c3 = design([9.0, 9.0], h=50, dl=6, ll=4)["curtailment"]
check("3: มี interior support (top ผ่าน)", len(c3["top"]) >= 1, len(c3["top"]))
if c3["top"]:
    tB3 = c3["top"][0]
    # Ln/16 = 9/16 = 0.5625 · d ≈ (50-4-0.9-1.25)/100=0.439 → Ln/16 ครอง
    check("top ext = max(d,12db,Ln/16) ≈ Ln/16 = 0.5625", near(tB3["ext_min_m"], 0.5625, 0.02), tB3["ext_min_m"], 0.5625)
    check("top cut_third > cut_half (เลยจุดดัดกลับ)", tB3["cut_third_m"] > tB3["cut_half_m"], tB3["cut_third_m"])

# ---- Case 5 · คานยื่น → exterior support ต้องถูกรวม (Codex P2) ----
print("\nCase 5 · 2-span + คานยื่นซ้าย → exterior support A มีเหล็กบน")
inp5 = calc.ContinuousBeamInput(
    b=30, h=55, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9,
    spans=[calc.SpanInput(L=5, DL=20, LL=12, point_loads=[]),
           calc.SpanInput(L=5, DL=20, LL=12, point_loads=[])],
    load_combo="1.4D+1.7L", left_cantilever={"L": 1.5, "DL": 15, "LL": 8, "point_loads": []})
c5 = calc.design_continuous_beam_exact(inp5)["curtailment"]
tops5 = {t["support"]: t for t in c5["top"]}
check("exterior support A (คานยื่น) ถูกรวมใน top", "A" in tops5, list(tops5))
check("A.exterior_cantilever = True", tops5.get("A", {}).get("exterior_cantilever") is True, tops5.get("A", {}).get("exterior_cantilever"))
check("A ใช้ช่วงในข้างเดียว (L_left None · L_right=5)",
      tops5.get("A", {}).get("L_left_m") is None and near(tops5.get("A", {}).get("L_right_m", 0), 5.0),
      (tops5.get("A", {}).get("L_left_m"), tops5.get("A", {}).get("L_right_m")))
check("A cut_half = 5/4 = 1.25", near(tops5.get("A", {}).get("cut_half_m", 0), 1.25), tops5.get("A", {}).get("cut_half_m"))
check("interior support B ยังอยู่ (exterior_cantilever False)",
      tops5.get("B", {}).get("exterior_cantilever") is False, tops5.get("B", {}).get("exterior_cantilever"))

# ---- Case 6 · gating: UDL equal → applicable=True · จุดโหลด/ช่วงไม่เท่า → False (Codex P2) ----
print("\nCase 6 · gating applicable")
check("UDL ช่วงเท่า [5,6,5] → applicable=True", c["applicable"] is True, c["applicable"])
check("UDL ช่วงเท่า → ไม่มี warnings", len(c["warnings"]) == 0, c["warnings"])
# มีจุดโหลด → applicable=False
inp_pl = calc.ContinuousBeamInput(
    b=30, h=55, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9,
    spans=[calc.SpanInput(L=5, DL=20, LL=12, point_loads=[calc.PointLoad(kind="LL", P=50, x=2.5)]),
           calc.SpanInput(L=5, DL=20, LL=12, point_loads=[])],
    load_combo="1.4D+1.7L")
cpl = calc.design_continuous_beam_exact(inp_pl)["curtailment"]
check("มีจุดโหลด → applicable=False", cpl["applicable"] is False, cpl["applicable"])
check("มีจุดโหลด → warning เรื่องจุดโหลด", any("จุดโหลด" in w for w in cpl["warnings"]), cpl["warnings"])
# ช่วงไม่เท่ามาก [3,9] UDL → applicable=False
cuneq = design([3.0, 9.0], h=60, dl=8, ll=5)["curtailment"]
check("ช่วงไม่เท่า max/min=3 → applicable=False", cuneq["applicable"] is False, cuneq["applicable"])
check("ช่วงไม่เท่า → warning เรื่องช่วง", any("ช่วง" in w for w in cuneq["warnings"]), cuneq["warnings"])

# ---- Case 7 · คานยื่นมีจุดโหลด (ช่วงใน UDL) → applicable=False (Codex P2) ----
print("\nCase 7 · คานยื่นมีจุดโหลด → applicable=False")
inp7 = calc.ContinuousBeamInput(
    b=30, h=55, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9,
    spans=[calc.SpanInput(L=5, DL=20, LL=12, point_loads=[]),
           calc.SpanInput(L=5, DL=20, LL=12, point_loads=[])],
    load_combo="1.4D+1.7L",
    left_cantilever={"L": 2.0, "DL": 10, "LL": 5, "point_loads": [{"kind": "LL", "P": 40, "x": 1.8}]})
c7 = calc.design_continuous_beam_exact(inp7)["curtailment"]
check("คานยื่นมีจุดโหลด → applicable=False", c7["applicable"] is False, c7["applicable"])
check("คานยื่นมีจุดโหลด → warning เรื่องจุดโหลด", any("จุดโหลด" in w for w in c7["warnings"]), c7["warnings"])
# คานยื่น UDL ล้วน (ไม่มีจุดโหลด) + ช่วงในเท่า → ยัง applicable=True
inp7b = calc.ContinuousBeamInput(
    b=30, h=55, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9,
    spans=[calc.SpanInput(L=5, DL=20, LL=12, point_loads=[]),
           calc.SpanInput(L=5, DL=20, LL=12, point_loads=[])],
    load_combo="1.4D+1.7L",
    left_cantilever={"L": 1.5, "DL": 12, "LL": 6, "point_loads": []})
c7b = calc.design_continuous_beam_exact(inp7b)["curtailment"]
check("คานยื่น UDL ล้วน + ช่วงเท่า → applicable=True", c7b["applicable"] is True, c7b["applicable"])

# ---- Case 4 · citations + method ครบ ----
print("\nCase 4 · metadata")
check("method อ้าง รูปที่ 8.32", "8.32" in c["method"], c["method"])
check("มี ≥3 citations", len(c["citations"]) >= 3, len(c["citations"]))
check("datum ระบุจุดอ้างอิง (หน้าเสา/ศูนย์เสา)", "เสา" in c["datum"], c["datum"])

print("\n" + "=" * 60)
print(f" RESULT: {PASS} PASS / {FAIL} FAIL" + ("  ALL GREEN" if FAIL == 0 else "  *** FAIL ***"))
print("=" * 60)
sys.exit(1 if FAIL else 0)
