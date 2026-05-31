# Civil Calc — เครื่องมือออกแบบคาน คสล. (มาตรฐานไทย)

![CI](https://github.com/PanuwatLab/civilcalc-web/actions/workflows/ci.yml/badge.svg)

เว็บแอปออกแบบคานคอนกรีตเสริมเหล็ก (RC beam) ด้วยวิธีกำลัง (Strength Design Method · SDM)
ตามมาตรฐาน **ว.ส.ท. 1008-38** หน่วยไทย (ตัน / กก. / ksc / ซม.) — ใช้งานในเบราว์เซอร์ ไม่ต้องติดตั้ง

## ✨ ความสามารถ

- **3 โหมด:**
  - **ช่วงเดียว (Single-span)** — คานช่วงเดียว + จุดโหลด 0–5 จุด
  - **ต่อเนื่อง (Continuous)** — 2–4 ช่วง · วิเคราะห์แม่นยำด้วย Three-Moment + จุดโหลด + โหลดต่อช่วง
  - **คานยื่น (Cantilever)** — ส่วนยื่นปลายซ้าย/ขวาบนคานต่อเนื่อง
- ออกแบบ **ดัด** (เหล็กล่าง/บน) + **เฉือน** (เหล็กปลอก ว.ส.ท.) + ตรวจ **แอ่นตัว**
- กราฟ **แรงเฉือน (V) / โมเมนต์ (M)** + รูปหน้าตัดคาน + ตารางเหล็ก
- โหลดอัตโนมัติจากไลบรารี ว.ส.ท. (ผนัง / พื้น / จร) + Load Combinations
- Export Excel (ก.ว.-ready) · รองรับ a11y (ARIA + keyboard) · responsive มือถือ

## 🚀 วิธีรัน

ไม่ต้อง build — เป็นไฟล์ HTML ไฟล์เดียว:

```bash
# เสิร์ฟด้วย Python (แนะนำ — กันปัญหา cache / CORS)
python -m http.server 8777
# เปิดเบราว์เซอร์ที่ http://localhost:8777
```

> VS Code: มี launch config ชื่อ `civilcalc` ใน `.claude/launch.json`

## 🧱 Tech Stack

| ส่วน | เทคโนโลยี |
|---|---|
| Frontend | HTML ไฟล์เดียว + Tailwind (CDN) + vanilla JS |
| เครื่องคำนวณ | **Pyodide** (Python ในเบราว์เซอร์) รัน `calc.py` |
| กราฟ | Inline SVG |
| Excel | ExcelJS (CDN) |
| ฟอนต์ | Sarabun · Inter · JetBrains Mono |

## 📁 โครงสร้างไฟล์

```
index.html         # ตัวแอป (UI + logic + calc.py ที่ฝังไว้)
calc.py            # เครื่องยนต์คำนวณ (Python ล้วน · source of truth · NO external deps)
embed_calc.py      # สคริปต์ฝัง calc.py -> index.html
rebar_table.json   # ตารางขนาดเหล็ก
uat_recheck.py     # เทสต์ engine: ดัด/เฉือน (เทียบ ground-truth ตำรา DRMK)
uat_continuous.py  # เทสต์ engine: ต่อเนื่อง + คานยื่น (closed-form)
design.md          # เอกสารออกแบบ
```

## 🧪 การทดสอบ

```bash
python uat_recheck.py       # flexure / shear เทียบ textbook ground-truth
python uat_continuous.py    # continuous + cantilever closed-form
```

เทสต์ฝั่งเบราว์เซอร์: เปิด Console พิมพ์ `runTests()` · `runDesignAudit()`
CI บน GitHub รันเทสต์ Python อัตโนมัติทุก Pull Request

## 📐 มาตรฐานอ้างอิง

- **หลัก:** ว.ส.ท. 1008-38 (E.I.T. Strength Design Method)
- **อ้างอิง:** มงคล (DRMK) · พงฬ์นธี · วัฒนชัย (ACI 318)
