## สรุปการเปลี่ยนแปลง (Summary)
<!-- ทำอะไร · ทำไม · เฟส/ฟีเจอร์ไหน -->


## Scope Lock (ขอบเขต)
- [ ] แก้เฉพาะไฟล์ที่จำเป็น (no unrelated refactor)
- [ ] **ไม่แตะ engine `calc.py`** (ถ้าจำเป็นต้องแตะ — ติ๊กออก + อธิบายเหตุผล)
- [ ] ไม่มี secret / คีย์
- [ ] ไม่มีไฟล์ build / `.bak` / mockup หลุดเข้ามา

## ประเภท (Type)
- [ ] ฟีเจอร์ใหม่ (feat)
- [ ] แก้บั๊ก (fix)
- [ ] UI/UX
- [ ] เอกสาร / ตั้งค่า (docs / chore)

## ความเสี่ยง (Risk)
- [ ] ต่ำ
- [ ] กลาง
- [ ] สูง

## จุดเสี่ยงที่ควรเพ่ง (High-risk area)
- [ ] engine `calc.py` / สูตรวิศวกรรม
- [ ] Pyodide embed (`embed_calc.py`)
- [ ] กระทบทั้ง 2 โหมด (ช่วงเดียว / ต่อเนื่อง)
- [ ] หน่วยไทย (ตัน / กก. / ksc)
- [ ] a11y / print-CSS / localStorage
- [ ] ไม่มี

## ผลทดสอบ (Tests Run) — บังคับ
```text
# Python (CI รันให้อัตโนมัติด้วย):
python uat_recheck.py        ->  __ / __ PASS
python uat_continuous.py     ->  __ / __ PASS

# In-browser (รันเองในเบราว์เซอร์ · แปะผล/สกรีนช็อต):
runTests()                   ->  52 / 52
runDesignAudit()             ->  27 / 27
viewport ทดสอบ: 1920 / 1085  ·  ทั้ง 2 โหมด
```

## ให้ผู้รีวิวเพ่ง (Reviewer focus)
scope creep · regression ทั้ง 2 โหมด · ความถูกต้องของหน่วย/สูตร · zero-regression (52 + 27) · ความปลอดภัย
