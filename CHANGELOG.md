# Changelog

รูปแบบตาม [Keep a Changelog](https://keepachangelog.com/) · เวอร์ชันตาม [SemVer](https://semver.org/)

## [Unreleased]
### เพิ่ม
- **Beam Workspace Phase 1 — ตั้งชื่อกริด + เบอร์คาน + metadata** (ทั้ง 2 โหมด · in-memory) — ตั้งชื่อกริดเอง (free-text · cap 8 ตัว) · การ์ดเบอร์คาน (prefix B/GB/RB/CB + เลข + ชั้น + หมายเหตุ · optional ไม่บล็อกคำนวณ) · หัวผล cross-ref "คาน B1 · ช่วงกริด g1–g2 · ชั้น X" · ป้าย "ปลายยื่น" ที่คานยื่น · ชื่อ display-only (engine เข้าถึง by index) · XSS-safe · **ไม่แตะ engine** · runDesignAudit 27→32 (+5 naming guards)
- ตั้งค่า GitHub workflow: branch protection (main + dev), PR template, CI (รันเทสต์ Python ทุก PR), README, CHANGELOG
- **เครื่องมือ dev (ไม่ใช่ฟีเจอร์แอป)** — `tools/web_arch_audit.py` sensor วัดสุขภาพโครงสร้าง `index.html` (script-block size · function length · cross-scope globals · responsibility count → SPLIT verdict · **sensor-only ไม่แตะโค้ด**) + CI step **warn-only** (ไม่บล็อก build) + trend log `tools/arch-trend.jsonl`

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
