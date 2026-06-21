# Changelog

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/) · เวอร์ชันตาม [SemVer](https://semver.org/)

## [Unreleased]
### ปรับปรุง (รูปด้านข้าง + หน้าตัด · detailing)
- **เส้นบอกระยะ (dim line) เหล็กเสริมหัวเสา/กลางคาน** — เปลี่ยนจากตัวหนังสือลอย → เส้นลูกศรมีหัว · หัวเสาโชว์ระยะยื่นซ้าย/ขวาแยกกัน (เห็น asymmetric ตาม moment envelope ชัด · ยื่นเข้าช่วงในมากกว่าช่วงริม) + ความยาวเหล็กตัดกลางคาน
- **ป้ายเหล็กปลอกย้ายเข้ากลางลำคาน** + halo อ่านทับเส้นปลอก + แยกโซน `@ระยะ(ปลาย)·(กลาง)` (เดิมอยู่ใต้คาน)
- **หน้าตัดบอกเบอร์เหล็ก + แยก "หลัก/เสริมพิเศษ"** — เดิมบอกแค่จำนวน → `บน 2-DB16 หลัก + 2-DB16 เสริม` (mixed-size ครบ) · ใช้ decomposition (`extraBarGroups`) ตัวเดียวกับรูปด้านข้าง/BBS → ทุก surface พูดภาษาเดียวกัน
- **หน้าตัดคาน scale ตามสัดส่วน b×h จริง + วงกลมเหล็กสะท้อนขนาดเบอร์** (audit ความถูกต้องเชิงเรขาคณิต) — เดิม fix viewBox 130×150 → คานสูง/แบนวาดรูปเดียวกัน · เดิมทุกเบอร์รัศมีเท่ากัน (DB10 = DB28). แก้: กล่องคอนกรีต scale `W=b·k, H=h·k` (fit-box คงสัดส่วน) · ปลอก/เหล็ก inset = (cover+ปลอกขนาดจริง) scale จริง · รัศมีวงกลม ∝ db (เบอร์ใหญ่=วงใหญ่ · เบอร์ผสมวาดตามจริง ใหญ่ไปมุม) · เหล็ก tangent กับเส้นปลอก + clamp กันวงกลมทับ/x-span กลับด้าน/ชั้นข้ามกึ่งกลาง (คานสูงแคบ/ตื้น) · ใช้ logic จาก reference `rc-beam-section.js` + vault (verified vs DRMK ตาราง 3.3) · n_layers ยังมาจาก engine · index-only ไม่แตะ engine
### ภายใน
- `runDesignAudit` 50→52→**57** (guard เบอร์เหล็ก + guard แยกหลัก/เสริม + guard สัดส่วนหน้าตัด ≈ b/h จริง (G1) + guard เบอร์ผสม→วงหลายขนาด หน้าล่าง+หน้าบน (G2) · เปลี่ยน guard นับเหล็กหน้าตัดเป็นนับตาม `data-bar` attribute robust ต่อ geometry scale) · index-only
- ทนทานหน้าตัด (จาก adversarial self-review): `_szNum` กัน numeric-input crash · ปลอกอ่านขนาดจริงจาก `dsVal(P.dstir)` (เลิก hardcode 0.9)

## [0.7.0] — 2026-06-11
### เพิ่ม
- **Doubly-reinforced — คานต่อเนื่อง / คานยื่น (เหล็กรับแรงอัดสลับด้าน)** — ขยาย doubly จากช่วงเดียว (v0.6.0) ไปยังคานต่อเนื่อง/คานยื่นที่เกิน ρmax: −M หัวเสา/ปลายยื่น (เหล็กดึงบน · เหล็กอัด **ล่าง**) และ +M ช่วง (เหล็กดึงล่าง · เหล็กอัด **บน**) — แทนที่ hard-fail "หน้าตัดไม่พอ" เดิม · helper `_doubly_design_for_moment` (New Module · `design_beam` ช่วงเดียวไม่แตะ = zero-reg by construction) · ผลตรงกับช่วงเดียวเป๊ะ (face-agnostic · ตาราง+รูปหน้าตัด+**BBS** โชว์ As′ หน้าถูกต้อง)
- **BBS (ตารางตัดเหล็ก) รวมเหล็กรับแรงอัด** — เพิ่มแถวเหล็กอัด As′ ลง BBS ทั้ง 2 โหมด (มาร์ก `TC`/`MC` · ตำแหน่ง "ล่าง·รับอัด·หัวเสา" / "บน·รับอัด·กลางช่วง") → takeoff ครบ ไม่ขัดกับตาราง/หน้าตัด (ปิด sibling-surface gap · รวมช่วงเดียว #27 ที่เดิมก็ขาด)
### ภายใน (กันถดถอย)
- ตาข่ายเทสต์ใหม่ `uat_doubly_continuous` (31 · parity กับ single-span ที่ verify DRMK Ex 3.10) + `runDesignAudit` 46→50 (guard หน้าวางเหล็กอัด −M = ล่าง + BBS มีแถวเหล็กอัด 2 โหมด) · zero-reg: recheck 65 · continuous 25 · multilayer 34 · curtailment 69 · doubly 30 · runTests 8

## [0.6.0] — 2026-06-08
### เพิ่ม
- **Multi-layer rebar (การจัดเหล็กหลายชั้น)** — แก้ honeycomb: เดิมเรียงเหล็กแถวเดียวเสมอ + ระยะห่างไม่รวมมวลรวม → `s_clear = max(db, 2.5, 1.33·d_agg)` · `max_bars_per_layer` (เทียบ DRMK ตาราง 3.3) · `effective_depth_multilayer` (c.g. หลายชั้น · ≤ ชั้นเดียวเสมอ) · guard ρ_provided ≤ ρmax ทุก path · **§A: รูปหน้าตัดดึงเบอร์+จำนวน+ชั้นจาก engine จริง (`detailBars`)** ต่อตำแหน่ง (governing span/support · ปิด display drift ถาวร)
- **Doubly-reinforced beam (คานเสริมเหล็กรับแรงอัด · ช่วงเดียว)** — ปลดล็อกคานแคบ/โหลดหนักที่เกิน ρmax (เดิม error) → เพิ่มเหล็กรับแรงอัด As′ (บน) ตาม DRMK บท 3 (เสริมเหล็กคู่) · As = As1+As2 · ตรวจการครากเหล็กดึง/อัดด้วย strain compatibility · fixed-point design (req↔geometry สอดคล้อง) · **เฉพาะ simply-supported** · โชว์ As′ ในหน้าตัด/ตาราง/วิธีทำ
### ภายใน (กันถดถอย)
- ตาข่ายเทสต์: `uat_multilayer` (34) + `uat_doubly` (30) · `runDesignAudit` 38→46 · baseline sweep (1656 same / 0 regression) · knowledge-first จาก DRMK → vault

## [0.5.0] — 2026-06-07
### เพิ่ม
- **ระยะหยุดเหล็ก (Curtailment / Bar cutoff)** — ระยะตัด-ยื่นเหล็กจริงตาม DRMK รูป 8.32 (เหล็กล่าง L/8 · เหล็กบน L/4·L/3 จากหน้าเสา · เลยจุดดัดกลับ ≥ max(d,12db)) · **moment envelope จริง** เมื่อมีจุดโหลด (ช่วงเดียว + ต่อเนื่อง · asymmetric ซ้าย/ขวา) · รูปด้านข้างคาน + ตาราง + BBS wire ตรง engine
- **Transparency "ดูวิธีทำ"** — แสดงสูตร + แทนค่า + อ้างอิง ว.ส.ท./DRMK ทีละสเต็ป + อัตราส่วนใช้กำลัง D/C (%) 2 โหมด
- **พิมพ์ PDF รายการคำนวณ ก.ว.** — A4 print-CSS + title block + ช่องเซ็น (vector · 2 โหมด)
- **Beam Workspace Phase 1** — ตั้งชื่อกริด + เบอร์คาน (prefix B/GB/RB/CB) + metadata + per-mode grid state (display-only · ไม่แตะ engine)
### ภายใน
- ตาข่ายเทสต์ถาวร: `runTests()` (value parity) + `runDesignAudit()` (UI drift) + `window.__civilTest` hook
- เครื่องมือ dev `tools/web_arch_audit.py` (sensor สุขภาพโครงสร้าง · warn-only ใน CI) · GitHub workflow (branch protection · PR template · CI)

## [0.4.0] — 2026-05-30
### เพิ่ม
- **คานยื่น (Cantilever)** — ส่วนยื่นปลายซ้าย/ขวาบนคานต่อเนื่อง (Three-Moment · เหล็กบน · เฉือนหน้าเสา · Ld · min-depth)
- Smart Load Input — โหลดอัตโนมัติจากไลบรารี ว.ส.ท. (ผนัง / พื้น / จร)
- Design Parameters แสดงทั้ง 2 โหมด · As/ρ ต่อช่วง
### ปรับปรุง
- Design system unify ทั้ง 2 โหมด (support symbols · animation · verdict card · color tokens)
- a11y: ARIA + keyboard · responsive มือถือ · full-width 2-col layout
- ระบบกันพังในแอป: `runTests()` 52/52 + `runDesignAudit()` 27/27

## [0.3.0] — 2026-05-30
### เพิ่ม
- **คานต่อเนื่อง 2–4 ช่วง** — วิเคราะห์แม่นยำ Three-Moment + จุดโหลด + โหลดต่อช่วง
- กราฟ V/M ซ้อน + ตารางเหล็กต่อช่วง + Excel export (ก.ว.-ready)

## [0.2.0] — 2026-05-29
### เพิ่ม
- จุดโหลด (Point loads) 0–5 จุด
- ออกแบบเหล็กปลอก (Shear stirrup · DRMK ว.ส.ท. 1008-38)
- หน่วยไทย (ตัน) ทั้งแอป

## [0.1.0] — 2026-05-29
### เพิ่ม
- เวอร์ชันแรก — ออกแบบคานช่วงเดียว (ดัด · singly-reinforced flexure)
