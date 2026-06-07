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
# A2b: จุดโหลด → เหล็กบน-ล่างจาก moment envelope จริง (exact · ไม่ใช่ fig-8.32 approx อีกต่อไป)
check("มีจุดโหลด → applicable=True (envelope exact · A2b)", cpl["applicable"] is True, cpl["applicable"])
check("มีจุดโหลด → bottom_exact + top_exact (บน-ล่าง envelope จริง)",
      bool(cpl.get("bottom_exact")) and bool(cpl.get("top_exact")), (cpl.get("bottom_exact"), cpl.get("top_exact")))
check("มีจุดโหลด → ไม่มี warning ค่าประมาณ (exact แล้ว)", len(cpl["warnings"]) == 0, cpl["warnings"])
# ช่วงไม่เท่ามาก [3,9] UDL → applicable=False
cuneq = design([3.0, 9.0], h=60, dl=8, ll=5)["curtailment"]
check("ช่วงไม่เท่า max/min=3 → applicable=False", cuneq["applicable"] is False, cuneq["applicable"])
check("ช่วงไม่เท่า → warning เรื่องช่วง", any("ช่วง" in w for w in cuneq["warnings"]), cuneq["warnings"])

# ---- Case 7 · คานยื่นมีจุดโหลด → A2b envelope exact (applicable=True) ----
print("\nCase 7 · คานยื่นมีจุดโหลด → envelope exact")
inp7 = calc.ContinuousBeamInput(
    b=30, h=55, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9,
    spans=[calc.SpanInput(L=5, DL=20, LL=12, point_loads=[]),
           calc.SpanInput(L=5, DL=20, LL=12, point_loads=[])],
    load_combo="1.4D+1.7L",
    left_cantilever={"L": 2.0, "DL": 10, "LL": 5, "point_loads": [{"kind": "LL", "P": 40, "x": 1.8}]})
c7 = calc.design_continuous_beam_exact(inp7)["curtailment"]
# A2b: คานยื่นมีจุดโหลด → เหล็กล่าง+บนหัวเสาในเป็น envelope · แต่เหล็กบน "ฝั่งคานยื่น" = full+Ld (ไม่ใช่ envelope crossing)
#   → applicable=False (honest · ฝั่งคานยื่นยังไม่ได้ envelope-check · Codex P2)
check("คานยื่นมีจุดโหลด → applicable=False (ฝั่งคานยื่นยังไม่ envelope · honest)", c7["applicable"] is False, c7["applicable"])
check("คานยื่นมีจุดโหลด → bottom_exact=True + warning คานยื่น",
      bool(c7.get("bottom_exact")) and any("คานยื่น" in w for w in c7["warnings"]), (c7.get("bottom_exact"), c7["warnings"]))
# คานยื่น UDL ล้วน (ไม่มีจุดโหลด) + ช่วงในเท่า → ยัง applicable=True
inp7b = calc.ContinuousBeamInput(
    b=30, h=55, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9,
    spans=[calc.SpanInput(L=5, DL=20, LL=12, point_loads=[]),
           calc.SpanInput(L=5, DL=20, LL=12, point_loads=[])],
    load_combo="1.4D+1.7L",
    left_cantilever={"L": 1.5, "DL": 12, "LL": 6, "point_loads": []})
c7b = calc.design_continuous_beam_exact(inp7b)["curtailment"]
check("คานยื่น UDL ล้วน + ช่วงเท่า → applicable=True", c7b["applicable"] is True, c7b["applicable"])

# ---- Case 8 · single-span (bottom-only · simple-support exception) ----
print("\nCase 8 · คานช่วงเดียว bottom-only")
_LC = calc.LoadCombo("1.4D+1.7L")
o8 = calc.design_beam(calc.BeamInput(b=25, h=50, L=4.8, fc=240, fy=4000, cover=4,
                                     db_assume=1.6, d_stirrup=0.9, DL=14, LL=9, load_combo=_LC))
c8 = o8.to_dict()["curtailment"]
check("single: มี curtailment", c8 is not None, c8 is not None)
check("single: top ว่าง (ไม่มีเหล็กบนรับแรง)", len(c8["top"]) == 0, len(c8["top"]))
check("single: bottom 1 แถว (กลางช่วง)", len(c8["bottom"]) == 1, len(c8["bottom"]))
check("single: ext = max(d,12db) (ที่จุดตัด)", c8["bottom"][0]["ext_min_m"] > 0, c8["bottom"][0]["ext_min_m"])
check("single: UDL → applicable=True", c8["applicable"] is True, c8["applicable"])
check("single: method อ้าง รูป 8.23 (ช่วงเดียว)", "8.23" in c8["method"], c8["method"])
# ตัด ≤ ครึ่ง + main เต็ม (Codex P1+P2) · unit test ตรง (deterministic · ไม่ขึ้น select_rebar)
b8 = c8["bottom"][0]
if b8["n_extra_cut"] > 0:
    check("single: cont + cut = n_total · cont ≥ ครึ่ง",
          b8["n_continuous_past_L8"] >= b8["n_extra_cut"], (b8["n_continuous_past_L8"], b8["n_extra_cut"]))
rb2 = calc.RebarSelection(main_bars=[("DB16", 2)], As_provided=4.0)
b2 = calc.compute_curtailment_single(rb2, 4.0, 45.0, 1.6)["bottom"][0]
check("2-bar: cut None · ต่อเนื่อง 2 (ไม่ตัด)", b2["cut_eighth_m"] is None and b2["n_extra_cut"] == 0, b2["n_extra_cut"])
rb4 = calc.RebarSelection(main_bars=[("DB16", 4)], As_provided=8.0)
b4 = calc.compute_curtailment_single(rb4, 4.0, 45.0, 1.6)["bottom"][0]
check("4-bar: ตัด 2 · ต่อเนื่อง 2 (50%)", b4["n_extra_cut"] == 2 and b4["n_continuous_past_L8"] == 2, (b4["n_extra_cut"], b4["n_continuous_past_L8"]))
# 🔴 Codex P1: 6 บาร์ ต้องตัด 3 (ไม่ใช่ 4) → ต่อเนื่อง 3 = 50% ≥ 43.75% (M ที่ L/8)
rb6 = calc.RebarSelection(main_bars=[("DB12", 6)], As_provided=6.78)
b6 = calc.compute_curtailment_single(rb6, 4.0, 45.0, 1.2)["bottom"][0]
check("6-bar: ตัด ≤ ครึ่ง = 3 (ไม่ใช่ 4)", b6["n_extra_cut"] == 3, b6["n_extra_cut"])
check("6-bar: ต่อเนื่องผ่าน L/8 = 3 (50% ≥ 43.75%)", b6["n_continuous_past_L8"] == 3, b6["n_continuous_past_L8"])
check("5-bar: ตัด 2 · ต่อเนื่อง 3 (60%)",
      calc.compute_curtailment_single(calc.RebarSelection(main_bars=[("DB12", 5)], As_provided=5.65), 4.0, 45.0, 1.2)["bottom"][0]["n_extra_cut"] == 2,
      None)
# 🔴 Codex P2: mixed-size 2-DB12+2-DB10 → ต้องตัดเส้นเล็ก (DB10) เก็บ DB12 (As ≥43.75%)
bm = calc.compute_curtailment_single(calc.RebarSelection(main_bars=[("DB12", 2), ("DB10", 2)], As_provided=3.83), 4.0, 45.0, 1.6)["bottom"][0]
check("mixed: ตัดเบอร์เล็กสุด (DB10) ไม่ใช่ DB12", bm["cut_bars"] == "2-DB10", bm["cut_bars"])
check("mixed: ต่อเนื่อง 2 (DB12 · As 59% ≥43.75%)", bm["n_continuous_past_L8"] == 2, bm["n_continuous_past_L8"])
# single + จุดโหลด → envelope จริง (applicable=True · Path A · ไม่ใช่ approx อีกต่อไป)
o8p = calc.design_beam(calc.BeamInput(b=50, h=55, L=5, fc=240, fy=4000, cover=4,
                                      db_assume=1.6, d_stirrup=0.9, DL=14, LL=9,
                                      point_loads=[calc.PointLoad(kind="LL", P=120, x=2.5)], load_combo=_LC))
cu8p = o8p.to_dict()["curtailment"]
check("single + จุดโหลด → envelope (applicable=True · ไม่ใช่ค่าประมาณ)", cu8p["applicable"] is True, cu8p["applicable"])
check("single + จุดโหลด → method อ้าง envelope", "envelope" in cu8p["method"].lower(), cu8p["method"])
check("single + จุดโหลด → ไม่มี warning ค่าประมาณ", len(cu8p["warnings"]) == 0, cu8p["warnings"])
_b8p = cu8p["bottom"][0]
if _b8p["n_extra_cut"] > 0:
    check("single + จุดโหลด → มี cut_left_m/cut_right_m (envelope position)",
          _b8p.get("cut_left_m") is not None and _b8p.get("cut_right_m") is not None, _b8p)
    # จุดโหลดกลางช่วง (x=2.5=L/2) → M สมมาตร → cut ซ้าย≈ขวา (closed-form property · validate algorithm)
    check("จุดโหลดกลาง → cut ซ้าย≈ขวา (สมมาตร ±5ซม.)",
          abs(_b8p["cut_left_m"] - _b8p["cut_right_m"]) < 0.05, (_b8p["cut_left_m"], _b8p["cut_right_m"]))
    check("cut อยู่ในช่วง [0, L/2) สมเหตุผล",
          0 <= _b8p["cut_left_m"] < 2.5 and 0 <= _b8p["cut_right_m"] < 2.5, (_b8p["cut_left_m"], _b8p["cut_right_m"]))
# single + partial UDL → envelope จริง (applicable=True)
o8q = calc.design_beam(calc.BeamInput(b=30, h=55, L=5, fc=240, fy=4000, cover=4,
                                      db_assume=1.6, d_stirrup=0.9, DL=14, LL=9,
                                      partial_udls=[calc.PartialUDL(kind="LL", w=20, x1=1.5, x2=3.5)], load_combo=_LC))
cu8q = o8q.to_dict()["curtailment"]
check("single + partial UDL → envelope (applicable=True)", cu8q["applicable"] is True, cu8q["applicable"])
# cantilever support → curtailment None (เหล็กหลัก=บน · ไม่ใช่ bottom-cut · Codex P2)
o8c = calc.design_beam(calc.BeamInput(b=30, h=55, L=2.5, fc=240, fy=4000, cover=4,
                                      db_assume=1.6, d_stirrup=0.9, DL=14, LL=9,
                                      support=calc.SupportType.CANTILEVER, load_combo=_LC))
check("cantilever support → curtailment None", o8c.to_dict()["curtailment"] is None, o8c.to_dict()["curtailment"])

# ---- Case 4 · citations + method ครบ ----
print("\nCase 4 · metadata")
check("method อ้าง รูปที่ 8.32", "8.32" in c["method"], c["method"])
check("มี ≥3 citations", len(c["citations"]) >= 3, len(c["citations"]))
check("datum ระบุจุดอ้างอิง (หน้าเสา/ศูนย์เสา)", "เสา" in c["datum"], c["datum"])

# ---- Case 5 · continuous + จุดโหลด → เหล็กบน-ล่างจาก moment envelope จริง (A2a+A2b) ----
print("\nCase 5 · continuous envelope (A2a ล่าง +M · A2b บน −M)")
SI, PL = calc.SpanInput, calc.PointLoad
# 2-span [6,6] · จุดโหลดเยื้องช่วงแรก (x=2.0 ≠ 3.0) → asymmetric
ce = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30, h=60, fc=240, fy=4000,
    cover=4.0, d_stirrup=0.9, db_assume=2.5,
    spans=[SI(6.0, 15.0, 10.0, [PL("LL", 80.0, 2.0)]), SI(6.0, 15.0, 10.0, [])]))["curtailment"]
check("cont+จุดโหลด → applicable=True (บน-ล่าง exact · A2b ลบ half-state)", ce["applicable"] is True, ce["applicable"])
check("cont+จุดโหลด → bottom_exact=True", ce.get("bottom_exact") is True, ce.get("bottom_exact"))
check("cont+จุดโหลด → top_exact=True (A2b)", ce.get("top_exact") is True, ce.get("top_exact"))
check("cont+จุดโหลด → method อ้าง envelope", "envelope" in ce["method"].lower(), ce["method"])
check("cont+จุดโหลด → ไม่มี warning (exact ครบ)", len(ce["warnings"]) == 0, len(ce["warnings"]))
# A2b top: support B (interior) envelope · asymmetric ซ้าย≠ขวา (โหลดเยื้องช่วง A-B)
_teB = next((t for t in ce["top"] if t["support"] == "B"), None)
check("cont top B → envelope=True + cut_third_left/right (asymmetric)",
      bool(_teB) and _teB.get("envelope") and _teB.get("cut_third_left_m") is not None and _teB.get("cut_third_right_m") is not None, _teB)
check("cont top B → cut_half ≤ cut_third แต่ละข้าง (cut group หยุดก่อน inflection)",
      bool(_teB) and (_teB.get("cut_half_left_m") is None or _teB["cut_half_left_m"] <= _teB["cut_third_left_m"] + 1e-6)
      and (_teB.get("cut_half_right_m") is None or _teB["cut_half_right_m"] <= _teB["cut_third_right_m"] + 1e-6),
      _teB and (_teB.get("cut_half_left_m"), _teB.get("cut_third_left_m"), _teB.get("cut_half_right_m"), _teB.get("cut_third_right_m")))
_beAB = next(b for b in ce["bottom"] if b["span"] == "A-B")
check("cont envelope A-B → มี cut_left_m/cut_right_m",
      _beAB.get("cut_left_m") is not None and _beAB.get("cut_right_m") is not None, _beAB)
check("cont envelope A-B → asymmetric (โหลดเยื้องซ้าย x=2.0 → ยื่นซ้ายมากกว่า · cutL<cutR)",
      _beAB["cut_left_m"] < _beAB["cut_right_m"], (_beAB["cut_left_m"], _beAB["cut_right_m"]))
check("cont envelope A-B → cut อยู่ในช่วง [0,L] สมเหตุผล",
      0 <= _beAB["cut_left_m"] <= 6.0 and 0 <= _beAB["cut_right_m"] <= 6.0, (_beAB["cut_left_m"], _beAB["cut_right_m"]))
# parity sanity: ไม่มีจุดโหลด → คง fig-8.32 (ไม่ override envelope)
cn = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30, h=60, fc=240, fy=4000,
    cover=4.0, d_stirrup=0.9, db_assume=2.5,
    spans=[SI(6.0, 15.0, 10.0, []), SI(6.0, 15.0, 10.0, [])]))["curtailment"]
check("cont UDL ล้วน → bottom_exact ไม่ set (fig-8.32 คงเดิม)", cn.get("bottom_exact") is None, cn.get("bottom_exact"))
check("cont UDL ล้วน → bottom ยังเป็น L/8 (cut_eighth_m=0.75 · ไม่ override)",
      near(cn["bottom"][0]["cut_eighth_m"], 0.75), cn["bottom"][0]["cut_eighth_m"])
# symmetric property: จุดโหลดกลางช่วงแรก (x=3.0=L/2) — span A-B ยังเบี้ยวจาก end moment (B≠A) แต่ค่าต้องอยู่ในช่วงสมเหตุผล
cs = calc.design_continuous_beam_exact(calc.ContinuousBeamInput(b=30, h=60, fc=240, fy=4000,
    cover=4.0, d_stirrup=0.9, db_assume=2.5,
    spans=[SI(6.0, 15.0, 10.0, [PL("LL", 80.0, 3.0)]), SI(6.0, 15.0, 10.0, [])]))["curtailment"]
_csAB = next(b for b in cs["bottom"] if b["span"] == "A-B")
check("cont จุดโหลดกลาง → cut_eighth_m = เฉลี่ย (cutL+cutR)/2",
      near(_csAB["cut_eighth_m"], (_csAB["cut_left_m"] + _csAB["cut_right_m"]) / 2.0), _csAB["cut_eighth_m"])

print("\n" + "=" * 60)
print(f" RESULT: {PASS} PASS / {FAIL} FAIL" + ("  ALL GREEN" if FAIL == 0 else "  *** FAIL ***"))
print("=" * 60)
sys.exit(1 if FAIL else 0)
