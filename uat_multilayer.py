"""UAT · Multi-layer rebar arrangement (correctness B · 2026-06-07)
ตรวจ: clear-spacing(+aggregate) · N_max/layer · d จาก c.g. หลายชั้น · multilayer trigger · Mn parity · zero-reg single-layer.
ที่มา: [[Formula - Rebar Clear Spacing & Multi-Layer Arrangement (RC-SDM)]] · DRMK บท1 p15 + บท3 ตาราง3.3 · ACI 25.2.
"""
import sys, math
sys.stdout.reconfigure(encoding="utf-8")
import calc
PASS = FAIL = 0
def chk(name, cond, detail=""):
    global PASS, FAIL
    ok = bool(cond); PASS += ok; FAIL += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" · {detail}" if (detail and not ok) else ""))
def near(a, b, t=0.01): return abs(a - b) < t

print("=" * 64); print(" UAT · Multi-layer rebar (correctness B)"); print("=" * 64)

print("\nCase 1 · clear spacing = max(db, 2.5, 1.33·d_agg)")
chk("DB12 (db=1.2) → s_clear = 1.33·2.0 = 2.66 (aggregate ครอง)", near(calc.min_clear_spacing(1.2), 2.66))
chk("DB16 (db=1.6) → s_clear = 2.66 (aggregate ยังครอง)", near(calc.min_clear_spacing(1.6), 2.66))
chk("DB28 (db=2.8) → s_clear = 2.8 (db ครอง)", near(calc.min_clear_spacing(2.8), 2.8))
chk("DB12 s_clear ≠ 2.5 (เดิม ignore aggregate · บั๊ก honeycomb)", calc.min_clear_spacing(1.2) > 2.5 + 1e-9)

print("\nCase 2 · N_max/layer formula (vs DRMK ตาราง 3.3 · structure)")
# ตาราง 3.3 (cover 2 · stir 0.9 · s 2.5): DB16 b=11.5→2 · b=15.6→3
def nmax_tbl(b, db, s=2.5):
    av = b - 2*2 - 2*0.9
    return max(1, int((av + s) / (db + s) + 1e-9))
chk("DB16 b=11.5 → 2 เส้น/ชั้น (ตาราง3.3)", nmax_tbl(11.5, 1.6) == 2, nmax_tbl(11.5,1.6))
chk("DB16 b=15.5 → 2 · b=15.6 → 3 (boundary ตาราง3.3)", nmax_tbl(15.5,1.6)==2 and nmax_tbl(15.6,1.6)==3)
chk("DB20 b=16.7 → 2 · b=16.8 → 3 (ตาราง3.3)", nmax_tbl(16.7,2.0)==2 and nmax_tbl(16.8,2.0)==3)
# engine (d_agg=2.0): 30cm
av30 = 30 - 2*4 - 2*0.9
chk("engine DB20 ใน 30cm → 4 เส้น/ชั้น", calc.max_bars_per_layer(av30, 2.0) == 4, calc.max_bars_per_layer(av30,2.0))

print("\nCase 3 · effective depth จาก c.g. หลายชั้น")
h, cov, stir, db = 60, 4, 0.9, 2.5
d_single = calc.compute_effective_depth(h, cov, stir, db)
chk("nl=1 → d == compute_effective_depth เดิม (zero-reg)",
    near(calc.effective_depth_multilayer(h, cov, stir, db, 3, 1), d_single))
# 5 เส้น 2 ชั้น (3+2): c.g. hand = (3·6.15+2·11.15)/5 = 8.15 → d = 51.85
d2 = calc.effective_depth_multilayer(h, cov, stir, db, 5, 2)
chk("5 เส้น 2 ชั้น(3+2) → d = 51.85 (hand-calc c.g.)", near(d2, 51.85))
chk("d_multilayer < d_single เสมอ (conservative · safety)", d2 < d_single - 0.01)
# 3 ชั้น ลึกกว่า 2 ชั้น
d3 = calc.effective_depth_multilayer(h, cov, stir, db, 9, 3)
chk("d_3layer < d_2layer (c.g. ลึกขึ้น)", d3 < d2)
chk("_layer_counts(5,2) = [3,2] (ชั้นนอกเต็มก่อน)", calc._layer_counts(5, 2) == [3, 2])
chk("_layer_counts(7,3) = [3,2,2]", calc._layer_counts(7, 3) == [3, 2, 2])

print("\nCase 4 · select_rebar multilayer trigger")
# คานแคบ 20cm + โหลดหนัก → ต้องหลายชั้น (เดิม fail/None)
o = calc.design_beam(calc.BeamInput(b=20, h=60, L=5, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9, DL=40, LL=24))
chk("20×60 DL40/LL24 → rebar ไม่ None (multilayer solve · เดิม fail)", o.rebar is not None)
if o.rebar:
    chk("→ n_layers ≥ 2 (จัดหลายชั้น)", o.rebar.n_layers >= 2, o.rebar.n_layers)
    chk("→ fits_in_one_layer = False", o.rebar.fits_in_one_layer is False)
    # Mn parity ที่ d เล็กลง
    a = calc.compute_stress_block_depth(o.rebar.As_provided, 4000, 240, 20)
    chk("→ Mn = As·fy·(d−a/2) parity (d หลายชั้น)", near(o.Mn, o.rebar.As_provided*4000*(o.d_actual - a/2), 10))

print("\nCase 5 · zero-reg single-layer (เคสปกติ ไม่ขึ้นชั้น)")
o2 = calc.design_beam(calc.BeamInput(b=30, h=60, L=5, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9, DL=20, LL=12))
chk("30×60 DL20/LL12 → n_layers == 1 (ปกติ)", o2.rebar and o2.rebar.n_layers == 1)
chk("→ d == single-layer formula (ไม่ขยับ)", near(o2.d_actual, calc.compute_effective_depth(60, 4, 0.9,
        next(s['diameter_cm'] for s in calc._load_rebar_table()['sizes'] if s['name']==o2.rebar.main_bars[0][0]))))

print("\nCase 6 · section เล็กเกิน/เกิน 3 ชั้น → fail graceful (raise domain error หรือ None · ไม่ crash)")
try:
    o3 = calc.design_beam(calc.BeamInput(b=20, h=40, L=6, fc=180, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9, DL=50, LL=40))
    ok6 = (o3.rebar is None) or (not o3.passes) or (o3.rebar.n_layers <= calc.MAX_REBAR_LAYERS)
except calc.CivilCalcError:
    ok6 = True   # หน้าตัดเล็กเกิน → raise domain error ชัดเจน (ถูกต้อง · caller catch)
chk("คานเล็กมาก+โหลดหนักมาก → graceful (domain error/None · ไม่ crash · n_layers ≤ 3)", ok6)
chk("MAX_REBAR_LAYERS = 3 (cap)", calc.MAX_REBAR_LAYERS == 3)

print("\nCase 7 · Codex review fixes (#26)")
# P1: avail < db → 0 เส้น/ชั้น (ไม่ยอมรับ layout ที่เหล็กไม่ลอด)
chk("max_bars_per_layer(0.2, DB12) = 0 (เหล็กไม่ลอด · Codex P1)", calc.max_bars_per_layer(0.2, 1.2) == 0)
chk("max_bars_per_layer(2.2, DB25) = 0 (DB25 2.5cm ไม่ลอด bay 2.2cm)", calc.max_bars_per_layer(2.2, 2.5) == 0)
o7 = calc.design_beam(calc.BeamInput(b=10, h=50, L=4, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9, DL=5, LL=3))
chk("b=10cm (avail 0.2) → rebar=None/fail (แนะขยาย · ไม่ยอมรับ impossible)", o7.rebar is None or not o7.passes)
# P2 1373: tie-break ต้องเลือก db เล็ก (d ใหญ่ · pass) ไม่ใช่ db ใหญ่ (false-fail) ในเคส multilayer
o8 = calc.design_beam(calc.BeamInput(b=18, h=45, L=7, fc=240, fy=4000, cover=4, db_assume=2.5, d_stirrup=0.9, DL=10, LL=6))
chk("b=18×45 multilayer → solve ได้ (db เล็ก d ใหญ่ · ไม่ false-fail · Codex 1373)", o8.rebar is not None and o8.passes)
if o8.rebar:
    maxdb8 = max(int("".join(c for c in nm if c.isdigit())) for nm, _ in o8.rebar.main_bars)
    chk("→ ไม่เลือก DB ใหญ่สุด (DB28) ที่ d ต่ำ → เลือก db ≤ 25 (d ใหญ่กว่า)", maxdb8 <= 25, f"maxdb={maxdb8}")

print("\nCase 8 · Codex P1 #26 round-2 — over-reinforced ที่ d จริงหลายชั้น → FAIL (ไม่ accept ด้วย phi_Mn อย่างเดียว)")
o9 = calc.design_beam(calc.BeamInput(b=14, h=35, L=4, fc=240, fy=4000, cover=4, d_stirrup=0.9, DL=15, LL=9))
chk("b=14×35 narrow+heavy → passes=False (ไม่ false-pass · capacity/ρ ไม่พอ)", not o9.passes)
chk("→ combo ที่เลือกไม่ over-reinforced (select กรอง ρ_prov ≤ ρmax) หรือไม่มี combo",
    (not o9.rebar) or o9.rebar.As_provided / (14 * o9.d_actual) <= o9.rho_max + 1e-9)
# Codex P1 round-3 (#26 · 1551): over-reinforced path ที่ recompute ไม่ raise → ρ_provided check ต้องจับ
o10 = calc.design_beam(calc.BeamInput(b=12, h=30, L=5, fc=240, fy=4000, cover=3, d_stirrup=0.9, DL=5, LL=3))
chk("b=12×30 L5 → passes=False (section ไม่พอ · ไม่ false-pass)", not o10.passes)
if o10.rebar:   # select กรอง over-reinforced → combo ที่เลือกต้อง ρ_prov ≤ ρmax
    chk("→ combo ที่เลือก ρ_provided ≤ ρmax (select กรอง over-reinforced)",
        o10.rebar.As_provided / (12 * o10.d_actual) <= o10.rho_max + 1e-9)
# Codex P2 #26 (1379): false-failure fix — เคยเลือก 2-DB20(2ชั้น over) → fail · ตอนนี้เลือก 3-ชั้น valid → solve
o11 = calc.design_beam(calc.BeamInput(b=12, h=30, L=3, fc=240, fy=4000, cover=3, d_stirrup=0.9, DL=12, LL=7.2))
chk("b=12×30 L3 → solve ได้ (select เลี่ยง over-reinforced → 3-ชั้น valid · ไม่ false-fail · Codex P2)", o11.passes)
if o11.rebar:
    chk("→ combo valid ρ_provided ≤ ρmax", o11.rebar.As_provided / (12 * o11.d_actual) <= o11.rho_max + 1e-9)
# safety-net: design ρ_provided guard (continuous path) ยังทำงานเมื่อ select คืน over (กรณีไม่ส่ง h/rho_max)
_rc = calc._safe_flexure_design(30, 12, 30, 240, 4000, 4, 0.9, 1.6)
chk("continuous _safe_flexure_design narrow → passes=False (guard ครบ 2 path)", not _rc["passes"])

print("\n" + "=" * 64)
print(f" RESULT: {PASS} PASS / {FAIL} FAIL" + ("  ALL GREEN" if FAIL == 0 else "  *** FAIL ***"))
print("=" * 64)
sys.exit(1 if FAIL else 0)
