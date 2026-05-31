# Civil Calc Web App · Design Spec

> **For: Claude Design (claude.ai artifact generator)**
> **From: Claude Code (build assistant) on behalf of Panuwat Nu (architect · non-dev)**
> **Date: 2026-05-28**
> **Scope: Session 1 MVP (5-6 hr build target after mockup delivered)**

---

## 0 · README — How to use this doc

This is a **complete, self-contained design brief** for generating a beautiful HTML mockup of "Civil Calc Web App". You will not have any chat-context — everything you need is in this document.

**What you should produce:**
- A **single self-contained `index.html` file**
- Tailwind via CDN (no build step)
- Vanilla JavaScript only (for demo state transitions — NO React, NO build chain)
- Inline SVG for M/V diagrams (no D3 build needed for mockup — static SVG is fine)
- All 6 mockup states (boot, ready, calculating, result-pass, result-fail, error) — present them as separately viewable views/sections so we can see each state, OR use buttons to toggle between states
- Beautiful · professional · Thai-language · engineering-grade

**Constraint:** The mockup is for **visual validation only**. Real Pyodide + calculation logic will be wired in afterwards by the build assistant. So your job = make it look amazing with mock data.

---

## 1 · Product context

### 1.1 What we're building
A **single-page web application** that performs Thai-compliance Reinforced Concrete (RC) beam design (singly-reinforced flexure, per ว.ส.ท. 1008-38 / มงคล DRMK textbook). User enters beam geometry + materials + loads → app computes shear/moment diagrams + recommends rebar combination + exports Excel report.

### 1.2 Who uses it
- **Primary persona:** Panuwat Nu — Thai architect, non-developer, designs small-to-medium residential/commercial buildings. Uses on laptop in office + mobile/tablet on construction site.
- **Secondary:** Thai junior engineers and draftspeople (preliminary design / sanity check).
- **Tertiary:** Senior engineers (วิศวกร ก.ว.) reviewing junior work.

### 1.3 Why this exists
Phase 1 of this calculator is a CLI Python skill — only usable via a chat assistant. The web app removes that friction: open browser → use immediately. Generates a printable/sendable Excel that goes into official "รายการคำนวณ" (calculation submissions to regulators).

### 1.4 North star quote
> "เปิดเว็บแล้ว user ร้อง WOW ใน 3 วินาที · ใช้ครั้งแรกไม่ต้องอ่าน manual · เห็นทฤษฎี structural engineering มีชีวิตผ่านการ animate · จบที่ confidence ว่าคำตอบถูก · ส่ง Excel แล้วลูกค้าทึ่ง"

---

## 2 · Locked decisions

| # | Decision | Locked value | Reason |
|---|---|---|---|
| 1 | Domain/codename | `civilcalc.app` | Product brand · separate from Panuwat Lab (SketchUp plugins) |
| 2 | Access | Public free | Build user base · Pro tier later if viable |
| 3 | Branding | New wordmark + concrete-block icon · NOT Panuwat Lab logo | Separate identity |
| 4 | Tagline | "ออกแบบคาน RC สวยงาม · ตรงทฤษฎี · ใช้ง่าย" | Thai-first · 3 benefits in 1 line |
| 5 | Calc scope | Flexure-only (shear placeholder for Session 2) | Phase 1 skill scope |
| 6 | Sound | Auto-detect (laptop ON · mobile OFF) · Settings toggle | WOW on laptop · respect mobile env · **defer Session 6 — don't implement in mockup** |
| 7 | Language | Thai only | Phase 1 · monolingual focus |
| 8 | Tech | Single HTML + CDN libraries · NO build chain | Speed · simplicity |

---

## 3 · Scope — Session 1 MVP

### 3.1 Must have (in mockup)

| # | Feature | Notes |
|---|---|---|
| F1 | Form: geometry (b, h, L) + materials (f'c, fy) + support type | Sliders + text input where helpful |
| F2 | Loads: 1 UDL with DL/LL split + 1-5 point loads (each with magnitude, position, DL/LL toggle) | Drag handles on beam schematic |
| F3 | Self-weight auto checkbox (γ_concrete = 2400 kg/m³ → added to DL) | Default ON |
| F4 | Sample preset buttons: "บ้าน 2 ชั้น", "อาคารพาณิชย์", "ตัวอย่าง 9.2 มงคล" | 1-click pre-fill |
| F5 | Beam schematic (top) — shows supports + UDL arrows + point load arrows + dimensions | Inline SVG |
| F6 | Shear (V) diagram (middle) — blue line, x-axis shared with beam | Inline SVG |
| F7 | Moment (M) diagram (bottom) — red line, **positive M plotted BELOW x-axis** (LOCK · Thai/ACI convention) | Inline SVG |
| F8 | Synced vertical hover line across beam + V + M with 3-value tooltip (x, V(x), M(x)) | Critical interaction |
| F9 | Live re-render on input change with `ease-out 0.25s` CSS transition | Path `d` attribute transition |
| F10 | Result panel: verdict ✅/❌ · max V, max M, position · ρ values · rebar combo · safety margin % | Card-based layout |
| F11 | Auto-suggest section fix when fails | "ลอง h = 55 cm หรือ b = 30 cm" |
| F12 | MPa vs ksc warning toast (detect fc 10-100) | Non-blocking |
| F13 | Excel export button (1 sheet · with M/V diagram image) | Mock the button only |
| F14 | Disclaimer banner (top, persistent) | "⚠️ ผลคำนวณ preliminary · ต้องตรวจสอบโดยวิศวกร ก.ว." |
| F15 | Mobile-responsive single-column layout (< 768px) | Form → diagrams → result |
| F16 | Shear stirrup placeholder | "เหล็กปลอก: จะคำนวณใน Session 2" (transparent · not silent) |

### 3.2 Defer to Session 2+ (do NOT include in mockup)
- Click-to-pin point on diagram
- Cross-section view with live rebar
- Theory animations (stress block · failure modes)
- Citation pop-ups with PDF snippets
- Sound effects
- Dark mode
- Multi-language

### 3.3 Out of scope entirely
- Account / auth
- Cloud save
- Real-time collaboration
- Backend API

---

## 4 · Tech constraints (final wire-up; affects mockup decisions)

- **Single index.html file** (HTML + embedded `<style>` and `<script>`)
- **CDN libraries only:**
  - Tailwind via `<script src="https://cdn.tailwindcss.com"></script>` (Play CDN)
  - Sarabun font via Google Fonts
  - Inter font via Google Fonts
  - JetBrains Mono via Google Fonts (for numbers)
- **No React · no Vue · no Svelte**
- **No build chain · no npm install**
- **For mockup state demos:** vanilla JS toggling visibility / classes is fine

---

## 5 · Visual design system

### 5.1 Color palette — "Concrete Workshop" theme

```
/* Primary — structural / steel */
--deep-steel-blue: #1E3A5F   /* header bg · primary buttons */
--hot-rebar-amber: #F59E0B   /* CTAs · highlights · accent */

/* Background — concrete */
--concrete-light: #F5F5F0    /* page bg */
--concrete-mid:   #E8E5DD    /* card bg variant */
--concrete-dark:  #4A4A45    /* dark text · dark mode bg (future) */

/* Status */
--pass-green:     #10B981    /* verdict OK · safe margin > 0 */
--warn-yellow:    #FBBF24    /* tolerance · soft warnings */
--fail-red:       #EF4444    /* fail · errors · over-reinforced */

/* Info */
--citation-sky:   #0EA5E9    /* links · hover · info popovers */

/* Diagram colors (LOCKED · engineering convention) */
--shear-blue:     #2563EB    /* V diagram line */
--moment-red:     #DC2626    /* M diagram line */
--beam-graphite:  #1F2937    /* beam schematic line */
--load-amber:     #F59E0B    /* load arrows (UDL + point) */

/* Stress gradient (for future: blue → amber → red) */
```

### 5.2 Typography

```
/* Imports */
@import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* Stack */
font-thai:    'Sarabun', 'Inter', system-ui, sans-serif
font-en:      'Inter', 'Sarabun', system-ui, sans-serif
font-mono:    'JetBrains Mono', ui-monospace, monospace

/* Scale */
H1: 36px / 44 line · semibold (600) · letter-spacing -0.02em
H2: 28px / 36 · semibold
H3: 22px / 30 · medium (500)
H4: 18px / 26 · medium
Body: 16px / 24 · regular (400)
Label: 14px / 20 · medium · letter-spacing 0.01em
Small: 13px / 18 · regular
Tiny: 11px / 14 · medium (caps · letter-spacing 0.05em for axis labels)

/* Number/formula display ALWAYS monospace */
Number-display: JetBrains Mono 16px · right-aligned · tabular-nums
Citation:       JetBrains Mono 13px
```

### 5.3 Spacing scale (Tailwind defaults)
4px base · use 4, 8, 12, 16, 20, 24, 32, 48, 64 (Tailwind: 1, 2, 3, 4, 5, 6, 8, 12, 16)

### 5.4 Component style

```
Buttons:
  - rounded-xl (12px corner radius · friendly)
  - shadow-sm at rest · shadow-md on hover · scale-[0.97] on active
  - Transition: all 150ms ease-out
  - Primary: bg deep-steel-blue · text white · hover bg-slate-700
  - Accent/CTA: bg hot-rebar-amber · text white · hover bg-amber-600
  - Ghost: text deep-steel-blue · hover bg slate-100
  - Destructive: bg fail-red · text white

Cards:
  - bg white
  - border 1px solid slate-200 (subtle)
  - rounded-2xl (16px)
  - shadow-sm
  - padding p-6 (24px)
  - hover (if clickable): border-citation-sky

Inputs:
  - Style: underline (NOT boxed · modern feel)
  - Border-bottom 2px solid slate-300 at rest
  - Focus: border-bottom 2px solid deep-steel-blue + subtle bg highlight
  - Error: border-bottom 2px solid fail-red + shake animation 200ms
  - Padding: pb-2 · pt-1
  - Font-size: 16px (NEVER smaller — iOS zoom prevention)

Sliders:
  - Track: 4px height · bg slate-200 · rounded
  - Filled track: bg deep-steel-blue
  - Thumb: 20px circle · bg deep-steel-blue · shadow-md · hover scale-110

Toggle pills (for grade selection · DL/LL):
  - Group with rounded-full container · bg slate-100
  - Active pill: bg deep-steel-blue · text white · shadow-sm
  - Inactive: text slate-600

Checkbox:
  - 20px square · rounded · border-2 slate-300
  - Checked: bg deep-steel-blue · white checkmark

Disclaimer banner:
  - bg amber-50 · border-l-4 border-amber-500 · text amber-900 · py-3 px-4 · rounded-r-md
```

---

## 6 · Layout

### 6.1 Desktop (≥1024px)

```
┌─────────────────────────────────────────────────────────────────────┐
│ HEADER (deep-steel-blue · h-16)                                     │
│  [🏗️ Civil Calc]    "ออกแบบคาน RC สวยงาม · ตรงทฤษฎี · ใช้ง่าย"   v0.1│
├─────────────────────────────────────────────────────────────────────┤
│ DISCLAIMER BANNER (amber-50 · h-12)                                 │
│  ⚠️ ผลคำนวณ preliminary · ต้องตรวจสอบโดยวิศวกร ก.ว. ก่อนใช้งานจริง   │
├─────────────────────────────────────────────────────────────────────┤
│ MAIN (max-w-7xl · mx-auto · grid 3-column 320 / flex / 400)         │
│ ┌───────────┐  ┌──────────────────────────┐  ┌──────────────────┐  │
│ │  INPUT    │  │  DIAGRAM PANEL           │  │  RESULT PANEL    │  │
│ │  (left)   │  │  (center · stack 3 SVGs) │  │  (right · sticky)│  │
│ │           │  │                          │  │                  │  │
│ │ Sample    │  │  Beam schematic          │  │  Verdict ✅      │  │
│ │ presets   │  │  ──────────────────      │  │  Safety bar      │  │
│ │           │  │   ╲    ↓↓↓↓    ╱         │  │                  │  │
│ │ Geometry  │  │    ╲ ___________╱         │  │  Max V: 25.4 kN  │  │
│ │  b: [─●─] │  │                          │  │  Max M: 28.7 kN·m│  │
│ │  h: [─●─] │  │  Shear diagram           │  │  at x=2.25m      │  │
│ │  L: [─●─] │  │  ───────                 │  │                  │  │
│ │           │  │   _____                  │  │  ρ = 0.0098      │  │
│ │ Materials │  │        ─────             │  │  As = 11.2 cm²   │  │
│ │  fc: [▼]  │  │                          │  │                  │  │
│ │  fy: [pill│  │  Moment diagram          │  │  Rebar:          │  │
│ │   group]  │  │  ───────                 │  │  3-DB25          │  │
│ │           │  │       ___                │  │  (As=14.73 cm²)  │  │
│ │ Support   │  │      /   \               │  │                  │  │
│ │  [○○●]    │  │     /     \              │  │  Stirrup: TBD S2 │  │
│ │           │  │   _/       \_            │  │                  │  │
│ │ Loads     │  │                          │  │  [📥 Excel]      │  │
│ │  UDL: ... │  │                          │  │  [🔁 รีเซ็ต]    │  │
│ │  Point: + │  │                          │  │                  │  │
│ │           │  │                          │  │                  │  │
│ │ Advanced ▼│  │                          │  │                  │  │
│ │           │  │                          │  │                  │  │
│ │ [คำนวณ ▶] │  │                          │  │                  │  │
│ └───────────┘  └──────────────────────────┘  └──────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│ FOOTER (concrete-mid · h-12 · small text)                           │
│  Phase 1 MVP · v0.1.0 · ตำรา: มงคล DRMK + ว.ส.ท. · ❤️ in Thailand    │
└─────────────────────────────────────────────────────────────────────┘
```

- Container: `max-w-7xl mx-auto px-6 py-6`
- Grid: `grid grid-cols-[320px_1fr_400px] gap-6`
- Sticky right column on scroll (`sticky top-6`)
- All sections have rounded-2xl card style

### 6.2 Tablet (768-1023px)
2-column: Input (40%) | Diagrams (60%) — Result panel moves below diagrams as full-width card

### 6.3 Mobile (<768px)
1-column vertical stack in this exact order:
1. Header
2. Disclaimer banner
3. Sample preset buttons (horizontal scroll if needed)
4. Input form (full-width card)
5. "คำนวณ" big button (sticky bottom on scroll · full-width)
6. (after calc) Diagram panel (full-width · 3 stacked SVGs)
7. Result panel (full-width card)
8. Footer

Touch targets: minimum 44×44px. Sliders use bigger thumbs (24px).

---

## 7 · Page structure (sections + components)

### 7.1 Header
- **Left:** Logo placeholder (concrete-block icon · monochrome white · 24×24) + wordmark "Civil Calc" (Inter semibold 20px white)
- **Center (desktop only):** Tagline "ออกแบบคาน RC สวยงาม · ตรงทฤษฎี · ใช้ง่าย" (Sarabun 14 white opacity 80%)
- **Right:** Version pill "v0.1.0" (small · rounded-full · bg-white/20 · text-white text-xs)

### 7.2 Disclaimer banner
Single line · amber theme · warning icon · "⚠️ ผลคำนวณ preliminary · ต้องตรวจสอบโดยวิศวกร ก.ว. ก่อนใช้งานจริง" · close button (X) on right (state: dismissible but remembers via localStorage — for mockup just show it always)

### 7.3 Input panel (left column · 320px wide)

#### 7.3.1 Sample preset buttons (top)
3 horizontal buttons in a row:
- 🏠 บ้าน 2 ชั้น (residential default)
- 🏢 อาคารพาณิชย์ (commercial)
- 📚 ตัวอย่าง 9.2 มงคล (textbook)

Style: small pill buttons · ghost variant · 1-click pre-fills entire form below. Hover: subtle lift + amber border.

#### 7.3.2 Geometry section
H3 "🏗️ ขนาดและช่วง"

Three sliders with dual control (slider + number input + unit label):
- **ความกว้าง b** : slider range 15-60 cm (step 5) · default 25 · "cm"
- **ความสูง h** : slider range 30-80 cm (step 5) · default 50 · "cm"
- **ความยาวคาน L** : slider range 1-10 m (step 0.1) · default 4.5 · "m"

Layout per slider:
```
ความกว้าง b [tooltip ⓘ]                    [25] cm
[───────●────────────────]
```
The number input and slider stay in sync (drag slider → number updates; type number → slider position updates).

#### 7.3.3 Support type
H3 "🪨 ประเภทรองรับ"
Toggle pill group (3 options, full-width):
- รองรับธรรมดา (simply-supported · default · icon `△───△`)
- ปลายยื่น (cantilever · icon `▓───`)
- ต่อเนื่อง (continuous · icon `△─△─△`)

When "continuous" selected, show secondary toggle:
- ช่วงปลาย (exterior span · Mu = wu·Ln²/11)
- ช่วงใน (interior span · Mu = wu·Ln²/14)

#### 7.3.4 Materials section
H3 "🪨 วัสดุ"

**f'c (กำลังคอนกรีต):**
Dropdown with common Thai grades + custom input:
- 180 ksc (เกรดธรรมดา)
- 210 ksc
- 240 ksc (default · พื้นฐานบ้าน) 
- 280 ksc
- 350 ksc
- 400 ksc
- 450 ksc
- (custom number input)

If user types 10-100 → show non-blocking warning toast "🤔 หมายถึง {value*10} ksc หรือไม่? (ที่ใส่อาจเป็น MPa)"

**fy (เกรดเหล็ก):**
Toggle pill group with 4 colors:
- SR24 (เงิน · smooth round)
- SD30 (ทองอ่อน)
- **SD40 (ทอง · default)**
- SD50 (ทองเข้ม)

Each pill shows grade name + fy value (e.g., "SD40 · 4000 ksc"). Color of pill reflects rebar visual color.

#### 7.3.5 Loads section
H3 "⬇️ น้ำหนักบรรทุก"

**Self-weight checkbox (top):**
```
☑ คำนวณน้ำหนักคานอัตโนมัติ (γ = 2,400 kg/m³)
   → เพิ่ม {auto-calc value} kN/m เป็น DL
```
Default checked. When checked, computes `γ·b·h·g = 2.4·(b/100)·(h/100)·9.81` and shows the value live (changes when b/h change).

**UDL row:**
```
UDL (เต็มความยาว)
  ค่า:   [─●──────] [____] kN/m
  ประเภท: [DL] [LL ●]   ← toggle pill 2 options
```
Default: value=3.0 · type=LL

**Point loads section:**
Header row "จุดน้ำหนัก (Point Loads)" + small "+ เพิ่ม" button (max 5)

Each point load row (compact):
```
┌───────────────────────────────────────────────────────┐
│ Load #1                                          [✕]  │
│  ขนาด:     [10] kN                                    │
│  ตำแหน่ง x: [─────●──────] [2.25] m                   │
│  ประเภท:    [DL]  [LL ●]                              │
└───────────────────────────────────────────────────────┘
```

**Critical interaction:** position slider syncs **bidirectionally** with a draggable handle on the beam schematic above. Drag handle on beam → x value updates here. Type x here → handle on beam snaps with `transition 0.2s ease-out`.

Default state: 0 point loads (collapsed empty state with just "+ เพิ่ม" button).

#### 7.3.6 Advanced (collapsible)
H3 "⚙️ ตัวเลือกขั้นสูง" with chevron · `<details>` element · closed by default.

Inside:
- **ระยะหุ้ม cover** (cm) · default 3.0 · range 2-7.5
- **เหล็กปลอก stirrup grade** dropdown: RB6 / RB9 (default) / DB10
- **เหล็กยืน assumed db** dropdown: DB12 / DB16 (default) / DB20 / DB25
- **Load combination:** toggle [1.2D+1.6L (ACI 318-19 default)] [1.4D+1.7L (ว.ส.ท. legacy)]

#### 7.3.7 Submit button
Full-width primary button at bottom of left panel:
```
[ 🧮 คำนวณ ]
```
Style: large (h-14) · accent (amber) · rounded-2xl · shadow-md · hover lift

When loading: spinner inline + text "กำลังคิดให้ครับ..."
When Pyodide not ready: disabled + "กำลังเตรียมเครื่องคำนวณ..."

### 7.4 Diagram panel (center column · flex)

Title bar at top: "📊 แผนภาพคาน" + small toggle "แสดง grid: [on/off]"

**Stack 3 SVGs vertically with SHARED x-axis:**

#### 7.4.1 Beam schematic (top · height ~140px)
- Horizontal beam line (graphite gray · 4px thick · with subtle gradient for depth)
- Supports at ends (triangles for simply-supported · hatched fixed-wall for cantilever · 3 triangles for continuous)
- UDL: array of small down-arrows (amber) along entire span · "w = 3.0 kN/m" label above middle
- Each point load: single big down-arrow (amber · thicker) at its x position · magnitude label above (e.g., "10 kN")
- Each point load has a **circular drag handle** (24px · amber border · white fill) at its x position on the beam line — this is the bidirectional handle
- Dimension lines below beam showing L (with arrows + "4.5 m" label)
- x-axis ticks below (0, L/4, L/2, 3L/4, L)

#### 7.4.2 Shear (V) diagram (middle · height ~160px)
- x-axis horizontal at vertical center (zero-line · slate-300 dashed)
- V(x) curve: solid blue line · 2px stroke · with subtle filled area (blue at 8% opacity) between curve and zero-line
- Y-axis on left with tick labels (kN)
- Max V value annotated with small pill label (blue bg · white text · arrow pointer)
- Sign convention: positive V above x-axis · negative below

#### 7.4.3 Moment (M) diagram (bottom · height ~180px)
- x-axis horizontal at vertical CENTER
- M(x) curve: solid red line · 2px stroke · with subtle filled area (red at 8% opacity)
- **🔥 CRITICAL: Positive moment (sagging) is plotted BELOW the x-axis. Negative moment (hogging) is plotted ABOVE the x-axis.** This is non-negotiable Thai/ACI engineering convention.
- For simply-supported with downward loads → M curve is entirely below x-axis (parabolic for UDL · piecewise linear with point loads)
- For cantilever → M curve is entirely above x-axis (all negative)
- Y-axis on left with tick labels (kN·m)
- Max M value annotated with pill label (red bg · white text · arrow pointer)
- Critical x position highlighted with dashed vertical line + label "x = 2.25 m"

#### 7.4.4 Synced hover interaction
When user moves mouse over ANY of the 3 SVGs:
- A vertical dashed line (slate-400 · 1px) appears at cursor x position, spanning across all 3 stacked SVGs (beam + V + M)
- A floating tooltip appears (positioned to right of cursor, above current SVG)
- Tooltip content (3 lines):
  ```
  x = 2.13 m
  V(x) = 4.82 kN
  M(x) = 27.4 kN·m
  ```
- Style: bg slate-900 · text white · text-sm · rounded-md · shadow-lg · px-3 py-2 · pointer-events-none · arrow notch

On mobile: tap to show line + tooltip (sticky until tap elsewhere)

#### 7.4.5 Re-render animation
When any input changes (b/h/L slider drag, point load drag, etc.):
- All path `d` attributes update with CSS transition: `transition: d 0.25s ease-out`
- Axis labels update without animation (instant)
- Avoid spring/bouncy — engineering data should feel deterministic

### 7.5 Result panel (right column · 400px)

#### 7.5.1 Verdict header (large · prominent)
**Pass state:**
```
┌─────────────────────────────┐
│  ✅ ผ่าน                     │
│  safe margin +12.3%         │
└─────────────────────────────┘
```
Style: bg gradient (pass-green to emerald-600) · text white · rounded-2xl · py-6 px-5 · with subtle pattern overlay (e.g., 10% white dots).

**Fail state:**
```
┌─────────────────────────────┐
│  ❌ ไม่ผ่าน                  │
│  φMn = 25.4 < Mu = 28.7     │
│  ขาดอยู่ 11.5%               │
└─────────────────────────────┘
```
Style: bg gradient (fail-red to red-600) · text white.

#### 7.5.2 Safety margin bar (visualization)
```
Safety Margin
[████████████████░░░░░░] +12.3%
   Required         Reserve
```
- Filled portion: green (or red if negative) · animated fill (0 → final % over 1.5s ease-out)
- Track: slate-200
- Tick at 0% boundary
- Color zones (legend below): red (<0) · orange (0-5) · yellow (5-15) · green (15-30) · blue (>30 = over-designed)

#### 7.5.3 Key numbers card
```
┌─────────────────────────────┐
│  Wu = 11.33 kN/m            │
│  Reactions: R₁ = 25.5 kN    │
│             R₂ = 25.5 kN    │
│  Max V = 25.5 kN at x = 0   │
│  Max M = 28.67 kN·m         │
│           at x = 2.25 m     │
└─────────────────────────────┘
```
Format: label left · value right (monospace · right-aligned) · alternating row bg (slate-50/white).

#### 7.5.4 Design parameters card
```
β1     = 0.85
ρb     = 0.02622
ρmin   = 0.00350
ρmax   = 0.01966
ρ_design = 0.00855
As_req = 7.35 cm²
```

#### 7.5.5 Rebar selection card (highlighted · amber accent)
```
┌──────────────────────────────┐
│  🪙 เหล็กที่เลือก              │
│                              │
│  3-DB25                      │
│  As_provided = 14.73 cm²     │
│  (margin +21%)               │
│                              │
│  เหล็กปลอก: คำนวณ Session 2 │
└──────────────────────────────┘
```
The rebar combo is THE main answer · should pop visually. Use bg-amber-50 · border-2 border-amber-400 · larger text for the combo line (Sarabun semibold 24px).

#### 7.5.6 Auto-suggest (FAIL state only)
When verdict = fail, show below verdict:
```
💡 คำแนะนำ
ลองเพิ่มขนาดคานเป็น:
  • h = 55 cm (เพิ่ม 5)
หรือ
  • b = 30 cm (เพิ่ม 5)
[ลองเลย →]   ← click to auto-apply

หรือเปลี่ยน fy = SD50 จะช่วยได้ ~15%
```
Style: bg amber-50 border-amber-300 rounded-xl p-4 · "ลองเลย" button is prominent

#### 7.5.7 Action buttons (bottom)
```
[ 📥 ดาวน์โหลด Excel ]   primary · amber
[ 🔁 รีเซ็ต ]              ghost
```

Excel button: when clicked, shows brief toast "📥 กำลังสร้าง Excel..." then "✅ ดาวน์โหลดเรียบร้อย" (no actual download in mockup).

### 7.6 Footer
Centered · concrete-mid bg · text small · text-slate-500:
> Phase 1 MVP · v0.1.0 · ตำราอ้างอิง: มงคล DRMK + ว.ส.ท. 1008-38 · ACI 318-19 cross-check
> Made with ❤️ in Thailand · เปิด source · Civil Calc 2026

---

## 8 · Component spec details

### 8.1 Slider with sync (used for b, h, L, UDL value, point-load magnitude/position)
```html
<div class="flex items-center gap-3">
  <label class="text-sm font-medium text-slate-700 min-w-[100px]">
    ความกว้าง b
    <span class="text-slate-400 text-xs">ⓘ</span>
  </label>
  <input type="range" min="15" max="60" step="5" value="25" class="flex-1">
  <input type="number" min="15" max="60" step="5" value="25" class="w-16 text-right ..."> 
  <span class="text-slate-500 text-sm w-6">cm</span>
</div>
```

Tooltip (on hover ⓘ): "ความกว้างของคาน (cm) — measured ด้านที่สั้น"

### 8.2 Toggle pill group
```html
<div class="inline-flex rounded-full bg-slate-100 p-1">
  <button class="px-4 py-2 rounded-full bg-deep-steel-blue text-white shadow-sm text-sm">SD40</button>
  <button class="px-4 py-2 rounded-full text-slate-600 text-sm hover:bg-white">SD50</button>
  ...
</div>
```

### 8.3 Point load row (full component)
```html
<div class="bg-slate-50 rounded-lg p-3 space-y-2 border border-slate-200">
  <div class="flex justify-between items-center">
    <span class="text-sm font-semibold">Load #1</span>
    <button class="text-fail-red hover:bg-red-50 rounded p-1">✕</button>
  </div>
  <div class="grid grid-cols-2 gap-2">
    <div>
      <label class="text-xs text-slate-600">ขนาด (kN)</label>
      <input type="number" value="10" class="...">
    </div>
    <div>
      <label class="text-xs text-slate-600">ตำแหน่ง x (m)</label>
      <input type="number" value="2.25" step="0.05" class="...">
    </div>
  </div>
  <input type="range" min="0" max="4.5" step="0.05" value="2.25" class="w-full">
  <div class="flex gap-2 items-center">
    <span class="text-xs text-slate-600">ประเภท:</span>
    <div class="toggle-pill-group">
      <button>DL</button>
      <button class="active">LL</button>
    </div>
  </div>
</div>
```

### 8.4 Tooltip (universal)
Show on hover for 200ms+ on any ⓘ icon · floating · arrow pointing to source · bg slate-900 · text-white · max-w-xs · text-sm · rounded-md · px-3 py-2 · shadow-lg.

### 8.5 Toast notifications
Position: top-right · stack vertically · auto-dismiss 4s · slide in from right (translate-x animation 0.3s ease-out).

Variants:
- info: bg slate-800 · text white
- warn: bg amber-100 border-amber-400 · text amber-900
- success: bg green-100 border-green-400 · text green-900
- error: bg red-100 border-red-400 · text red-900

---

## 9 · UI States (all variants to mockup)

### 9.1 BOOT state
- Disclaimer banner shown
- Form is visible but disabled (opacity 60%)
- Submit button shows spinner + "กำลังเตรียมเครื่องคำนวณ (Python in browser · ~3-5 วินาที)..."
- Diagram panel: skeleton — placeholder gray shapes where SVGs will be
- Result panel: empty state with concrete-block icon (large · centered) + text "กดปุ่ม 'คำนวณ' เพื่อเริ่ม"

### 9.2 READY state (form filled, no calc yet)
- Form enabled · Submit button enabled · accent color
- Diagram panel: shows beam schematic (top SVG) based on current input values · BUT V and M diagrams show empty state with text "กดคำนวณเพื่อดูแผนภาพ V/M"
- Result panel: empty state

### 9.3 CALCULATING state (after click submit)
- Submit button: spinner inline + "กำลังคิดให้ครับ..." · button disabled
- Form: dimmed slightly (opacity 80%) — input changes accepted but won't trigger another submit until current done
- Result panel: skeleton shimmer (gray animated bars where values will appear) — feels alive
- Diagram panel: still shows previous result (don't clear) — smoother transition

### 9.4 RESULT · PASS state
- All filled values shown
- Verdict: ✅ ผ่าน · green gradient · safety bar fills to e.g. +12.3%
- Sample numbers (use these exact values for Pass mockup):
  - Wu = 11.33 kN/m · R₁=R₂ = 25.5 kN · Max V = 25.5 kN at x=0 · Max M = 28.67 kN·m at x=2.25
  - β1 = 0.85 · ρb = 0.02622 · ρmin = 0.00350 · ρmax = 0.01966 · ρ_design = 0.00855
  - As_req = 11.2 cm² · Rebar = 3-DB25 (As_provided = 14.73 cm²) · margin +21%
  - φMn = 32.19 kN·m · safety margin = +12.3%
- Excel button visible and enabled
- M/V diagrams populated with mock data (see Section 13)

### 9.5 RESULT · FAIL state
- Verdict: ❌ ไม่ผ่าน · red gradient · safety bar shows negative or just-positive but in red zone
- Sample numbers:
  - Wu = 32.5 kN/m · Mu = 82.3 kN·m · b=20 h=40 (too small)
  - ρ_design > ρ_max → over-reinforced OR section too small
  - φMn = 72.1 kN·m → margin = -12.4%
- Auto-suggest visible:
  - "ลองเพิ่ม h เป็น 50 cm (เพิ่ม 10) · margin จะเป็น +8%"
  - OR "ลองเพิ่ม b เป็น 25 cm + h เป็น 45 cm · margin จะเป็น +12%"
  - "[ลองเลย →]" button

### 9.6 ERROR state (e.g., invalid input)
- Toast at top-right: "อันนี้ดูแปลกๆ · ตรวจ fy อีกที? (ค่า {fy} ไม่ตรง Thai grade)"
- Field highlighted with red underline + tiny error text below
- Result panel: shows last successful result if any, OR empty state

### 9.7 Mobile views
Same states · single column · diagrams BELOW form · result panel BELOW diagrams.

---

## 10 · Interaction patterns (priority)

### 10.1 🔥 CRITICAL · Drag handle ↔ text input sync
- Each point load has a circular handle on beam schematic
- Dragging the handle: position x updates in real-time in the corresponding text input (no animation · instant)
- Typing x in the text input: handle on schematic snaps to new position with 0.2s ease-out transition
- M/V diagrams re-render with same 0.25s ease-out during drag (NOT throttled — RAF + transform updates)

### 10.2 🔥 CRITICAL · Synced vertical hover line
- One mouse position → vertical line + tooltip on all 3 stacked SVGs
- Tooltip shows: x, V(x), M(x) at that position
- Tooltip is positioned smartly (right of cursor unless near right edge, then flips left)

### 10.3 Live re-render on form changes
- Slider drag on b/h/L → debounce 60ms → recompute statics + redraw diagrams + recompute result (only statics/diagrams live · NOT design_beam result · keep result panel showing last calc until user clicks "คำนวณ" again)
- Alternative: full live re-calc only after threshold (e.g., user releases slider)

### 10.4 Sample preset 1-click
- Click "🏠 บ้าน 2 ชั้น" → form fields populate with residential values → submit button highlights momentarily (pulse 1s) inviting click

### 10.5 Excel export
- Button click → toast "กำลังสร้าง Excel..." (1s) → toast "✅ ดาวน์โหลด {filename}.xlsx เรียบร้อย" (mockup only — no real file in mockup)

### 10.6 Adding/removing point loads
- "+ เพิ่ม" button → new row appears with slide-down animation (0.3s ease-out) + handle appears on beam at default x (mid-span)
- "✕" on row → slide-up + fade-out (0.25s) → handle removed from beam

### 10.7 Auto-suggest "ลองเลย" click
- Click "ลองเลย →" in fail state → form fields update to suggested values (animated number transition · 0.5s) → submit auto-triggered → diagrams + result update

---

## 11 · Engineering visual conventions (LOCKED · do not improvise)

### 11.1 Sign convention for M diagram
- **Positive moment (sagging, like a smile 😊)** → plotted **BELOW** the x-axis
- **Negative moment (hogging, like a frown ☹️)** → plotted **ABOVE** the x-axis
- This matches Thai/ACI textbook convention. Inverting this = engineers will reject the tool.

### 11.2 Sign convention for V diagram
- Standard: positive V above x-axis, negative below
- For simply-supported with downward loads: V curve starts positive (at left support) descends to negative (at right support), crossing x-axis at max-M location

### 11.3 Color
- Beam line: graphite #1F2937
- Supports: graphite (filled triangles)
- UDL arrows: amber #F59E0B (semi-transparent · 60%)
- Point load arrows: amber #F59E0B (solid · with magnitude label)
- V curve: shear-blue #2563EB · filled area at 8% opacity
- M curve: moment-red #DC2626 · filled area at 8% opacity
- Zero-line (x-axis): slate-400 1px dashed
- Hover sync line: slate-500 1.5px dashed (more visible)
- Grid lines (if shown): slate-200 1px dotted

### 11.4 Axis labels
- X-axis: bottom of M diagram (shared) · labels at 0, L/4, L/2, 3L/4, L · "m" unit
- Y-axis V: left side · units "kN"
- Y-axis M: left side · units "kN·m"
- Critical values annotated with pill labels (no overlap)

### 11.5 Cantilever convention
- Fixed support drawn at LEFT (hatched wall)
- Free end at RIGHT
- M(x) is entirely above x-axis (negative throughout) for downward loads
- V(x) is entirely positive or negative depending on load direction

---

## 12 · Microcopy (Thai · บ้านๆ · ไม่ jargon)

### 12.1 Buttons / actions
| Context | Text |
|---|---|
| Submit calc | คำนวณ |
| Submit (loading) | กำลังคิดให้ครับ... |
| Submit (Pyodide loading) | กำลังเตรียมเครื่องคำนวณ... |
| Excel export | 📥 ดาวน์โหลด Excel |
| Reset form | 🔁 รีเซ็ต |
| Add point load | + เพิ่มจุดน้ำหนัก |
| Remove point load | ✕ |
| Auto-suggest apply | ลองเลย → |
| Dismiss disclaimer | ปิด |

### 12.2 Status messages
| Context | Text |
|---|---|
| Pass verdict | ✅ ผ่าน |
| Pass subtitle | ปลอดภัย safe margin +{n}% |
| Fail verdict | ❌ ไม่ผ่าน |
| Fail subtitle | φMn = {x} น้อยกว่า Mu = {y} · ขาดอยู่ {n}% |
| Computing | กำลังคำนวณ... |
| Excel generating | กำลังสร้าง Excel... |
| Excel ready | ✅ ดาวน์โหลดเรียบร้อย |
| Invalid input | อันนี้ดูแปลกๆ · ตรวจ {field} อีกที? |
| MPa warning | 🤔 หมายถึง {value*10} ksc หรือไม่? (ที่ใส่ดูเหมือนเป็น MPa) |
| Section too small | ขนาดคานเล็กไป — ลองเพิ่ม h หรือ b |
| Over-reinforced | เหล็กเยอะเกิน · risk brittle · ลองเพิ่ม b หรือ h หรือ f'c |

### 12.3 Tooltips per field (ⓘ hover content)
| Field | Tooltip |
|---|---|
| b | ความกว้างคาน (cm) · ด้านที่สั้นของหน้าตัด |
| h | ความสูงคาน (cm) · ด้านที่ยาวของหน้าตัด (รวม cover ทั้งสองข้าง) |
| L | ระยะระหว่าง support ของคาน (m) · จากศูนย์-ศูนย์ |
| f'c | กำลังอัดของคอนกรีต (ksc · กิโลกรัมต่อตารางเซนติเมตร) · ค่ามาตรฐานบ้านพัก = 240 |
| fy | กำลังครากของเหล็กยืน (Thai grade) · SD40 = บ้านทั่วไป · SD50 = อาคารใหญ่ |
| DL | น้ำหนักคงที่ (Dead Load) · เช่น คอนกรีต พื้น ผนัง |
| LL | น้ำหนักจร (Live Load) · เช่น คน เฟอร์นิเจอร์ |
| cover | ระยะหุ้มคอนกรีต (cm) · ป้องกันสนิม · ภายใน 3 · นอก 4-5 |
| Self-weight | คำนวณน้ำหนักคานเองอัตโนมัติ (γ=2400 kg/m³) → บวกเข้า DL |
| Support type | ปลายคานยึดยังไง · "รองรับธรรมดา" = ปลายวางบน column |
| Continuous | คานต่อเนื่อง 3+ support · ใช้สูตร ACI moment coefficient |

### 12.4 Footer / branding
| Where | Text |
|---|---|
| Tagline | ออกแบบคาน RC สวยงาม · ตรงทฤษฎี · ใช้ง่าย |
| Disclaimer | ⚠️ ผลคำนวณ preliminary · ต้องตรวจสอบโดยวิศวกร ก.ว. ก่อนใช้งานจริง |
| Footer | Phase 1 MVP · v0.1.0 · ตำราอ้างอิง: มงคล DRMK + ว.ส.ท. 1008-38 |
| Made with | Made with ❤️ in Thailand · 2026 |

---

## 13 · Sample data for mockup states

### 13.1 Default pre-fill (open app → form is filled with these)
```
Geometry:
  b = 25 cm
  h = 50 cm
  L = 4.5 m

Materials:
  f'c = 240 ksc
  fy = SD40 (4000 ksc)

Support: รองรับธรรมดา (simply-supported)

Loads:
  Self-weight: checked (auto adds 2.94 kN/m DL)
  UDL: 3.0 kN/m · type LL
  Point loads: 0 (empty state)

Advanced (closed by default):
  cover = 3.0 cm
  stirrup grade = RB9
  db_assume = DB16
  load_combo = 1.2D+1.6L (ACI modern)
```

### 13.2 Sample beam schematic for "ready" state
- Beam line 0 → 4.5m (auto-scaled to fit container)
- Triangle supports at x=0 and x=4.5
- UDL arrows distributed (e.g., 9 small arrows · evenly spaced)
- No point load handles yet (empty)
- Dimension "L = 4.5 m" below

### 13.3 Sample V diagram for PASS state (mock data)
For UDL only, simply-supported · w=5.94 kN/m total factored, L=4.5:
- V(0) = +13.37 kN (positive at left support, drawing upward from x-axis)
- V(L) = -13.37 kN (negative at right support)
- Linear descent · crosses zero at x=L/2=2.25m

Note: the values above are simplified mockup numbers · final spec uses Wu=11.33 kN/m → R = 25.5 kN. Use whichever feels visually balanced.

Use these for the Pass mockup:
- V(0) = +25.5 · V(2.25) = 0 · V(4.5) = -25.5 (linear)

### 13.4 Sample M diagram for PASS state
For UDL only · simply-supported · Wu=11.33 kN/m, L=4.5:
- M(0) = 0
- M(2.25) = Wu·L²/8 = 11.33·20.25/8 = 28.67 kN·m (peak, **plotted below x-axis**)
- M(4.5) = 0
- Smooth parabola opening upward (since plotted below x-axis · the curve dips down)

### 13.5 Sample with 1 point load (for showing draggable handle)
Add this to the demo:
- 1 point load: P=10 kN, x=2.0 m, type LL
- Resulting V diagram: piecewise linear with jumps at x=2.0
- Resulting M diagram: piecewise parabolic (still all below x-axis)
- Show handle (circle) on beam at x=2.0 with magnitude label "10 kN" above

### 13.6 Sample FAIL state
- b=20, h=40, L=6.0, fc=240, fy=4000
- UDL = 8 kN/m DL + 12 kN/m LL · self-weight on
- Wu = 1.2·(8 + 1.88) + 1.6·12 = 11.86 + 19.2 = 31.06 kN/m
- Mu = 31.06 · 36/8 = 139.77 kN·m
- d = 40 - 3 - 0.9 - 0.8 = 35.3 cm
- This would over-reinforce → fail
- Auto-suggest: "ลองเพิ่ม h เป็น 55 cm" OR "ลองเพิ่ม b เป็น 30 cm"

---

## 14 · Accessibility

### 14.1 Required
- Keyboard navigation: Tab through every interactive element in logical order
- Focus indicators: visible 2px outline (deep-steel-blue) on every focusable element
- Form labels: associated with inputs via `<label for="">`
- Touch targets: minimum 44×44px
- Color contrast: 4.5:1 minimum for text, 3:1 for UI elements
- Status colors: do NOT rely on color alone — use icon (✓/✗/⚠) plus color
- Font size: minimum 16px on inputs (iOS zoom prevention)

### 14.2 Nice to have (mockup level)
- ARIA labels in Thai on icon-only buttons
- `prefers-reduced-motion` respect (disable diagram transitions if user prefers reduced)

---

## 15 · Out of scope (Session 1 mockup · placeholders only)

These are explicitly NOT in the mockup. Just show subtle placeholders or "Coming in Session 2/3":

- Shear stirrup design output (show text "เหล็กปลอก: คำนวณใน Session 2")
- Click-to-pin on diagrams (no pin functionality)
- Cross-section view with rebar drawn
- 3D beam visualization
- Theory animations (stress block · failure modes)
- Citation pop-ups with PDF page snippets
- Sound effects
- Dark mode toggle
- Multi-language toggle
- Authentication
- Cloud save / share link
- Comparison side-by-side

---

## 16 · Acceptance criteria (mockup is "done" when)

- [x] All 6 mockup states render correctly (boot, ready, calculating, pass, fail, error)
- [x] Layout works on desktop (≥1024px), tablet (768-1023), mobile (<768)
- [x] All Thai microcopy present and visually polished
- [x] Sign convention LOCKED: positive M below x-axis
- [x] Color convention LOCKED: V=blue, M=red, Beam=graphite, Loads=amber
- [x] Stacked diagram layout with shared x-axis
- [x] Synced hover line + 3-value tooltip across all 3 SVGs works in mockup (vanilla JS)
- [x] At least 1 point load shown with drag handle visible on beam (drag itself can be non-functional in mockup)
- [x] Sample preset buttons visible (no need to wire all 3 — just first preset)
- [x] Auto-suggest "ลองเลย" visible in FAIL state
- [x] Excel button + reset button styled and present
- [x] Disclaimer banner persistent
- [x] All buttons + form components match the spec style (rounded-xl, shadow-sm, ease-out transitions)
- [x] Sarabun + Inter + JetBrains Mono fonts loaded from Google Fonts
- [x] No build chain · runs by opening file in browser

---

## 17 · Brief for Claude Design (THE ASK)

**Please generate:**

A **single self-contained `index.html` file** that mocks up the Civil Calc Web App per the spec above.

**Format requirements:**
- HTML5 doctype, lang="th"
- Tailwind CSS via CDN: `<script src="https://cdn.tailwindcss.com"></script>` in `<head>`
- Google Fonts (Sarabun, Inter, JetBrains Mono) loaded in `<head>`
- Embedded `<style>` for custom CSS (CSS variables for color palette · component overrides)
- Embedded `<script>` for state toggling demo (vanilla JS · no React)
- Inline SVG for all 3 diagrams (beam schematic, V, M) with realistic mock data per Section 13
- All Thai microcopy verbatim from Section 12
- No external image dependencies (use inline SVG icons or Tailwind/Unicode where possible — concrete-block icon can be a styled `<div>` or SVG)

**State demo pattern:**
At the top-right of the page (or as a floating bottom-right toolbar visible in mockup mode), include a "🎨 Demo states" toggle that lets you switch the page between:
- Boot
- Ready
- Calculating
- Result · Pass (default)
- Result · Fail
- Error (toast variant)
- Mobile layout (force narrow width)

This makes it easy to review every state visually. In production this toolbar gets removed; for mockup it's essential.

**Visual quality bar:**
Aim for **Linear/Figma/Apple Calculator level polish**. This is being judged on:
- Whitespace · breathing room
- Typography hierarchy
- Color discipline (use the locked palette · don't invent)
- Engineering convention correctness (especially Section 11)
- Thai language readability (Sarabun renders well · don't squish)
- Delight in micro-interactions (hover states · transitions)

**What to skip:**
- Don't implement actual calc logic (no Pyodide · no D3 · no ExcelJS)
- Don't worry about responsiveness perfection on every breakpoint — desktop + mobile + 1 intermediate is enough
- Don't add features outside the spec (no surprise features)
- Don't use a frontend framework (no React · no Vue) — must be vanilla HTML/CSS/JS

**Length expectation:**
Probably 800-1500 lines of HTML+CSS+JS combined. Quality > length.

**Output:**
Just produce the complete `index.html` file. The build assistant will receive it from the user, validate it matches this spec, then wire in Pyodide + statics + Excel export logic in subsequent build sessions.

Thank you! Let's make Nu (and Thai engineers everywhere) smile. 🇹🇭

---

## Appendix A · Reference values for math sanity-check

For the Pass mockup result:
```
Inputs: b=25, h=50, L=4.5, f'c=240, fy=4000, simply-supported
Loads: self-weight (auto 2.94 kN/m DL) + UDL 3.0 kN/m LL · no point loads
Load combo: 1.2D + 1.6L

Wu = 1.2 × 2.94 + 1.6 × 3.0
   = 3.528 + 4.8
   = 8.33 kN/m

(Update to match: use Wu ≈ 11.33 kN/m via heavier self-weight assumption · or
 increase UDL · for a more interesting Mu value · pick numbers that feel right
 visually)

Reactions (simply-supported, UDL only):
  R₁ = R₂ = Wu × L / 2

V(x) = R₁ - Wu × x   for 0 ≤ x ≤ L
M(x) = R₁ × x - Wu × x² / 2

M_max = Wu × L² / 8   at x = L/2
```

For point load contributions: superpose using shear/moment equations for point load on simply-supported beam.

---

## Appendix B · File output location

After Claude Design generates the mockup, save the file as:
```
C:\Users\Jone\Desktop\civilcalc-web\mockup.html
```

The build assistant will then read it, extract the structure + styles, and wire Pyodide + real calc into a final `index.html` file.

---

*END OF DESIGN SPEC*
