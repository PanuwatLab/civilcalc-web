"""
panuwat-civil-calc · calc.py

Pure Python stdlib helper for RC beam design (singly-reinforced flexure · SDM · Thai compliance).
Deterministic math · type-hinted · explicit exceptions · NO external dependencies.

Standards referenced:
  - Primary: ว.ส.ท. 1008-38 (E.I.T. SDM · มงคล DRMK + พงฬ์นธี ACI 318-95 era)
  - Cross-check: ACI 318M-08 (วัฒนชัย CU · modern strain-based)

Units: kg, cm, ksc (Thai construction permit standard)

Source: PanuwatBrain/02-Knowledge/Civil-Engineering/Formulas/RC Beam Flexure Design Formulas.md
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


# ----------------------------------------------------------------------------
# Constants (per reference.md)
# ----------------------------------------------------------------------------

ES_KSC: float = 2_040_000.0        # Steel modulus (ksc)
EPS_CU: float = 0.003              # Ultimate concrete strain (universal)
EPS_TENSION_LIMIT: float = 0.005   # ACI 318-08 strain-based limit (not used in default mode)

PHI_FLEXURE: float = 0.90          # Strength reduction factor for flexure (Thai compliance default)
PHI_SHEAR: float = 0.85            # Strength reduction factor for shear (ว.ส.ท. compliant)
MAX_AGGREGATE_CM: float = 2.0      # ขนาดมวลรวมหยาบโตสุด (default ~3/4"-1") · clear spacing ≥ 1.33·d_agg (ACI 25.2 · DRMK รูป1.13)
MAX_REBAR_LAYERS: int = 3          # cap จำนวนชั้นเหล็กนอน (เกินนี้ → แนะขยายหน้าตัด)
PRACTICAL_MAX_PER_LAYER: int = 6   # เส้น/ชั้น เชิงปฏิบัติ (industry norm · กันเหล็กจิ๋วหลายเส้นเบียดแถวเดียว · เกิน→ขึ้นชั้น)
REBAR_LAYER_VCLEAR_CM: float = 2.5 # ระยะห่างแนวดิ่งระหว่างชั้นเหล็ก (clear · ACI 25.2.2)

# Unit conversion · Thai engineering uses ตัน (tonf) / กก. (kgf) / ksc · NOT kN/SI
# 1 kN = 101.97 kgf = 0.10197 tonf  (matches kNm_to_kgcm = 10197 kg·cm/kN·m · g=9.80665)
KN_TO_TON: float = 0.10197         # multiply kN → ตัน (tonf) for Thai display
KNM_TO_TONM: float = 0.10197       # multiply kN·m → ตัน·ม for Thai display

RHO_MAX_FACTOR: float = 0.75       # ρmax = 0.75·ρb (ACI 318-95 / ว.ส.ท. era · Thai practice)
RHO_MIN_NUMERATOR: float = 14.0    # ρmin = 14/fy (fy in ksc)

LOAD_FACTOR_DEAD: float = 1.2      # Wu = 1.2D + 1.6L (ACI 318-19 modern combo)
LOAD_FACTOR_LIVE: float = 1.6
LOAD_FACTOR_DEAD_LEGACY: float = 1.4   # legacy combo Wu = 1.4D + 1.7L (some Thai projects use this)
LOAD_FACTOR_LIVE_LEGACY: float = 1.7

FC_THRESHOLD_HIGH_KSC: float = 350.0    # Above this · warn ("textbook scope · need manual cross-check")
FC_THRESHOLD_BETA1_DROP_KSC: float = 280.0   # Above this · β1 starts dropping below 0.85
FC_MAX_KSC: float = 700.0          # Hard upper cap (ACI 318-95 era textbook scope)
FC_MIN_KSC: float = 150.0          # Hard lower cap (lightweight concrete excluded)

FLOAT_TOL: float = 1e-6            # Floating-point comparison tolerance (per Role 2 finding)

# Session 2 · Point load constraints
POINT_LOAD_MAX_COUNT: int = 5        # max point loads per beam (Session 2 cap)
POINT_LOAD_MAX_P_KN: float = 10_000.0  # sanity clamp (10 MN ridiculous)
POINT_LOAD_MIN_P_KN: float = 0.001     # 1 N min (below = noise)

# Thai standard rebar grades (per reference.md)
THAI_STEEL_GRADES: dict[str, float] = {
    "SR24": 2400.0,
    "SD30": 3000.0,
    "SD40": 4000.0,
    "SD50": 5000.0,
}


# ----------------------------------------------------------------------------
# Exceptions
# ----------------------------------------------------------------------------


class CivilCalcError(Exception):
    """Base exception for all civil-calc errors."""
    pass


class InvalidInputError(CivilCalcError):
    """Input value outside valid range or wrong type."""
    pass


class InvalidGradeError(CivilCalcError):
    """fy doesn't match Thai standard grade (SR24/SD30/SD40/SD50)."""
    pass


class SectionTooSmallError(CivilCalcError):
    """Mu exceeds what the section can carry — sqrt(1 - 2Rn/0.85fc) goes negative.
    User must enlarge section before retry."""
    pass


class OverReinforcedError(CivilCalcError):
    """ρ_design > ρmax · over-reinforced · brittle compression failure risk.
    User must choose: enlarge section · doubly-reinforced · or increase f'c."""
    pass


class PointLoadOutOfRangeError(CivilCalcError):
    """Point load position x outside [0, L] · or kind not 'DL'/'LL' · or P<=0."""
    pass


class TooManyPointLoadsError(CivilCalcError):
    """Number of point loads exceeds Session 2 cap (POINT_LOAD_MAX_COUNT = 5)."""
    pass


class SectionTooSmallForShearError(CivilCalcError):
    """Vs required > 4·√f'c·b·d (max allowed) · section cannot carry shear even with max stirrups.
    User must enlarge b/h or increase f'c."""
    pass


# ----------------------------------------------------------------------------
# Enums
# ----------------------------------------------------------------------------


class SupportType(str, Enum):
    SIMPLY_SUPPORTED = "simply-supported"
    CANTILEVER = "cantilever"
    CONTINUOUS = "continuous"


class LoadCombo(str, Enum):
    ACI_MODERN = "1.2D+1.6L"    # ACI 318-19 default (skill default)
    ACI_LEGACY = "1.4D+1.7L"    # ACI 318-95 / ว.ส.ท. legacy


# ----------------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------------


@dataclass
class PointLoad:
    """Discrete point load on a beam (Session 2 · simply-supported only).

    Sign convention: P > 0 means downward force (gravity direction).
    Upward / uplift forces not supported in Session 2 (use kind='DL' for permanent · 'LL' for live).
    """
    kind: str       # "DL" (dead) or "LL" (live) · drives load combo factor
    P: float        # magnitude in kN (always positive · downward)
    x: float        # position from left support (m · 0 ≤ x ≤ L)


@dataclass
class PartialUDL:
    """Partial uniformly-distributed load over a sub-segment [x1, x2] of the span.

    Additional to the full-span UDL (DL/LL) · simply-supported only (this PR).
    Sign: w > 0 downward (gravity). w in kN/m · x1, x2 in m (0 ≤ x1 < x2 ≤ L).
    """
    kind: str       # "DL" or "LL" · drives load combo factor
    w: float        # intensity in kN/m (downward · per metre over [x1,x2])
    x1: float       # segment start from left support (m)
    x2: float       # segment end from left support (m)


@dataclass
class BeamInput:
    """Input for singly-reinforced RC beam design.

    Units: b, h, d, cover in cm · L in m · fc, fy in ksc · DL, LL in kN/m · P in kN · x in m
    """
    b: float                          # beam width (cm)
    h: float                          # total depth (cm)
    L: float                          # span (m)
    fc: float                         # concrete strength f'c (ksc)
    fy: float                         # steel yield strength (ksc · must be Thai grade)
    DL: float                         # dead load UDL (kN/m)
    LL: float                         # live load UDL (kN/m)
    support: SupportType = SupportType.SIMPLY_SUPPORTED
    cover: float = 3.0                # concrete cover (cm · default 3.0 for indoor)
    d_stirrup: float = 0.9            # stirrup diameter (cm · RB9 typical)
    db_assume: float = 1.6            # assumed main bar diameter for d-calc (cm · DB16 typical)
    load_combo: LoadCombo = LoadCombo.ACI_MODERN
    point_loads: list[PointLoad] = field(default_factory=list)   # Session 2 · up to 5
    stirrup_legs: int = 2             # APPENDED (keep positional order stable) · 2=1ป · 4=2ป double
    partial_udls: list = field(default_factory=list)   # list[PartialUDL] · simply-supported

    def to_dict(self) -> dict:
        d = asdict(self)
        d["support"] = self.support.value
        d["load_combo"] = self.load_combo.value
        # point_loads remain list[dict] under asdict — preserve
        return d


@dataclass
class RebarSelection:
    """A specific rebar combination."""
    main_bars: list[tuple[str, int]] = field(default_factory=list)  # [("DB16", 3), ("DB12", 1)]
    As_provided: float = 0.0                                          # cm²
    spacing_min_clear: float = 0.0                                    # cm (min clear spacing)
    fits_in_one_layer: bool = True
    n_layers: int = 1                                                 # จำนวนชั้นเหล็ก (1 ปกติ · ≥2 เมื่อกว้างไม่พอ · multi-layer)
    notes: list[str] = field(default_factory=list)


@dataclass
class BeamOutput:
    """Full design output trace."""
    # input echo
    input: BeamInput

    # computed geometry
    d_assumed: float = 0.0          # effective depth (cm) · per db_assume
    d_actual: float = 0.0           # effective depth after rebar selected (cm)

    # loads
    Wu: float = 0.0                 # factored line load (kN/m · UDL component only)
    Mu: float = 0.0                 # factored moment envelope max (kN·m)
    Mu_kg_cm: float = 0.0           # Mu converted to kg·cm for calc
    Vu: float = 0.0                 # factored shear envelope max (kN · at critical section)

    # Session 2 · point load echo + envelope details
    point_loads_factored: list = field(default_factory=list)   # [(Pu_kN, x_m, kind), ...]
    R_A: float = 0.0                # left reaction (kN · simply-supported)
    R_B: float = 0.0                # right reaction (kN · simply-supported)
    x_at_M_max: float = 0.0         # location of M_max (m)
    x_at_V_max: float = 0.0         # location of V_max (m · usually 0 or L)

    # Session 2 · shear stirrup design (None until design_shear runs)
    stirrup_design: dict = field(default_factory=dict)   # see _shear_design_full output below
    passes_shear: bool = False
    passes_flexure: bool = False

    # material/section parameters
    beta1: float = 0.0              # Whitney stress block factor
    rho_b: float = 0.0              # balanced reinforcement ratio
    rho_min: float = 0.0            # minimum reinforcement ratio
    rho_max: float = 0.0            # maximum reinforcement ratio (0.75·ρb · Thai default)
    Rn: float = 0.0                 # required nominal strength (kg/cm²)
    rho_design: float = 0.0         # design reinforcement ratio (before limit check)

    # final design
    rho_final: float = 0.0          # ρ after applying limits
    As_required: float = 0.0        # cm²
    rebar: Optional[RebarSelection] = None

    # doubly-reinforced (compression steel · เมื่อ singly เกิน ρmax · DRMK book p70)
    is_doubly: bool = False                    # True → หน้าตัดเสริมเหล็กรับแรงอัด
    As1: float = 0.0                           # tension steel จับคู่คอนกรีต (= ρmax·b·d · cm²)
    As2: float = 0.0                           # tension steel เพิ่ม จับคู่เหล็กอัด (cm²)
    As_prime_required: float = 0.0             # เหล็กรับแรงอัด (บน) ต้องการ (cm²)
    fs_prime_ksc: float = 0.0                  # หน่วยแรงในเหล็กอัด (ksc · = fy ถ้าคราก)
    comp_steel_yields: bool = False            # เหล็กอัดถึงจุดครากไหม
    rebar_compression: Optional[RebarSelection] = None   # เหล็กรับแรงอัดที่เลือก

    # verification
    a_stress_block: float = 0.0     # cm
    Mn: float = 0.0                 # nominal moment (kg·cm)
    phi_Mn: float = 0.0             # design moment capacity (kg·cm)
    safety_margin_pct: float = 0.0  # (φMn − Mu) / Mu × 100

    # serviceability · ความลึกน้อยที่สุด (DRMK ตาราง 3.1 · ไม่ผ่าน = ต้องคำนวณการแอ่น · ไม่ใช่ fail กำลัง)
    min_depth_ok: bool = True       # h ≥ h_min (L/16 ช่วงเดียว) ?
    h_min_cm: float = 0.0           # ความลึกน้อยที่สุดที่ต้องการ (ซม.)

    # status
    passes: bool = False
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)

    # detailing · ระยะหยุดเหล็กล่าง คานช่วงเดียว (Phase detailing · bottom-only)
    curtailment: Optional[dict] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["input"] = self.input.to_dict()
        if self.rebar:
            d["rebar"] = asdict(self.rebar)
        if self.rebar_compression:
            d["rebar_compression"] = asdict(self.rebar_compression)
        return d


# ----------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------


def validate_input(inp: BeamInput) -> list[str]:
    """Validate BeamInput · return list of warnings (empty if all OK · raises on hard fail).

    Raises:
        InvalidInputError: hard fail (negative dimensions · zero · out of range)
        InvalidGradeError: fy not Thai standard
    """
    warnings: list[str] = []

    # Hard rejects
    if inp.b <= 0 or inp.b > 200:
        raise InvalidInputError(f"b = {inp.b} cm · outside [0, 200] · ปรับ b ให้ realistic")
    if inp.h <= 0 or inp.h > 200:
        raise InvalidInputError(f"h = {inp.h} cm · outside [0, 200]")
    if inp.h <= inp.cover + inp.d_stirrup + inp.db_assume / 2:
        raise InvalidInputError(f"h = {inp.h} cm เล็กเกินสำหรับ cover + stirrup + rebar")
    if inp.L <= 0:
        raise InvalidInputError(f"L = {inp.L} m · must be positive")
    if inp.fc < FC_MIN_KSC or inp.fc > FC_MAX_KSC:
        raise InvalidInputError(
            f"f'c = {inp.fc} ksc · outside textbook range [{FC_MIN_KSC}, {FC_MAX_KSC}] ksc"
        )
    if inp.DL < 0 or inp.LL < 0:
        raise InvalidInputError(f"DL or LL negative · DL={inp.DL} LL={inp.LL}")

    # Thai grade enforcement
    grade_match = None
    for grade_name, grade_fy in THAI_STEEL_GRADES.items():
        if abs(inp.fy - grade_fy) < FLOAT_TOL:
            grade_match = grade_name
            break
    if grade_match is None:
        raise InvalidGradeError(
            f"fy = {inp.fy} ksc · ไม่ตรง Thai standard grade. "
            f"ใช้ได้: " + " · ".join(f"{name}({fy:.0f})" for name, fy in THAI_STEEL_GRADES.items())
        )

    # Soft warnings (non-blocking)
    if inp.fc > FC_THRESHOLD_HIGH_KSC:
        warnings.append(
            f"f'c = {inp.fc} ksc > {FC_THRESHOLD_HIGH_KSC} · เกิน textbook scope (มงคล/พงฬ์นธี) "
            "· แนะนำให้วิศวกร cross-check formula กับ ACI 318-19"
        )
    if inp.fc < 100:
        warnings.append(
            f"f'c = {inp.fc} · ค่าน้อยมาก · อาจ confuse กับ MPa? (28 MPa ≈ 280 ksc) · ขอ confirm"
        )
    if inp.fy < 1000:
        warnings.append(
            f"fy = {inp.fy} · ค่าน้อยมาก · อาจ confuse กับ MPa? (235 MPa = SR24 = 2400 ksc) · ขอ confirm"
        )
    if inp.cover < 2.0 or inp.cover > 7.5:
        warnings.append(f"cover = {inp.cover} cm · นอกช่วง normal [2.0, 7.5] · confirm exposure class")
    if inp.L > 20:
        warnings.append(f"L = {inp.L} m · ยาวมาก · อาจต้องใช้ prestressed concrete แทน")

    # Session 2 · validate point loads
    if inp.point_loads:
        # cap at POINT_LOAD_MAX_COUNT
        if len(inp.point_loads) > POINT_LOAD_MAX_COUNT:
            raise TooManyPointLoadsError(
                f"จำนวน point loads = {len(inp.point_loads)} > {POINT_LOAD_MAX_COUNT} · Session 2 จำกัด {POINT_LOAD_MAX_COUNT} จุด"
            )
        # support type check — Session 2 only supports simply-supported with points
        if inp.support != SupportType.SIMPLY_SUPPORTED:
            raise InvalidInputError(
                f"Point loads รองรับเฉพาะ simply-supported ใน Session 2 (ได้รับ support = {inp.support.value})"
            )
        # per-point validation
        for i, pt in enumerate(inp.point_loads):
            # accept dict from JSON deserialization too
            kind = pt.kind if isinstance(pt, PointLoad) else pt.get("kind", "")
            P = float(pt.P if isinstance(pt, PointLoad) else pt.get("P", 0))
            x = float(pt.x if isinstance(pt, PointLoad) else pt.get("x", -1))
            if kind not in ("DL", "LL"):
                raise PointLoadOutOfRangeError(
                    f"Point load #{i+1} · kind = {kind!r} · ต้องเป็น 'DL' หรือ 'LL'"
                )
            if not math.isfinite(P) or P < POINT_LOAD_MIN_P_KN:
                raise PointLoadOutOfRangeError(
                    f"Point load #{i+1} · P = {P} kN · ต้อง > {POINT_LOAD_MIN_P_KN} kN (downward only · Session 2)"
                )
            if P > POINT_LOAD_MAX_P_KN:
                raise PointLoadOutOfRangeError(
                    f"Point load #{i+1} · P = {P} kN · เกิน sanity limit {POINT_LOAD_MAX_P_KN} kN"
                )
            if not math.isfinite(x) or x < -FLOAT_TOL or x > inp.L + FLOAT_TOL:
                raise PointLoadOutOfRangeError(
                    f"Point load #{i+1} · x = {x} m · นอกช่วง [0, L={inp.L}]"
                )

    return warnings


# ----------------------------------------------------------------------------
# Core calc functions
# ----------------------------------------------------------------------------


def compute_effective_depth(h: float, cover: float, d_stirrup: float, db: float) -> float:
    """d = h − cover − d_stirrup − db/2 (single layer · c.g. ของเหล็กชั้นเดียว)"""
    return h - cover - d_stirrup - db / 2.0


# kind → อัตราส่วนความลึกน้อยที่สุด (DRMK ตารางที่ 3.1 · p55 · ACI Table 9.5(a) / ว.ส.ท.)
_MIN_DEPTH_RATIO = {"simple": 16.0, "one_end": 18.5, "both_ends": 21.0, "cantilever": 8.0}


def min_beam_depth(L_m: float, kind: str, fy: float) -> float:
    """ความลึกน้อยที่สุดของคาน h (ซม.) เพื่อ "ไม่ต้องคำนวณการแอ่น" (serviceability).

    DRMK ตารางที่ 3.1 (p55 · อ้าง ACI Table 9.5(a) + ว.ส.ท.) · คอนกรีตธรรมดา:
      simple (ช่วงเดียว) L/16 · one_end (ต่อเนื่องปลายเดียว) L/18.5 ·
      both_ends (ต่อเนื่องสองด้าน) L/21 · cantilever (ยื่น) L/8.
    Footnote: fy ≠ 4,000 ก.ก./ซม.² → คูณด้วย (0.4 + fy/7,000).
    หมายเหตุ: ไม่ผ่าน ≠ fail กำลัง — เป็นเกณฑ์ "ข้ามการคำนวณแอ่นได้" · ถ้าบางกว่านี้
    ต้องคำนวณระยะแอ่นจริงตามตารางที่ 10.3 (advisory · ตัวเลือก ก)."""
    md = (0.4 + fy / 7000.0) if abs(fy - 4000.0) > FLOAT_TOL else 1.0
    ratio = _MIN_DEPTH_RATIO.get(kind, 16.0)
    return L_m * 100.0 / ratio * md


def min_clear_spacing(db_cm: float) -> float:
    """ระยะช่องว่างน้อยสุดระหว่างเหล็กนอน = max(db, 2.5 ซม., 1.33·มวลรวมโตสุด)
    (ACI 25.2 · DRMK รูป 1.13 · [[Formula - Rebar Clear Spacing & Multi-Layer Arrangement]])"""
    return max(db_cm, 2.5, 1.33 * MAX_AGGREGATE_CM)


def max_bars_per_layer(available_cm: float, db_cm: float) -> int:
    """จำนวนเหล็กสูงสุดต่อ 1 ชั้น เมื่อช่องในระหว่างปลอก = available_cm.
    n·db + (n−1)·s ≤ available → n ≤ (available+s)/(db+s).
    คืน **0** ถ้า available < db (เหล็กเส้นเดียวยังไม่ลอด → caller ต้องขยายหน้าตัด · Codex P1) ·
    ไม่ floor เป็น 1 มิฉะนั้นยอมรับ layout ที่เหล็กไม่ลอดจริง. (verified vs DRMK ตาราง 3.3)"""
    if available_cm < db_cm - 1e-9:        # แม้แต่ 1 เส้นยังไม่ลอด
        return 0
    s = min_clear_spacing(db_cm)
    return max(1, int((available_cm + s) / (db_cm + s) + 1e-9))


def _layer_counts(n_bars: int, n_layers: int) -> list:
    """แจกแจงเหล็ก n เส้นลง n_layers ชั้น — ชั้นที่อยู่ห่างแกนสะเทินสุด (tension-most · index 0)
    ได้จำนวนมากก่อน (≥ ชั้นถัดไป) → c.g. ใกล้ผิวรับแรงดึง = d มากสุดเท่าที่จัดได้ (conservative-friendly)."""
    if n_layers <= 1:
        return [n_bars]
    base, rem = divmod(n_bars, n_layers)
    return [base + 1] * rem + [base] * (n_layers - rem)


def effective_depth_multilayer(h: float, cover: float, d_stirrup: float, db: float,
                               n_bars: int, n_layers: int,
                               s_vert: float = None) -> float:
    """d = h − c.g. ของกลุ่มเหล็กหลายชั้น (วัดจากผิวรับแรงดึง).
    ชั้น i ศูนย์กลางห่างผิวรับแรงดึง = cover + d_stirrup + db/2 + i·(db + s_vert).
    n_layers==1 → เท่ากับ compute_effective_depth เดิม. รับประกัน d(multi) ≤ d(single)."""
    if n_layers <= 1 or n_bars <= 0:
        return compute_effective_depth(h, cover, d_stirrup, db)
    if s_vert is None:
        s_vert = REBAR_LAYER_VCLEAR_CM
    counts = _layer_counts(n_bars, n_layers)
    y0 = cover + d_stirrup + db / 2.0                 # ศูนย์กลางชั้นแรก (ห่างผิวรับแรงดึง)
    pitch = db + s_vert                               # ระยะศูนย์กลาง-ศูนย์กลางระหว่างชั้น
    cg = sum(c * (y0 + i * pitch) for i, c in enumerate(counts)) / float(n_bars)
    return h - cg


def _rebar_d(h: float, cover: float, d_stirrup: float, rebar, db_cm: float) -> float:
    """d ของกลุ่มเหล็ก (multilayer-aware) จาก RebarSelection · single layer → เท่าสูตรเดิม."""
    if not rebar or not rebar.main_bars:
        return compute_effective_depth(h, cover, d_stirrup, db_cm)
    n_bars = sum(c for _, c in rebar.main_bars)
    return effective_depth_multilayer(h, cover, d_stirrup, db_cm, n_bars,
                                      getattr(rebar, "n_layers", 1))


def compute_beta1(fc: float) -> float:
    """Whitney stress block factor β1 per มงคล Figure 3.10 (piecewise · ksc units).

    β1 = 0.85                                if f'c ≤ 280 ksc
    β1 = 0.85 − 0.05·((f'c − 280) / 70)      if 280 < f'c ≤ 560 ksc
    β1 = 0.65                                if f'c > 560 ksc (lower bound)

    Note: 280 ksc ≈ 28 MPa · matches ACI 318 formula (28 MPa breakpoint · 7 MPa increment).
    Verified vs PDF (2026-05-28 Hr 7 citation spot-check · Section 'Whitney stress block').
    """
    if fc <= FC_THRESHOLD_BETA1_DROP_KSC:
        return 0.85
    beta1 = 0.85 - 0.05 * ((fc - FC_THRESHOLD_BETA1_DROP_KSC) / 70.0)
    return max(0.65, beta1)


def compute_rho_b(fc: float, fy: float, beta1: float) -> float:
    """Balanced reinforcement ratio · per มงคล Eq 3.12 (Thai units · Es = 2,040,000 ksc).

    ρb = (0.85 · β1 · f'c / fy) · (6120 / (6120 + fy))

    where 6120 = εcu · Es = 0.003 · 2,040,000 = 6120 ksc.
    """
    eps_cu_es = EPS_CU * ES_KSC   # = 6120 ksc
    return (0.85 * beta1 * fc / fy) * (eps_cu_es / (eps_cu_es + fy))


def compute_rho_max(rho_b: float) -> float:
    """ρmax = 0.75·ρb per มงคล Eq 3.13 (Thai compliance · ACI 318-95 / ว.ส.ท.).

    Note: ACI 318-08 strict mode uses ~0.63·ρb (strain-based · εt ≥ 0.005).
    Not used in default mode · documented in reference.md.
    """
    return RHO_MAX_FACTOR * rho_b


def compute_rho_min(fy: float) -> float:
    """ρmin = 14/fy per มงคล Eq 3.16 (fy in ksc · Thai grade)."""
    return RHO_MIN_NUMERATOR / fy


def compute_Wu(DL: float, LL: float, combo: LoadCombo = LoadCombo.ACI_MODERN) -> float:
    """Factored line load · kN/m."""
    if combo == LoadCombo.ACI_MODERN:
        return LOAD_FACTOR_DEAD * DL + LOAD_FACTOR_LIVE * LL
    elif combo == LoadCombo.ACI_LEGACY:
        return LOAD_FACTOR_DEAD_LEGACY * DL + LOAD_FACTOR_LIVE_LEGACY * LL
    raise InvalidInputError(f"Unknown load combo: {combo}")


def _factor_point_loads(
    point_loads: list, combo: LoadCombo
) -> list[tuple[float, float, str]]:
    """Apply load combo factor to point loads · return [(Pu_kN, x_m, kind), ...].

    DL → 1.2 (modern) or 1.4 (legacy) · LL → 1.6 (modern) or 1.7 (legacy)
    Accepts PointLoad dataclass or dict (for JSON deserialize).
    """
    if not point_loads:
        return []
    if combo == LoadCombo.ACI_MODERN:
        f_DL, f_LL = LOAD_FACTOR_DEAD, LOAD_FACTOR_LIVE
    elif combo == LoadCombo.ACI_LEGACY:
        f_DL, f_LL = LOAD_FACTOR_DEAD_LEGACY, LOAD_FACTOR_LIVE_LEGACY
    else:
        raise InvalidInputError(f"Unknown load combo: {combo}")
    result: list[tuple[float, float, str]] = []
    for pt in point_loads:
        kind = pt.kind if isinstance(pt, PointLoad) else pt["kind"]
        P = float(pt.P if isinstance(pt, PointLoad) else pt["P"])
        x = float(pt.x if isinstance(pt, PointLoad) else pt["x"])
        factor = f_DL if kind == "DL" else f_LL
        result.append((factor * P, x, kind))
    return result


def _factor_partial_udls(
    partial_udls: list, combo: LoadCombo
) -> list[tuple[float, float, float, str]]:
    """Apply load combo factor to partial UDLs · return [(w_kN_m, x1, x2, kind), ...].

    Accepts PartialUDL dataclass or dict {kind,w,x1,x2}. Validates x1 < x2.
    """
    if not partial_udls:
        return []
    if combo == LoadCombo.ACI_MODERN:
        f_DL, f_LL = LOAD_FACTOR_DEAD, LOAD_FACTOR_LIVE
    elif combo == LoadCombo.ACI_LEGACY:
        f_DL, f_LL = LOAD_FACTOR_DEAD_LEGACY, LOAD_FACTOR_LIVE_LEGACY
    else:
        raise InvalidInputError(f"Unknown load combo: {combo}")
    result: list[tuple[float, float, float, str]] = []
    for s in partial_udls:
        kind = s.kind if isinstance(s, PartialUDL) else s["kind"]
        w = float(s.w if isinstance(s, PartialUDL) else s["w"])
        x1 = float(s.x1 if isinstance(s, PartialUDL) else s["x1"])
        x2 = float(s.x2 if isinstance(s, PartialUDL) else s["x2"])
        if kind not in ("DL", "LL"):
            raise InvalidInputError(f"Partial UDL: kind ต้องเป็น 'DL' หรือ 'LL' (ได้ '{kind}')")
        if not math.isfinite(w) or w <= 0:
            raise InvalidInputError(f"Partial UDL: w ต้องเป็นบวกและจำกัด (ได้ {w})")
        if not math.isfinite(x1) or not math.isfinite(x2):
            raise InvalidInputError(f"Partial UDL: x1/x2 ต้องเป็นตัวเลขจำกัด (ได้ x1={x1}, x2={x2})")
        if x2 <= x1 + FLOAT_TOL:
            raise InvalidInputError(f"Partial UDL: x2 ({x2}) ต้อง > x1 ({x1})")
        factor = f_DL if kind == "DL" else f_LL
        result.append((factor * w, x1, x2, kind))
    return result


# --- Partial-UDL statics helpers (segment = (w_kN_m, x1, x2, kind)) ---

def _partial_reactions(partials: list, L: float) -> tuple[float, float]:
    """Reaction contributions (R_A_add, R_B_add) from partial UDLs · kN.

    Each segment ≡ resultant W = w·(x2−x1) acting at centroid xc = (x1+x2)/2.
    R_B = Σ W·xc/L · R_A = Σ W·(L−xc)/L (moment balance · same as a point load at xc).
    """
    R_A = R_B = 0.0
    for w, x1, x2, _ in partials or []:
        W = w * (x2 - x1)
        xc = (x1 + x2) / 2.0
        R_B += W * xc / L
        R_A += W * (L - xc) / L
    return R_A, R_B


def _partial_shear_left(x: float, partials: list) -> float:
    """Total partial-UDL load to the LEFT of section x · kN (to subtract from V)."""
    total = 0.0
    for w, x1, x2, _ in partials or []:
        xr = min(x, x2)
        if xr > x1:
            total += w * (xr - x1)
    return total


def _partial_moment_left(x: float, partials: list) -> float:
    """Moment about section x of partial-UDL load to its left · kN·m (to subtract from M)."""
    total = 0.0
    for w, x1, x2, _ in partials or []:
        xr = min(x, x2)
        if xr > x1:
            W_seg = w * (xr - x1)
            c = (x1 + xr) / 2.0
            total += W_seg * (x - c)
    return total


def compute_reactions_ss(
    Wu: float, L: float, factored_points: list[tuple[float, float, str]],
    partials: list | None = None,
) -> tuple[float, float]:
    """Reactions R_A (left) and R_B (right) for simply-supported beam · kN.

    R_A = Wu·L/2 + Σ Pu_i·(L − x_i)/L  + partial-UDL contribution
    R_B = Wu·L/2 + Σ Pu_i·x_i/L        + partial-UDL contribution
    Verifies R_A + R_B = Wu·L + Σ Pu + Σ W_partial within FLOAT_TOL.
    """
    R_A = Wu * L / 2.0
    R_B = Wu * L / 2.0
    for Pu, x, _ in factored_points:
        R_A += Pu * (L - x) / L
        R_B += Pu * x / L
    pa, pb = _partial_reactions(partials, L)
    return R_A + pa, R_B + pb


def compute_shear_at(
    x: float,
    R_A: float,
    Wu: float,
    factored_points: list[tuple[float, float, str]],
    partials: list | None = None,
) -> float:
    """Shear at section x · kN (downward positive load convention).

    V(x) = R_A − Wu·x − Σ Pu_i (x_i < x) − Σ partial-UDL load left of x
    Section is taken on the LEFT side · sign per Thai convention (positive shear sags beam).
    """
    V = R_A - Wu * x
    for Pu, x_i, _ in factored_points:
        if x_i < x - FLOAT_TOL:
            V -= Pu
    V -= _partial_shear_left(x, partials)
    return V


def compute_moment_at(
    x: float,
    R_A: float,
    Wu: float,
    factored_points: list[tuple[float, float, str]],
    partials: list | None = None,
) -> float:
    """Bending moment at section x · kN·m (positive = sagging · tension at bottom).

    M(x) = R_A·x − Wu·x²/2 − Σ Pu_i·(x − x_i) (x_i < x) − Σ partial-UDL moment left of x
    """
    M = R_A * x - Wu * x * x / 2.0
    for Pu, x_i, _ in factored_points:
        if x_i < x - FLOAT_TOL:
            M -= Pu * (x - x_i)
    M -= _partial_moment_left(x, partials)
    return M


def compute_envelope_ss(
    Wu: float,
    L: float,
    factored_points: list[tuple[float, float, str]],
    n_samples: int = 201,
    eps: float = 1e-5,
    partials: list | None = None,
) -> dict:
    """Compute V/M envelope for simply-supported beam with UDL + point loads.

    Returns dict:
      R_A, R_B: kN
      x_grid:   list[float]   (m, sorted, includes 0, L, x_i±ε, and uniform samples)
      V_grid:   list[float]   (kN at each x)
      M_grid:   list[float]   (kN·m at each x)
      V_max:    float         (absolute max · kN)
      x_at_V_max: float       (m)
      M_max:    float         (positive max · sagging · kN·m)
      x_at_M_max: float       (m · usually mid-span or at a point load · NOT necessarily L/2)
    """
    R_A, R_B = compute_reactions_ss(Wu, L, factored_points, partials)

    # Build x grid: uniform + boundary + point ± ε (to capture V jumps cleanly)
    x_set: set[float] = set()
    if n_samples < 3:
        n_samples = 3
    for i in range(n_samples):
        x_set.add(i * L / (n_samples - 1))
    x_set.add(0.0)
    x_set.add(L)
    for _, x_i, _ in factored_points:
        # clamp to [0, L] to avoid floating slop
        x_safe = max(0.0, min(L, x_i))
        x_set.add(max(0.0, x_safe - eps))
        x_set.add(min(L, x_safe + eps))
        x_set.add(x_safe)
    # partial-UDL endpoints: V has slope-breaks (not jumps) but M_max can sit at x2
    for _, x1, x2, _ in (partials or []):
        for xb in (x1, x2):
            xs = max(0.0, min(L, xb))
            x_set.add(xs)
            x_set.add(max(0.0, xs - eps))
            x_set.add(min(L, xs + eps))
    x_grid = sorted(x_set)

    V_grid = [compute_shear_at(x, R_A, Wu, factored_points, partials) for x in x_grid]
    M_grid = [compute_moment_at(x, R_A, Wu, factored_points, partials) for x in x_grid]

    # V_max = max |V(x)|
    V_max = 0.0
    x_at_V_max = 0.0
    for x, V in zip(x_grid, V_grid):
        if abs(V) > abs(V_max):
            V_max = V
            x_at_V_max = x

    # Zero-shear crossings = local M extrema. V is piecewise-linear between grid
    # points (breakpoints at supports/points/partial-endpoints already in grid),
    # so linear interpolation of the V=0 root is EXACT within each segment.
    # Without this, M_max can fall between samples (partial-UDL peak · Codex P2).
    zero_x: list[float] = []
    for i in range(len(x_grid) - 1):
        v0, v1 = V_grid[i], V_grid[i + 1]
        if (v0 > 0.0 and v1 < 0.0) or (v0 < 0.0 and v1 > 0.0):
            dx = x_grid[i + 1] - x_grid[i]
            if dx > 0:
                zero_x.append(x_grid[i] + dx * v0 / (v0 - v1))

    # M_max = max sagging (positive) value · include zero-shear roots
    M_max = 0.0
    x_at_M_max = L / 2.0  # fallback
    for x, M in zip(x_grid, M_grid):
        if M > M_max:
            M_max = M
            x_at_M_max = x
    for x0 in zero_x:
        M0 = compute_moment_at(x0, R_A, Wu, factored_points, partials)
        if M0 > M_max:
            M_max = M0
            x_at_M_max = x0

    return {
        "R_A": R_A,
        "R_B": R_B,
        "x_grid": x_grid,
        "V_grid": V_grid,
        "M_grid": M_grid,
        "V_max": abs(V_max),
        "x_at_V_max": x_at_V_max,
        "M_max": M_max,
        "x_at_M_max": x_at_M_max,
    }


# ----------------------------------------------------------------------------
# Session 2 · Shear stirrup design (ว.ส.ท. 1008-38 · ACI 318-95 era)
# Reference: มงคล Chapter 4 (Shear in Beams) · ว.ส.ท. มาตรา 4.5
#
# Unit reminder (mixed by historical Thai convention):
#   f'c, fy : ksc  (kg/cm²)
#   b, d, s : cm
#   Vc, Vs  : kg   (force; internally) → converted to kN for display
#
# Conversion: 1 kg ≈ 0.0098 kN · use kg_to_kN(x) = x / 101.97
# ----------------------------------------------------------------------------


def _kg_to_kN(F_kg: float) -> float:
    """Convert force from kg → kN (1 kN = 101.97 kg · matches kNm_to_kgcm constant)."""
    return F_kg / 101.97


def _kN_to_kg(F_kN: float) -> float:
    """Convert force from kN → kg."""
    return F_kN * 101.97


# ----- Stirrup table (matches rebar_table.json `stirrup_sizes`) -----
# A_v = 2 legs · (cross-section per bar) — Session 2 assumes 2-leg vertical stirrups (Thai standard)
_STIRRUP_2LEG_AV_CM2: dict[str, float] = {
    "RB6":  2 * 0.283,    # 0.566 cm² (light beams only)
    "RB9":  2 * 0.636,    # 1.272 cm² (DEFAULT for typical Thai residential)
    "DB10": 2 * 0.785,    # 1.570 cm² (fallback when RB9 spacing too tight)
}
_STIRRUP_DIA_CM: dict[str, float] = {"RB6": 0.6, "RB9": 0.9, "DB10": 1.0}


def _av_legs(bar: str, n_legs: int = 2) -> float:
    """Total stirrup shear area A_v for `n_legs` legs of `bar`.

    Base table `_STIRRUP_2LEG_AV_CM2` is the 2-leg (single closed stirrup · 1ป) area.
    n_legs=2 → single stirrup (1ป) · n_legs=4 → double stirrup (2ป · 4 legs) → 2× area.
    """
    return _STIRRUP_2LEG_AV_CM2[bar] * (n_legs / 2.0)


# Practical Thai shop-drawing spacing values · floor-to-2.5cm grid + "killer pairs"
_PRACTICAL_SPACINGS_CM = [5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0, 22.5, 25.0, 27.5, 30.0]
# Killer pairs (S1, S2) ordered by tightness — used to nudge solver toward common combos
_KILLER_PAIRS = [(7.5, 15.0), (10.0, 20.0), (12.5, 25.0), (15.0, 30.0)]

# Stirrup fy for SR24 (typical Thai stirrup grade · 2400 ksc)
_FYT_STIRRUP_DEFAULT_KSC: float = 2400.0


def _floor_to_practical_spacing(s_cm: float) -> float:
    """Floor s to nearest practical 2.5cm multiple · clamp to [5, 30] cm."""
    if not math.isfinite(s_cm) or s_cm <= 0:
        return 5.0
    if s_cm <= _PRACTICAL_SPACINGS_CM[0]:
        return _PRACTICAL_SPACINGS_CM[0]
    if s_cm >= _PRACTICAL_SPACINGS_CM[-1]:
        return _PRACTICAL_SPACINGS_CM[-1]
    # find largest practical value ≤ s_cm
    for p in reversed(_PRACTICAL_SPACINGS_CM):
        if p <= s_cm + FLOAT_TOL:
            return p
    return _PRACTICAL_SPACINGS_CM[0]


def _nudge_to_killer_pair(s1: float, s2: float) -> tuple[float, float]:
    """If (s1, s2) close to a known killer pair, snap to it (constructability per Gemini Q2b).

    Snapping rule: if both s1 and s2 are within ±1 spacing-grid step of a killer pair
    AND snapping does not violate s_max (i.e. snap value ≤ original value), use it.
    """
    for k1, k2 in _KILLER_PAIRS:
        if abs(s1 - k1) <= 2.5 + FLOAT_TOL and abs(s2 - k2) <= 2.5 + FLOAT_TOL:
            # only snap if it does NOT make spacing larger than originally allowed
            if k1 <= s1 + FLOAT_TOL and k2 <= s2 + FLOAT_TOL:
                return k1, k2
    return s1, s2


def compute_Vc_ksc(fc_ksc: float, b_cm: float, d_cm: float) -> float:
    """Vc · concrete shear capacity (Thai simplified · ว.ส.ท. 1008-38).

    Vc = 0.53 · √f'c · b · d         (units: ksc · cm · cm → kg)

    Per มงคล Chapter 4 Eq 4.3 (simplified) · matches ACI 318-95 / ว.ส.ท. era.
    NOT the ACI 318-19 modern formula with size effect (out of MVP scope per Gemini Q1a).
    """
    if fc_ksc <= 0 or b_cm <= 0 or d_cm <= 0:
        raise InvalidInputError(f"Vc: invalid input fc={fc_ksc} b={b_cm} d={d_cm}")
    return 0.53 * math.sqrt(fc_ksc) * b_cm * d_cm  # kg


def compute_Vu_at_d(
    d_cm: float, L_m: float, Wu_kN_m: float,
    R_A_kN: float, factored_points: list[tuple[float, float, str]] | None,
    partials: list | None = None,
) -> tuple[float, float]:
    """Critical shear for design = max(|Vu(x=d)|, |Vu(x=L-d)|) · kN.

    Per ACI 22.5.5.1 and ว.ส.ท. · use shear at distance d from support face,
    NOT at support face itself (arch action carries some shear · Gemini Q4b).

    Returns (Vu_design_kN, x_critical_m) where x_critical is the location used.
    """
    d_m = d_cm / 100.0
    # clamp d to within [0, L/2]
    d_m = max(0.0, min(L_m / 2.0, d_m))
    pts = factored_points or []

    def V_left(x):
        # Section taken just LEFT of x (so x_i ≤ x counts)
        V = R_A_kN - Wu_kN_m * x
        for Pu, x_i, _ in pts:
            if x_i < x - FLOAT_TOL:
                V -= Pu
        V -= _partial_shear_left(x, partials)
        return V

    V_at_d_left = V_left(d_m)
    V_at_d_right = V_left(L_m - d_m)
    # take absolute max
    if abs(V_at_d_left) >= abs(V_at_d_right):
        return abs(V_at_d_left), d_m
    return abs(V_at_d_right), L_m - d_m


def _av_min_required(fc_ksc: float, b_cm: float, fyt_ksc: float, s_cm: float) -> float:
    """A_v,min per ว.ส.ท. / ACI 318-19 Eq 9.6.3.4 (whichever larger):
       A_v,min = max(0.2·√f'c · b·s / fyt, 3.5 · b·s / fyt)       [cm²]
    """
    a1 = 0.2 * math.sqrt(fc_ksc) * b_cm * s_cm / fyt_ksc
    a2 = 3.5 * b_cm * s_cm / fyt_ksc
    return max(a1, a2)


def _s_max_av_min(fc_ksc: float, b_cm: float, fyt_ksc: float, A_v_cm2: float) -> float:
    """Solve A_v ≥ A_v,min(s) for s_max (so chosen A_v meets min reinforcement requirement)."""
    # A_v ≥ max(0.2√fc·b·s/fyt, 3.5·b·s/fyt)
    s_lim1 = A_v_cm2 * fyt_ksc / (0.2 * math.sqrt(fc_ksc) * b_cm)
    s_lim2 = A_v_cm2 * fyt_ksc / (3.5 * b_cm)
    return min(s_lim1, s_lim2)


def _fmt_spacing_m(s_cm: float) -> str:
    """Format spacing (cm) as a Thai shop-drawing meter string.

    10 → '0.10' · 22.5 → '0.225' · 30 → '0.30' · 7.5 → '0.075'
    (≥2 decimal places for readability · matches JS formatter).
    """
    s_m = s_cm / 100.0
    txt = f"{s_m:.3f}".rstrip("0").rstrip(".")
    if "." not in txt:
        txt += ".00"
    elif len(txt.split(".")[1]) == 1:
        txt += "0"
    return txt


def design_shear(
    Wu_kN_m: float,
    L_m: float,
    R_A_kN: float, R_B_kN: float,
    factored_points: list[tuple[float, float, str]] | None,
    b_cm: float, d_cm: float, fc_ksc: float,
    fyt_ksc: float = _FYT_STIRRUP_DEFAULT_KSC,
    phi: float = PHI_SHEAR,
    vu_design_override_kN: float | None = None,
    n_legs: int = 2,
    partials: list | None = None,
) -> dict:
    """End-to-end shear design · returns a structured dict.

    Pipeline (per ว.ส.ท. 1008-38 + Gemini Pro guidance):
      1. Compute Vu_design = Vu at distance d from critical support (Gemini Q4b critical correction)
      2. Vc = 0.53·√f'c·b·d (Thai simplified)
      3. Branch: Vu vs 0.5·φVc · φVc · φVn_max
      4. Choose stirrup (RB9 default · fallback DB10 if spacing < 5 cm)
      5. Round spacing to 2.5cm grid + nudge to killer pair
      6. Enforce symmetric S1-S2-S1 zones (Gemini Q3)
      7. Apply A_v,min + s_max caps
      8. Hard fail if Vs > 4·√f'c·b·d

    Returns dict with keys:
      bar, A_v_cm2, S1_cm, S2_cm, L_S1_cm, L_S2_cm,
      Vu_at_d_kN, Vc_kN, Vs_required_kN, phi_Vn_kN,
      branch ('NO_STIRRUP' | 'MIN_STIRRUP' | 'DESIGN_STIRRUP'),
      shop_drawing_notation (e.g. "RB9 @ 0.10 (S1) / @ 0.20 (S2)"),
      passes, notes, citations,
      _intermediate (Black Box mitigation: Vu_at_d, phi_Vc, Vs_req, s_req_before_round)
    """
    notes: list[str] = []
    citations: list[str] = []

    # 0. Stirrup legs · 2 = single closed stirrup (1ป) · 4 = double stirrup (2ป)
    if n_legs not in (2, 4):
        raise InvalidInputError(f"n_legs = {n_legs} · รองรับเฉพาะ 2 (1ป) หรือ 4 (2ป)")
    n_stirrups = n_legs // 2

    # 1. Critical shear · normally at distance d from support (Gemini Q4b).
    #    Cantilever passes vu_design_override = Vu at FACE (no d-reduction · Gemini Q3:
    #    cantilever load is "hung" off the support → no arch action → critical at face).
    if vu_design_override_kN is not None:
        Vu_at_d_kN, x_critical_m = abs(vu_design_override_kN), 0.0
    else:
        Vu_at_d_kN, x_critical_m = compute_Vu_at_d(
            d_cm, L_m, Wu_kN_m, R_A_kN, factored_points, partials
        )

    # 2. Vc (Thai simplified)
    Vc_kg = compute_Vc_ksc(fc_ksc, b_cm, d_cm)
    Vc_kN = _kg_to_kN(Vc_kg)
    phi_Vc_kN = phi * Vc_kN
    half_phi_Vc = 0.5 * phi_Vc_kN

    citations.append(
        f"Vc = 0.53·√f'c·b·d = 0.53·√{fc_ksc:.0f}·{b_cm}·{d_cm:.1f} "
        f"= {Vc_kg:,.0f} กก. = {Vc_kg/1000:.2f} ตัน · ว.ส.ท. 1008-38 · มงคล Eq 5.7"
    )
    citations.append(
        f"φVc = {phi}·{Vc_kg/1000:.2f} = {phi_Vc_kN*KN_TO_TON:.2f} ตัน · φ = {phi} (shear · ว.ส.ท.)"
    )
    _crit_txt = ("ที่หน้าเสา (คานยื่น · ไม่ลดที่ d · Gemini Q3)" if vu_design_override_kN is not None
                 else "= d จากผิวจุดรองรับ · ว.ส.ท./ACI · มงคล p.110")
    citations.append(
        f"Vu_design = {Vu_at_d_kN*KN_TO_TON:.2f} ตัน at x = {x_critical_m:.3f} m ({_crit_txt})"
    )

    # Max allowed Vs (hard cap · prevent shear-compression web crushing)
    # DRMK Eq 5.19 (PDF p.122,125): Vs ≤ 2.1·√f'c·bw·d  (ksc units · NOT psi 8√f'c)
    Vs_max_kg = 2.1 * math.sqrt(fc_ksc) * b_cm * d_cm
    Vs_max_kN = _kg_to_kN(Vs_max_kg)

    # 3. Branch
    if Vu_at_d_kN <= half_phi_Vc + FLOAT_TOL:
        # No stirrup theoretically required · recommend minimum for detailing
        branch = "NO_STIRRUP"
        bar = "RB9"
        A_v = _av_legs(bar, n_legs)
        s_final_S1 = 30.0   # constructability default
        s_final_S2 = 30.0
        L_S1_cm = 0.0
        L_S2_cm = L_m * 100.0
        Vs_req_kN = 0.0
        phi_Vn_kN = phi_Vc_kN
        notes.append(
            f"Vu = {Vu_at_d_kN*KN_TO_TON:.2f} ตัน ≤ 0.5·φVc = {half_phi_Vc*KN_TO_TON:.2f} ตัน · "
            f"ไม่จำเป็นต้องมีเหล็กปลอก (detailing minimum RB9@0.30 m แนะนำ)"
        )
        passes = True
    elif Vu_at_d_kN <= phi_Vc_kN + FLOAT_TOL:
        # Minimum stirrup required · Vs ≈ 0 · use A_v,min spacing limit
        branch = "MIN_STIRRUP"
        bar = "RB9"
        A_v = _av_legs(bar, n_legs)
        s_min_av = _s_max_av_min(fc_ksc, b_cm, fyt_ksc, A_v)
        s_max_code = min(d_cm / 2.0, 60.0)
        s_chosen = min(s_min_av, s_max_code)
        s_final_S1 = _floor_to_practical_spacing(s_chosen)
        s_final_S2 = s_final_S1
        # Semantic: same spacing throughout · expressed as symmetric S1-S2-S1 with S1=S2
        # → L_S1 (each side) = L/2 · L_S2 = 0 · keeps invariant 2·L_S1 + L_S2 = L
        L_S1_cm = L_m * 100.0 / 2.0
        L_S2_cm = 0.0
        Vs_req_kN = 0.0
        phi_Vn_kN = phi_Vc_kN  # no Vs contribution needed
        citations.append(
            f"A_v,min spacing limit = min({s_min_av:.2f}, d/2={s_max_code:.2f}) cm · ว.ส.ท. / ACI 9.6.3.4"
        )
        notes.append(
            f"0.5·φVc < Vu ≤ φVc · ต้องใช้ minimum stirrup ({bar}@{s_final_S1:.1f} cm)"
        )
        passes = True
    else:
        # Vu > φVc → design Vs
        branch = "DESIGN_STIRRUP"
        Vs_req_kN = (Vu_at_d_kN / phi) - Vc_kN
        Vs_req_kg = _kN_to_kg(Vs_req_kN)
        # Hard cap: Vs ≤ 2.1·√f'c·b·d (DRMK Eq 5.19 · ksc)
        if Vs_req_kg > Vs_max_kg + FLOAT_TOL:
            raise SectionTooSmallForShearError(
                f"Vs_required = {Vs_req_kg/1000:.2f} ตัน > limit 2.1·√f'c·b·d = {Vs_max_kg/1000:.2f} ตัน · "
                f"หน้าตัดคานไม่เพียงพอ (Shear Failure) · ต้องเพิ่ม b/h หรือ f'c"
            )
        # s_max regime: tight if Vs > 1.1·√f'c·b·d (DRMK Step 7 · PDF p.126 · ksc)
        Vs_threshold_kg = 1.1 * math.sqrt(fc_ksc) * b_cm * d_cm
        if Vs_req_kg > Vs_threshold_kg:
            s_max_code = min(d_cm / 4.0, 30.0)
            notes.append(
                f"Vs > 1.1·√f'c·b·d → s_max = min(d/4, 30) = {s_max_code:.1f} cm (tight regime)"
            )
        else:
            s_max_code = min(d_cm / 2.0, 60.0)

        # Try RB9 first (Thai default), fallback DB10 if spacing < 5 cm
        bar = "RB9"
        A_v = _av_legs(bar, n_legs)
        # s_S1 from Vs equation (close zone · governed by Vu_at_d)
        # s = A_v · fyt · d / Vs_req   (Vs in kg · units balance: cm² · ksc · cm / kg = cm)
        s_req_S1_cm = A_v * fyt_ksc * d_cm / Vs_req_kg if Vs_req_kg > 0 else s_max_code
        # Wider middle zone · Vs there is less (or zero · use code minimum)
        s_req_S2_cm = min(_s_max_av_min(fc_ksc, b_cm, fyt_ksc, A_v), s_max_code)

        # Cap to s_max
        s_S1_capped = min(s_req_S1_cm, s_max_code)
        s_S2_capped = min(s_req_S2_cm, s_max_code)
        # Floor to practical (round DOWN · conservative)
        s_S1_final = _floor_to_practical_spacing(s_S1_capped)
        s_S2_final = _floor_to_practical_spacing(s_S2_capped)
        # Fallback DB10 if spacing tighter than 5 cm
        if s_S1_final < 5.0 - FLOAT_TOL:
            bar = "DB10"
            A_v = _av_legs(bar, n_legs)
            s_req_S1_cm = A_v * fyt_ksc * d_cm / Vs_req_kg if Vs_req_kg > 0 else s_max_code
            s_req_S2_cm = min(_s_max_av_min(fc_ksc, b_cm, fyt_ksc, A_v), s_max_code)
            s_S1_capped = min(s_req_S1_cm, s_max_code)
            s_S2_capped = min(s_req_S2_cm, s_max_code)
            s_S1_final = _floor_to_practical_spacing(s_S1_capped)
            s_S2_final = _floor_to_practical_spacing(s_S2_capped)
            notes.append(f"RB9 spacing too tight (<5 cm) · upgrade to DB10")
        # Ensure S1 ≤ S2 (sanity)
        if s_S1_final > s_S2_final:
            s_S1_final = s_S2_final
        # Nudge to killer pair (Gemini Q2b constructability)
        s_S1_final, s_S2_final = _nudge_to_killer_pair(s_S1_final, s_S2_final)
        s_final_S1 = s_S1_final
        s_final_S2 = s_S2_final

        # S1 zone length: distance from support where Vu drops below 0.5·φVc (closer point)
        # then round UP to nearest 25 cm (Gemini Q3 constructability) + symmetric apply
        L_S1_left = _shear_zone_length(
            "left", Wu_kN_m, L_m, R_A_kN, R_B_kN, factored_points, half_phi_Vc, partials
        )
        L_S1_right = _shear_zone_length(
            "right", Wu_kN_m, L_m, R_A_kN, R_B_kN, factored_points, half_phi_Vc, partials
        )
        L_S1_worst_m = max(L_S1_left, L_S1_right)
        # Round UP to nearest 25 cm
        L_S1_cm = math.ceil((L_S1_worst_m * 100.0) / 25.0) * 25.0
        # Apply symmetric · constrain to L/2
        L_S1_cm = min(L_S1_cm, (L_m * 100.0) / 2.0)
        L_S2_cm = max(0.0, L_m * 100.0 - 2.0 * L_S1_cm)

        # Verify chosen spacing gives sufficient ψVn at the critical section
        Vs_provided_kg = A_v * fyt_ksc * d_cm / s_final_S1  # kg
        Vs_provided_kN = _kg_to_kN(Vs_provided_kg)
        phi_Vn_kN = phi * (Vc_kN + Vs_provided_kN)
        passes = phi_Vn_kN >= Vu_at_d_kN - FLOAT_TOL

        citations.append(
            f"Vs_required = Vu/φ - Vc = {Vu_at_d_kN*KN_TO_TON:.2f}/{phi} - {Vc_kg/1000:.2f} = {Vs_req_kN*KN_TO_TON:.2f} ตัน"
        )
        citations.append(
            f"s_S1 = A_v·fyt·d / Vs_req = {A_v:.3f}·{fyt_ksc:.0f}·{d_cm:.1f}/{Vs_req_kg:.0f} = {s_req_S1_cm:.2f} cm "
            f"→ floor practical {s_S1_capped:.2f} → {s_final_S1:.1f} cm"
        )
        citations.append(
            f"S1 zone length (worst of L/R) = {L_S1_worst_m*100.0:.1f} cm → round UP to {L_S1_cm:.1f} cm "
            f"(symmetric S1-S2-S1 per Gemini Q3 constructability)"
        )
        notes.append(
            f"Vu = {Vu_at_d_kN*KN_TO_TON:.2f} ตัน > φVc = {phi_Vc_kN*KN_TO_TON:.2f} ตัน · design stirrup required · "
            f"{bar}@{s_final_S1:.1f}/{s_final_S2:.1f} cm (S1/S2)"
        )

    # Shop drawing notation · collapse to uniform when S1 ≈ S2 (UX clarity)
    is_uniform = (branch in ("NO_STIRRUP", "MIN_STIRRUP")) or (
        branch == "DESIGN_STIRRUP" and abs(s_final_S1 - s_final_S2) < 0.1
    )
    # Leg prefix · "2ป-" for double stirrup (4 legs) · "" for single (default · zero-regression)
    leg_pfx = f"{n_stirrups}ป-" if n_stirrups > 1 else ""
    bar_lbl = f"{leg_pfx}{bar}"
    if branch == "NO_STIRRUP":
        shop = f"{bar_lbl} @ {_fmt_spacing_m(s_final_S1)} m (detailing min · ทั้งคาน)"
    elif is_uniform:
        shop = f"{bar_lbl} @ {_fmt_spacing_m(s_final_S1)} m (ทั้งคาน)"
    else:
        shop = f"{bar_lbl} @ {_fmt_spacing_m(s_final_S1)} (S1) · {bar_lbl} @ {_fmt_spacing_m(s_final_S2)} (S2)"

    return {
        "branch": branch,
        "bar": bar,
        "n_legs": n_legs,
        "n_stirrups": n_stirrups,
        "uniform": is_uniform,
        "A_v_cm2": A_v,
        "S1_cm": s_final_S1,
        "S2_cm": s_final_S2,
        "L_S1_cm": L_S1_cm,
        "L_S2_cm": L_S2_cm,
        "Vu_at_d_kN": Vu_at_d_kN,
        "x_critical_m": x_critical_m,
        "Vc_kN": Vc_kN,
        "phi_Vc_kN": phi_Vc_kN,
        "Vs_required_kN": Vs_req_kN,
        "phi_Vn_kN": phi_Vn_kN,
        # Thai display units (ตัน) — primary for UI per DRMK convention
        "Vu_at_d_ton": Vu_at_d_kN * KN_TO_TON,
        "Vc_ton": Vc_kg / 1000.0,
        "phi_Vc_ton": phi_Vc_kN * KN_TO_TON,
        "Vs_required_ton": Vs_req_kN * KN_TO_TON,
        "phi_Vn_ton": phi_Vn_kN * KN_TO_TON,
        "shop_drawing_notation": shop,
        "passes": passes,
        "notes": notes,
        "citations": citations,
        # Black Box mitigation (Gemini Top Risk #1) — show intermediate steps
        "_intermediate": {
            "Vu_at_d_kN": Vu_at_d_kN,
            "x_critical_m": x_critical_m,
            "Vc_kg": Vc_kg,
            "phi_Vc_kN": phi_Vc_kN,
            "half_phi_Vc_kN": half_phi_Vc,
            "Vs_required_kN": Vs_req_kN,
            "Vs_max_kN": Vs_max_kN,
            "fyt_ksc": fyt_ksc,
        },
    }


def _shear_zone_length(
    side: str,   # "left" or "right"
    Wu_kN_m: float, L_m: float,
    R_A_kN: float, R_B_kN: float,
    factored_points: list[tuple[float, float, str]] | None,
    threshold_kN: float,
    partials: list | None = None,
) -> float:
    """Find distance from support where |Vu(x)| drops below threshold_kN (m).

    Walk inward in 0.05 m steps; return first x where |V| ≤ threshold.
    Conservative: returns 0 if threshold met immediately, returns L/2 if never met.
    """
    pts = factored_points or []
    if side == "left":
        # V at x from left, walk x = 0 → L/2
        for i in range(int(L_m / 0.05) + 1):
            x = i * 0.05
            V = R_A_kN - Wu_kN_m * x
            for Pu, x_i, _ in pts:
                if x_i < x - FLOAT_TOL:
                    V -= Pu
            V -= _partial_shear_left(x, partials)
            if abs(V) <= threshold_kN:
                return x
        return L_m / 2.0
    else:
        # Walk x from right (x = L → L/2)
        for i in range(int(L_m / 0.05) + 1):
            x = L_m - i * 0.05
            V = R_A_kN - Wu_kN_m * x
            for Pu, x_i, _ in pts:
                if x_i < x - FLOAT_TOL:
                    V -= Pu
            V -= _partial_shear_left(x, partials)
            if abs(V) <= threshold_kN:
                return L_m - x
        return L_m / 2.0


def compute_Mu(
    Wu: float,
    L: float,
    support: SupportType,
    factored_points: list[tuple[float, float, str]] | None = None,
) -> float:
    """Factored design moment · kN·m.

    If factored_points is None or empty → existing closed-form formula:
      - simply-supported:  Mu = Wu·L²/8
      - cantilever:        Mu = Wu·L²/2 (at fixed end)
      - continuous:        Mu = Wu·L²/10 (typical interior · ACI 8.3 coefficient method)

    If factored_points provided AND support = simply-supported →
      use envelope max from compute_envelope_ss (NOT necessarily at L/2).
    Cantilever/continuous + points → raises InvalidInputError (Session 2 OOS).
    """
    if not factored_points:
        if support == SupportType.SIMPLY_SUPPORTED:
            return Wu * L * L / 8.0
        elif support == SupportType.CANTILEVER:
            return Wu * L * L / 2.0
        elif support == SupportType.CONTINUOUS:
            return Wu * L * L / 10.0
        raise InvalidInputError(f"Unknown support type: {support}")
    # Has points · only simply-supported in Session 2
    if support != SupportType.SIMPLY_SUPPORTED:
        raise InvalidInputError(
            f"Point loads + {support.value} ไม่รองรับใน Session 2 (เฉพาะ simply-supported)"
        )
    env = compute_envelope_ss(Wu, L, factored_points)
    return env["M_max"]


def compute_Vu(
    Wu: float,
    L: float,
    support: SupportType,
    factored_points: list[tuple[float, float, str]] | None = None,
) -> float:
    """Factored design shear · kN (envelope absolute maximum).

    UDL-only fallback (closed-form):
      - simply-supported:  Vu = Wu·L/2
      - cantilever:        Vu = Wu·L
      - continuous:        Vu ≈ Wu·L/2 (approximation)

    With point loads (simply-supported only Session 2) → envelope max from compute_envelope_ss.
    """
    if not factored_points:
        if support == SupportType.SIMPLY_SUPPORTED:
            return Wu * L / 2.0
        elif support == SupportType.CANTILEVER:
            return Wu * L
        elif support == SupportType.CONTINUOUS:
            return Wu * L / 2.0
        raise InvalidInputError(f"Unknown support type: {support}")
    if support != SupportType.SIMPLY_SUPPORTED:
        raise InvalidInputError(
            f"Point loads + {support.value} ไม่รองรับใน Session 2 (เฉพาะ simply-supported)"
        )
    env = compute_envelope_ss(Wu, L, factored_points)
    return env["V_max"]


def kNm_to_kgcm(M_kNm: float) -> float:
    """Convert moment from kN·m to kg·cm.
    1 kN·m = 102 kg·m (g=9.81 m/s² · using g=9.80665 to 4 sig figs · skill uses 102 = 1 kN ≈ 102 kgf).
    1 kN·m = 102 kg·m = 10,197 kg·cm (precise) · skill uses 10197 to keep consistency.
    """
    return M_kNm * 10197.0


def compute_Rn(Mu_kg_cm: float, b: float, d: float, phi: float = PHI_FLEXURE) -> float:
    """Required strength index Rn = Mu / (φ · b · d²) · ksc."""
    if d <= 0:
        raise InvalidInputError(f"d = {d} ≤ 0 · cannot compute Rn")
    return Mu_kg_cm / (phi * b * d * d)


def compute_rho_design(fc: float, fy: float, Rn: float) -> float:
    """Solve quadratic for ρ given Rn.

    ρ = (0.85·f'c / fy) · [1 − √(1 − 2·Rn / (0.85·f'c))]

    Raises SectionTooSmallError if sqrt argument goes negative.

    Source: มงคล Eq 3.8 (verified 2026-05-28 Hr 7 citation spot-check).
    Derived from Eq 3.5 (Mn) + Eq 3.4 (a) + Eq 3.7 (Rn) chain · Chapter 3 pp 41-43.
    """
    inside_sqrt = 1.0 - (2.0 * Rn) / (0.85 * fc)
    if inside_sqrt < -FLOAT_TOL:
        raise SectionTooSmallError(
            f"Mu สูงเกินกว่าหน้าตัดจะรับได้ (Rn = {Rn:.2f} · 2Rn/0.85fc = {2*Rn/(0.85*fc):.4f} > 1) "
            f"· ต้องขยายหน้าตัด (h หรือ b) ก่อน retry"
        )
    # clamp negative tolerance to 0 (floating point edge)
    inside_sqrt = max(0.0, inside_sqrt)
    return (0.85 * fc / fy) * (1.0 - math.sqrt(inside_sqrt))


def apply_rho_limits(
    rho_design: float, rho_min: float, rho_max: float
) -> tuple[float, list[str]]:
    """Apply ρmin/ρmax limits · return (rho_final, notes_list).

    Decision tree per [[RC Beam Design Procedure (Thai compliance)]] Step 7.

    Raises:
        OverReinforcedError: if rho_design > rho_max + FLOAT_TOL
    """
    notes: list[str] = []
    if rho_design < rho_min - FLOAT_TOL:
        notes.append(
            f"ρ_design = {rho_design:.5f} < ρmin = {rho_min:.5f} · ใช้ ρmin (auto · ตาม มงคล Eq 3.16)"
        )
        return rho_min, notes
    if rho_design > rho_max + FLOAT_TOL:
        raise OverReinforcedError(
            f"ρ_design = {rho_design:.5f} > ρmax = {rho_max:.5f} · "
            "หน้าตัดเล็กเกินสำหรับ singly-reinforced · "
            "ลอง: (1) ขยายหน้าตัด · (2) doubly-reinforced (เกิน MVP) · (3) เพิ่ม f'c"
        )
    return rho_design, notes


def compute_As(rho: float, b: float, d: float) -> float:
    """Required steel area · cm²."""
    return rho * b * d


def compute_stress_block_depth(As: float, fy: float, fc: float, b: float) -> float:
    """a = (As · fy) / (0.85 · f'c · b) · cm"""
    return (As * fy) / (0.85 * fc * b)


def compute_Mn(As: float, fy: float, d: float, a: float) -> float:
    """Nominal moment capacity · Mn = As · fy · (d − a/2) · kg·cm"""
    return As * fy * (d - a / 2.0)


# εcu·Es = 0.003 × 2,040,000 ≈ 6,120 ksc · หน่วยแรงสูงสุดในเหล็กตามความเครียด (DRMK p65-70)
_EPS_CU_ES_KSC: float = 6120.0


def compute_doubly_reinforced(
    Mu_kg_cm: float, b: float, d: float, d_prime: float,
    fc: float, fy: float, beta1: float, rho_max: float,
    phi: float = PHI_FLEXURE,
) -> Optional[dict]:
    """ออกแบบหน้าตัดเสริมเหล็กคู่ (doubly-reinforced) เมื่อ singly เกิน ρmax.

    DRMK SDM 3 Bending · book p70 · ตัวอย่าง 3.10 (verified · uat_doubly).
    หน่วย: Mu_kg_cm = kg·cm · b/d/d_prime = cm · fc/fy = ksc · As = cm².
    คืน dict {As1, As2, As, As_prime, fs_prime, yields, a, c, Mn1, Mn2, Mn} หรือ
    None ถ้า doubly ช่วยไม่ได้ (c ≤ d′ → เหล็กอัดอยู่นอกโซนอัด · ต้องขยายหน้าตัด).
    ductility: (ρ − ρ′·fs′/fy) = ρmax โดยอัตโนมัติ → เหล็กดึงครากเสมอ (DRMK Eq 3.36).
    """
    # couple-1: คอนกรีต ↔ เหล็กดึง As1 (ที่ ρmax)
    As1 = rho_max * b * d
    a = compute_stress_block_depth(As1, fy, fc, b)      # As1·fy/(0.85 fc b)
    c = a / beta1
    if c <= d_prime + FLOAT_TOL:
        return None     # เหล็กอัดอยู่ที่/ใต้แกนสะเทิน → ใช้ไม่ได้ · ต้องขยายหน้าตัด
    Mn1 = compute_Mn(As1, fy, d, a)                     # As1·fy·(d − a/2)
    Mn2 = (Mu_kg_cm / phi) - Mn1
    if Mn2 <= FLOAT_TOL:
        return None     # singly พอแล้ว (caller ควรไม่เรียกถึงตรงนี้)
    # couple-2: เหล็กอัด As′ ↔ เหล็กดึงเพิ่ม As2 (ระยะแขน d − d′)
    As2 = Mn2 / (fy * (d - d_prime))
    fs_prime = _EPS_CU_ES_KSC * (1.0 - d_prime / c)     # หน่วยแรงเหล็กอัดตามความเครียด
    yields = fs_prime >= fy - FLOAT_TOL
    if yields:
        fs_prime = fy
    if fs_prime <= FLOAT_TOL:
        return None
    As_prime = As2 * fy / fs_prime                       # As′·fs′ = As2·fy
    return {
        "As1": As1, "As2": As2, "As": As1 + As2, "As_prime": As_prime,
        "a": a, "c": c, "Mn1": Mn1, "Mn2": Mn2,
        "Mn": Mn1 + As2 * fy * (d - d_prime),
        "fs_prime": fs_prime, "yields": yields,
    }


def analyze_doubly_capacity(
    As_t: float, As_c: float, b: float, d: float, d_prime: float,
    fc: float, fy: float, beta1: float,
) -> tuple:
    """วิเคราะห์กำลังโมเมนต์หน้าตัดเสริมเหล็กคู่จาก "เหล็กที่จัดจริง" (As_t ดึง · As_c อัด)
    ด้วย strain compatibility เต็ม (เหล็กดึง+อัด อาจคราก/ไม่คราก). DRMK Ex 3.8.
    คืน (Mn_kg_cm, a_cm, fs_prime_ksc, fs_tension_ksc, tension_yields).

    สมดุล: 0.85·fc·b·(β1·c) + As_c·fs_c(c) = As_t·fs_t(c)
      fs_t(c) = min(fy, 6120·(d−c)/c) · fs_c(c) = min(fy, 6120·(c−d′)/c) [0 ถ้า c≤d′]
    net(c) = Cc+Cs−T เพิ่มตาม c → bisection หา c สมดุล · เช็ค ductility (เหล็กดึงครากไหม · Codex P1 #27 r4).
    """
    def _fst(c):
        return min(fy, _EPS_CU_ES_KSC * (d - c) / c) if c > 0 else fy
    def _fsc(c):
        return min(fy, _EPS_CU_ES_KSC * (c - d_prime) / c) if c > d_prime else 0.0
    def _net(c):   # Cc + Cs − T · เพิ่มตาม c (Cc,Cs↑ · T↓)
        return 0.85 * fc * b * (beta1 * c) + As_c * _fsc(c) - As_t * _fst(c)
    lo, hi = 1e-4, d
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _net(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    c = 0.5 * (lo + hi)
    a = beta1 * c
    fs_prime, fs_t = _fsc(c), _fst(c)
    Mn = 0.85 * fc * b * a * (d - a / 2.0) + As_c * fs_prime * (d - d_prime)
    tension_yields = fs_t >= fy - 1.0   # เหล็กดึงคราก → ductile → φ=0.90 ใช้ได้
    return Mn, a, fs_prime, fs_t, tension_yields


# ----------------------------------------------------------------------------
# Rebar selection
# ----------------------------------------------------------------------------


def _load_rebar_table() -> dict:
    """Load rebar_table.json from skill directory · cached at module level if needed."""
    here = Path(__file__).parent
    path = here / "rebar_table.json"
    return json.loads(path.read_text(encoding="utf-8"))


def select_rebar(
    As_required: float,
    b: float,
    cover: float,
    d_stirrup: float,
    h_cm: float = None,
    rho_max: float = None,
) -> Optional[RebarSelection]:
    """Pick a practical rebar combination satisfying As_provided ≥ As_required.

    Strategy: single-size combos first, then 2-size mixes.
    Clear spacing = max(db, 2.5, 1.33·d_agg) (รวมมวลรวม · กัน honeycomb). ถ้าชั้นเดียวกว้างไม่พอ →
    จัด multi-layer (≤ MAX_REBAR_LAYERS). Tie-break: **ชั้นน้อยกว่าชนะ** (single-layer ถ้า fit เสมอ) แล้ว As น้อยสุด.

    ถ้าให้ h_cm + rho_max → **กรอง candidate ที่ over-reinforced** (ρ_provided=As/(b·d) ที่ความลึกจริง
    ของ combo นั้น > rho_max) ออก → กัน false-failure ที่เลือก combo ชั้นน้อยแต่ over-reinforced
    ทั้งที่ combo ชั้นมากกว่า (As น้อยกว่า) ผ่านได้ (Codex P2 #26). ไม่ให้ → ไม่กรอง (backward-compat).

    Returns RebarSelection (มี n_layers) หรือ None ถ้าเกิน MAX_REBAR_LAYERS / over-reinforced ทุก combo.
    """
    table = _load_rebar_table()
    sizes = table["sizes"]

    available = b - 2 * cover - 2 * d_stirrup
    if available <= 0:
        return None

    best: Optional[RebarSelection] = None

    def _over_reinforced(c: RebarSelection) -> bool:
        # ρ_provided ที่ความลึกจริงของ combo นี้ > rho_max ? (ใช้ db ใหญ่สุด · n_layers ของ combo)
        if not (h_cm and rho_max):
            return False
        nb = sum(n for _, n in c.main_bars)
        mdb = max((int("".join(ch for ch in nm if ch.isdigit()) or 0) for nm, _ in c.main_bars), default=16) / 10.0
        d = effective_depth_multilayer(h_cm, cover, d_stirrup, mdb, nb, c.n_layers)
        return d <= 0 or (c.As_provided / (b * d)) > rho_max + 1e-9

    def _key(c: RebarSelection):
        # prefer (1) ชั้นน้อย → single ชนะ multi เสมอ
        # (2) MULTILAYER: db เล็กกว่าก่อน (db เล็ก → c.g. ตื้น → d ใหญ่ → กำลังมากกว่าที่ As ใกล้กัน · Codex P2 false-failure)
        #     single-layer: slot=0 (db ไม่กระทบ d มาก → ใช้ As เป็นหลัก = baseline เดิม)
        # (3) over-provision น้อย (4) จำนวนเส้นน้อย (กัน 8-เส้นจิ๋วชนะ 2-เส้นปกติ)
        maxdb = max((int("".join(ch for ch in nm if ch.isdigit()) or 0) for nm, _ in c.main_bars), default=0)
        db_pref = maxdb if c.n_layers >= 2 else 0
        return (c.n_layers, db_pref, round(c.As_provided, 4), sum(n for _, n in c.main_bars))

    def _consider(combo: RebarSelection):
        nonlocal best
        if _over_reinforced(combo):     # ข้าม combo ที่ over-reinforced ที่ความลึกจริง (Codex P2 #26 · กัน false-failure)
            return
        if best is None or _key(combo) < _key(best):
            best = combo

    # 1) single-size combos
    for size in sizes:
        db = size["diameter_cm"]
        area_per_bar = size["area_cm2"]
        mc = min_clear_spacing(db)
        per = min(max_bars_per_layer(available, db), PRACTICAL_MAX_PER_LAYER)   # เส้น/ชั้น · cap practical 6
        if per < 1:                                     # เหล็กเส้นนี้ไม่ลอดความกว้าง → ข้าม (Codex P1)
            continue
        n_cap = MAX_REBAR_LAYERS * per
        for n in range(2, n_cap + 1):
            if n * area_per_bar < As_required:
                continue
            n_layers = -(-n // per)                     # ceil(n/per)
            if n_layers > MAX_REBAR_LAYERS:
                continue
            note = [] if n_layers == 1 else [
                f"เหล็ก {n} เส้นจัด {n_layers} ชั้น (กว้างไม่พอชั้นเดียว · d ลดตาม c.g. · ระยะดิ่ง ≥{REBAR_LAYER_VCLEAR_CM} ซม.)"]
            _consider(RebarSelection(
                main_bars=[(size["name"], n)], As_provided=n * area_per_bar,
                spacing_min_clear=mc, fits_in_one_layer=(n_layers == 1),
                n_layers=n_layers, notes=note))
            break  # smallest n for this size

    # 2) 2-size mixes
    for big in sizes:
        for small in sizes:
            if small["diameter_cm"] >= big["diameter_cm"]:
                continue
            mc = min_clear_spacing(big["diameter_cm"])          # ใช้ db ใหญ่ = conservative
            per = min(max_bars_per_layer(available, big["diameter_cm"]), PRACTICAL_MAX_PER_LAYER)
            if per < 1:                                 # bar ใหญ่ไม่ลอดความกว้าง → ข้าม (Codex P1 · กัน div-by-zero)
                continue
            for n_big in range(2, 5):
                for n_small in range(1, 3):
                    total_area = n_big * big["area_cm2"] + n_small * small["area_cm2"]
                    if total_area < As_required:
                        continue
                    n_total = n_big + n_small
                    n_layers = -(-n_total // per)
                    if n_layers > MAX_REBAR_LAYERS:
                        continue
                    notes = ["mixed-size combo · check production detailing"]
                    if n_layers > 1:
                        notes.append(f"จัด {n_layers} ชั้น · d ลดตาม c.g.")
                    _consider(RebarSelection(
                        main_bars=[(big["name"], n_big), (small["name"], n_small)],
                        As_provided=total_area, spacing_min_clear=mc,
                        fits_in_one_layer=(n_layers == 1), n_layers=n_layers, notes=notes))

    return best


# ----------------------------------------------------------------------------
# Main orchestrator
# ----------------------------------------------------------------------------


def design_beam(inp: BeamInput) -> BeamOutput:
    """End-to-end design · returns BeamOutput with full trace.

    Follows [[RC Beam Design Procedure (Thai compliance)]] 12-step procedure.
    """
    out = BeamOutput(input=inp)

    # Step 0 · validate
    out.warnings = validate_input(inp)

    # Step 1 · effective depth (assumed)
    out.d_assumed = compute_effective_depth(inp.h, inp.cover, inp.d_stirrup, inp.db_assume)

    # Step 2-2.5 · Compute loads (UDL + point loads · Session 2)
    out.Wu = compute_Wu(inp.DL, inp.LL, inp.load_combo)
    factored_points = _factor_point_loads(inp.point_loads, inp.load_combo)
    factored_partials = _factor_partial_udls(inp.partial_udls, inp.load_combo)
    if factored_partials and inp.support != SupportType.SIMPLY_SUPPORTED:
        raise InvalidInputError(
            f"Partial UDL รองรับเฉพาะคานช่วงเดียว (simply-supported) · "
            f"ได้ support = {inp.support.value}"
        )
    for _w, _x1, _x2, _k in factored_partials:
        if _x1 < -FLOAT_TOL or _x2 > inp.L + FLOAT_TOL:
            raise InvalidInputError(
                f"Partial UDL ช่วง [{_x1}, {_x2}] ต้องอยู่ใน [0, L={inp.L}] m"
            )
    out.point_loads_factored = [
        {"Pu": Pu, "x": x, "kind": kind} for Pu, x, kind in factored_points
    ]
    env = None   # moment envelope (เก็บไว้ให้ curtailment envelope ใช้ · Path A)
    if (factored_points or factored_partials) and inp.support == SupportType.SIMPLY_SUPPORTED:
        env = compute_envelope_ss(out.Wu, inp.L, factored_points, partials=factored_partials)
        out.Mu = env["M_max"]
        out.Vu = env["V_max"]
        out.R_A = env["R_A"]
        out.R_B = env["R_B"]
        out.x_at_M_max = env["x_at_M_max"]
        out.x_at_V_max = env["x_at_V_max"]
    else:
        out.Mu = compute_Mu(out.Wu, inp.L, inp.support, factored_points or None)
        out.Vu = compute_Vu(out.Wu, inp.L, inp.support, factored_points or None)
        # closed-form reactions for UDL-only simply-supported
        if inp.support == SupportType.SIMPLY_SUPPORTED:
            out.R_A = out.Wu * inp.L / 2.0
            out.R_B = out.Wu * inp.L / 2.0
            out.x_at_M_max = inp.L / 2.0
            out.x_at_V_max = 0.0
    out.Mu_kg_cm = kNm_to_kgcm(out.Mu)

    # Step 2 · β1
    out.beta1 = compute_beta1(inp.fc)

    # Step 3 · ρb
    out.rho_b = compute_rho_b(inp.fc, inp.fy, out.beta1)

    # Step 4 · limits
    out.rho_min = compute_rho_min(inp.fy)
    out.rho_max = compute_rho_max(out.rho_b)

    # Step 5 · Rn
    out.Rn = compute_Rn(out.Mu_kg_cm, inp.b, out.d_assumed, PHI_FLEXURE)

    # rebar-table helper (ใช้ทั้ง singly + doubly path)
    rebar_table = _load_rebar_table()

    def _db_of(rb):
        return next((s["diameter_cm"] for s in rebar_table["sizes"]
                     if s["name"] == rb.main_bars[0][0]), inp.db_assume)

    # Step 5.5 · ตัดสิน singly vs doubly — กำลัง singly สูงสุดที่ ρmax (DRMK book p70)
    #   Mu ≤ φMn1_max → singly (เดิม · zero-reg) · เกิน + simply-supported → doubly (เสริมเหล็กรับแรงอัด)
    #   ⚠️ doubly เฉพาะ SIMPLY_SUPPORTED — สมมติเหล็กดึงล่าง/เหล็กอัดบน · cantilever (fixed-end −M)
    #   เหล็กดึงบน/อัดล่าง = สลับด้าน → ไม่รองรับใน scope นี้ → คงพฤติกรรมเดิม (raise OverReinforcedError) · Codex P1 #27
    _As1_max = out.rho_max * inp.b * out.d_assumed
    _phi_Mn1_max = PHI_FLEXURE * compute_Mn(
        _As1_max, inp.fy, out.d_assumed,
        compute_stress_block_depth(_As1_max, inp.fy, inp.fc, inp.b))
    _use_doubly = (out.Mu_kg_cm > _phi_Mn1_max + FLOAT_TOL
                   and inp.support == SupportType.SIMPLY_SUPPORTED)

    if not _use_doubly:
        # ═══════════ SINGLY-REINFORCED (path เดิม · ไม่แตะ · zero-reg) ═══════════
        #   non-simply-supported ที่เกิน ρmax → compute_rho_design/apply_rho_limits raise เหมือนเดิม
        # Step 6 · ρ_design (may raise SectionTooSmallError)
        out.rho_design = compute_rho_design(inp.fc, inp.fy, out.Rn)

        # Step 7 · limit check (may raise OverReinforcedError)
        out.rho_final, limit_notes = apply_rho_limits(out.rho_design, out.rho_min, out.rho_max)
        out.notes.extend(limit_notes)

        # Step 8 · As_req
        out.As_required = compute_As(out.rho_final, inp.b, out.d_assumed)

        # Step 9 · rebar selection
        out.rebar = select_rebar(
            out.As_required, inp.b, inp.cover, inp.d_stirrup, inp.h, out.rho_max
        )
        if out.rebar is None:
            out.notes.append("ไม่พบ rebar combo ที่ fit ในหน้าตัดนี้ · ต้องขยาย b หรือ ใช้ multi-layer (เกิน MVP)")
            out.passes = False
            return out

        # Step 10 · d_actual after rebar selection (multilayer-aware · c.g. หลายชั้น)
        out.d_actual = _rebar_d(inp.h, inp.cover, inp.d_stirrup, out.rebar, _db_of(out.rebar))
        # multilayer (nl≥2) → c.g. ลึกขึ้น → d เล็กลง → recompute As ที่ d จริง · bounded · honest
        #   single-layer (nl=1) → d_actual = baseline เดิมเป๊ะ (h−cover−stir−db/2) · ไม่ iterate (zero-reg)
        for _ in range(3):
            if out.rebar.n_layers < 2 or out.d_actual >= out.d_assumed - 0.01:
                break
            try:
                Rn2 = compute_Rn(out.Mu_kg_cm, inp.b, out.d_actual, PHI_FLEXURE)
                rho2 = compute_rho_design(inp.fc, inp.fy, Rn2)
                rf2, _n2 = apply_rho_limits(rho2, out.rho_min, out.rho_max)
            except CivilCalcError:
                break   # ที่ d จริงหน้าตัดไม่พอ → หยุด · ρ_provided check ด้านล่างจะจับ over-reinforced (Codex P1 #26)
            As2 = compute_As(rf2, inp.b, out.d_actual)
            rb2 = select_rebar(As2, inp.b, inp.cover, inp.d_stirrup, inp.h, out.rho_max)
            if rb2 is None or rb2.As_provided <= out.rebar.As_provided + 1e-9:
                break   # ไม่มี combo ดีกว่า → หยุด (รับผลปัจจุบัน)
            out.rebar, out.As_required, out.rho_final, out.Rn, out.rho_design = rb2, As2, rf2, Rn2, rho2
            d_prev = out.d_actual
            out.d_actual = _rebar_d(inp.h, inp.cover, inp.d_stirrup, out.rebar, _db_of(out.rebar))
            if abs(out.d_actual - d_prev) < 0.01:
                break

        # Step 11 · final check (flexure)
        out.a_stress_block = compute_stress_block_depth(
            out.rebar.As_provided, inp.fy, inp.fc, inp.b
        )
        out.Mn = compute_Mn(out.rebar.As_provided, inp.fy, out.d_actual, out.a_stress_block)
        out.phi_Mn = PHI_FLEXURE * out.Mn
        out.passes_flexure = out.phi_Mn >= out.Mu_kg_cm - FLOAT_TOL
        if out.Mu_kg_cm > FLOAT_TOL:
            out.safety_margin_pct = (out.phi_Mn - out.Mu_kg_cm) / out.Mu_kg_cm * 100.0
        # ρ ที่ใช้จริง (As_provided) ที่ความลึกจริง ต้อง ≤ ρmax (singly-reinforced) — กัน over-reinforced
        #   ที่ multilayer ทำให้ d เล็กลง (ครอบทุก path · แม้ recompute ไม่ raise · Codex P1 #26 round-2/3)
        if out.rebar and out.d_actual > 0:
            rho_prov = out.rebar.As_provided / (inp.b * out.d_actual)
            if rho_prov > out.rho_max + 1e-9:
                out.passes_flexure = False
                out.notes.append(f"🔴 ρ ที่ใช้ ({rho_prov:.4f}) > ρmax ({out.rho_max:.4f}) ที่ความลึกจริง d={out.d_actual:.2f} ซม. "
                                 "— over-reinforced (singly-reinforced ไม่ผ่าน) · ต้องขยายหน้าตัด หรือ ใส่เหล็กรับแรงอัด")
    else:
        # ═══════════ DOUBLY-REINFORCED (NEW · DRMK book p70 · เหล็กรับแรงอัด) ═══════════
        out.is_doubly = True
        # fixed-point: req(d,d′) → เลือกเหล็ก → อัปเดต d,d′ เป็น geometry "เหล็กจริง" → วน จนชุดเหล็กนิ่ง (bar-set stable)
        #   d′ = h − _rebar_d(rebar_compression) = centroid จากผิวบน (multilayer-aware · mirror · Codex P1 r1)
        #   ที่จุดนิ่ง: dr คิดที่ d ของเหล็กจริง → As_prov/As′_prov ≥ req โดยสร้าง (req ตรง geometry · Codex P2 r6/r7)
        d_prime = inp.cover + inp.d_stirrup + inp.db_assume / 2.0
        d_cur, dr, rb, rbc, prev_key = out.d_assumed, None, None, None, None
        for _ in range(12):
            dr = compute_doubly_reinforced(out.Mu_kg_cm, inp.b, d_cur, d_prime,
                                           inp.fc, inp.fy, out.beta1, out.rho_max)
            if dr is None:
                break
            rb = select_rebar(dr["As"], inp.b, inp.cover, inp.d_stirrup, inp.h)         # multilayer · ข้าม ρmax filter (ตั้งใจ)
            rbc = select_rebar(dr["As_prime"], inp.b, inp.cover, inp.d_stirrup, inp.h)   # เหล็กอัด · ไม่จำกัด ρ ดึง
            if rb is None or rbc is None:                                               # fit ไม่ได้ → fail (Codex P1 r3)
                dr = None
                break
            key = (tuple(rb.main_bars), tuple(rbc.main_bars))
            d_cur = _rebar_d(inp.h, inp.cover, inp.d_stirrup, rb, _db_of(rb))
            d_prime = inp.h - _rebar_d(inp.h, inp.cover, inp.d_stirrup, rbc, _db_of(rbc))
            if key == prev_key:               # ชุดเหล็กไม่เปลี่ยน → จุดนิ่ง
                break
            prev_key = key
        # recompute requirement ที่ "geometry เหล็กจริง" (d_cur/d′ ของเหล็กชุดล่าสุด) · Codex P2 r6/r7
        if dr is not None and rb is not None and rbc is not None:
            dr = compute_doubly_reinforced(out.Mu_kg_cm, inp.b, d_cur, d_prime,
                                           inp.fc, inp.fy, out.beta1, out.rho_max)
        # consistency gate: เหล็กที่เลือก "พอ" กับ req ที่ geometry จริงไหม (As_prov ≥ As_req · As′_prov ≥ As′_req)
        #   ผ่าน → reported req สอดคล้องเหล็กจริง (ไม่มี req>prov หลอกตา) · ไม่ผ่าน/ไม่ลู่เข้า → fail (conservative · Codex P2 r6/r7)
        if (dr is None or rb is None or rbc is None
                or rb.As_provided < dr["As"] - 0.05
                or rbc.As_provided < dr["As_prime"] - 0.05):
            out.notes.append("🔴 หน้าตัดเล็กเกิน/ไม่ลู่เข้าแม้เสริมเหล็กคู่ (doubly) · ต้องขยายหน้าตัด (h/b) หรือ เพิ่ม f'c")
            out.rebar, out.rebar_compression = None, None
            out.passes_flexure = False
            out.passes = False
            return out
        out.rebar, out.rebar_compression = rb, rbc
        out.d_actual = d_cur
        out.As1, out.As2 = dr["As1"], dr["As2"]
        out.As_required = dr["As"]
        out.As_prime_required = dr["As_prime"]
        out.rho_final = (out.rebar.As_provided / (inp.b * out.d_actual)) if out.d_actual > 0 else 0.0
        out.rho_design = out.rho_final
        # Step 11 (doubly) · verify φMn จากเหล็กที่จัดจริง (strain compatibility เต็ม · DRMK Ex 3.8)
        As_c_prov = out.rebar_compression.As_provided if out.rebar_compression else 0.0
        out.Mn, out.a_stress_block, out.fs_prime_ksc, _fs_t, _t_yields = analyze_doubly_capacity(
            out.rebar.As_provided, As_c_prov, inp.b, out.d_actual, d_prime,
            inp.fc, inp.fy, out.beta1)
        # flag เหล็กอัดคราก/ไม่คราก จากผล "วิเคราะห์เหล็กจัดจริง" (ไม่ใช่ design dr · Codex P2 #27 r5)
        out.comp_steel_yields = out.fs_prime_ksc >= inp.fy - 1.0
        out.phi_Mn = PHI_FLEXURE * out.Mn
        # ductility: เหล็กดึงต้องครากที่เหล็ก "จัดจริง" → φ=0.90 ถึงใช้ได้ (over-provision อาจทำเหล็กดึงไม่คราก · Codex P1 #27 r4)
        out.passes_flexure = (out.phi_Mn >= out.Mu_kg_cm - FLOAT_TOL) and _t_yields
        _yld = "คราก" if out.comp_steel_yields else f"ไม่คราก (fs′={out.fs_prime_ksc:.0f} ksc)"
        out.notes.append(
            f"หน้าตัดเสริมเหล็กคู่ (doubly · Mu เกินกำลัง singly ที่ ρmax): เหล็กดึง As={dr['As']:.2f} ซม.² "
            f"(As1={dr['As1']:.2f}+As2={dr['As2']:.2f}) · เหล็กอัดบน As′={dr['As_prime']:.2f} ซม.² ({_yld}) "
            f"· d′={d_prime:.1f} ซม. · DRMK book p70 · ควรขยายหน้าตัดก่อนถ้าทำได้")
        if not _t_yields:
            out.notes.append(
                f"🔴 เหล็กดึงไม่คราก (fs={_fs_t:.0f} < fy={inp.fy:.0f} ksc) ที่เหล็กจัดจริง — "
                "หน้าตัด over-reinforced หลังเลือกเหล็ก · φ=0.90 ใช้ไม่ได้ (ไม่ ductile) · ต้องขยายหน้าตัด หรือ ลด/ปรับเหล็ก")
        if out.Mu_kg_cm > FLOAT_TOL:
            out.safety_margin_pct = (out.phi_Mn - out.Mu_kg_cm) / out.Mu_kg_cm * 100.0

    # Step 11.5 · Session 2 · Shear stirrup design (only for simply-supported · Session 2 scope)
    if inp.support == SupportType.SIMPLY_SUPPORTED:
        try:
            out.stirrup_design = design_shear(
                Wu_kN_m=out.Wu,
                L_m=inp.L,
                R_A_kN=out.R_A if out.R_A > 0 else (out.Wu * inp.L / 2.0),
                R_B_kN=out.R_B if out.R_B > 0 else (out.Wu * inp.L / 2.0),
                factored_points=factored_points,
                b_cm=inp.b,
                d_cm=out.d_actual,
                fc_ksc=inp.fc,
                fyt_ksc=_FYT_STIRRUP_DEFAULT_KSC,
                phi=PHI_SHEAR,
                n_legs=inp.stirrup_legs,
                partials=factored_partials,
            )
            out.passes_shear = bool(out.stirrup_design.get("passes", False))
            # Merge shear citations into main list
            out.citations.extend(out.stirrup_design.get("citations", []))
            out.notes.extend(out.stirrup_design.get("notes", []))
        except SectionTooSmallForShearError as exc:
            out.stirrup_design = {
                "branch": "FAIL",
                "passes": False,
                "error": str(exc),
                "shop_drawing_notation": "หน้าตัดไม่พอ · ต้องขยาย",
                "notes": [str(exc)],
            }
            out.passes_shear = False
            out.notes.append(f"Shear FAIL: {exc}")
    else:
        # Cantilever/continuous · shear design skipped (Session 3+ scope)
        out.stirrup_design = {
            "branch": "OUT_OF_SCOPE",
            "passes": True,
            "shop_drawing_notation": f"Shear ของ {inp.support.value} = Session 3+",
        }
        out.passes_shear = True

    # Overall pass = flexure AND shear
    out.passes = bool(out.passes_flexure and out.passes_shear)

    # Serviceability · ความลึกน้อยที่สุด (DRMK ตาราง 3.1 · advisory · ไม่เปลี่ยน passes กำลัง · ตัวเลือก ก)
    #   คานช่วงเดียว L/16 · (คานยื่นผ่าน design_beam → L/8 · ปกติคานยื่นใช้ทาง continuous อยู่แล้ว)
    _md_kind = "cantilever" if inp.support == SupportType.CANTILEVER else "simple"
    out.h_min_cm = min_beam_depth(inp.L, _md_kind, inp.fy)
    out.min_depth_ok = inp.h >= out.h_min_cm - FLOAT_TOL
    if not out.min_depth_ok:
        _r = "L/8" if _md_kind == "cantilever" else "L/16"
        out.warnings.append(
            f"🟡 ตื้นเกิน: h={inp.h:.0f} ซม. < ความลึกขั้นต่ำ {_r} = {out.h_min_cm:.1f} ซม. "
            f"(DRMK ตาราง 3.1 · {'คานยื่น' if _md_kind == 'cantilever' else 'คานช่วงเดียว'}) — "
            f"เสี่ยงแอ่นตัวเกิน · ต้องคำนวณระยะแอ่นจริง (ตาราง 10.3) หรือเพิ่มความลึก ก่อนใช้งานจริง")

    # Citations (Step 12 metadata · verified Hr 7)
    # PREPEND flexure citations (preserve shear citations already extended above)
    flex_citations = [
        f"β1 = {out.beta1:.3f} · มงคล Figure 3.10 piecewise (Whitney stress block factor · verified)",
        f"ρb = {out.rho_b:.5f} · มงคล Eq 3.12 (Balanced ratio · Thai units · verified)",
        f"ρmin = {out.rho_min:.5f} · มงคล Eq 3.16ก (14/fy · verified)",
        f"ρmax = {out.rho_max:.5f} · มงคล Eq 3.13 (0.75·ρb · ว.ส.ท. compliance · verified)",
        f"ρ_design quadratic · มงคล Eq 3.8 (derived from Eq 3.4 + 3.5 + 3.7 chain)",
        f"φ = {PHI_FLEXURE} · มงคล Section 1.6 (flexure · Thai)",
        f"Load combo = {inp.load_combo.value} · ACI 318-19 / มงคล Eq 2.9",
    ]
    # Session 2 · point load envelope citation if applicable
    if factored_points:
        flex_citations.append(
            f"Point load envelope · {len(factored_points)} จุด · M_max @ x={out.x_at_M_max:.3f} m "
            f"· R_A={out.R_A:.2f} kN · R_B={out.R_B:.2f} kN · superposition + statics (μงคล Ch.2)"
        )
    if factored_partials:
        _segs = " · ".join(
            f"w={_w:.2f} kN/m บน [{_x1:.2f},{_x2:.2f}] m" for _w, _x1, _x2, _k in factored_partials
        )
        flex_citations.append(
            f"Partial UDL · {len(factored_partials)} ชุด ({_segs}) · "
            f"resultant W=w·(x2−x1) ที่ centroid · superposition + statics (มงคล Ch.2)"
        )
    out.citations = flex_citations + list(out.citations)

    # detailing · ระยะหยุดเหล็กล่าง คานช่วงเดียว (bottom-only · อ่าน rebar ที่เลือกแล้ว · ไม่แตะ flexure core)
    #   เฉพาะ simply-supported · คานยื่น (CANTILEVER) เหล็กหลัก = บน (fixed-end) ไม่ใช่ bottom-cut (Codex P2)
    #   route (Path A): มีจุดโหลด/partial + มี moment envelope → ตัดจริงจาก envelope · ไม่งั้น fig 8.23 (L/8 ค่าประมาณ)
    if inp.support == SupportType.SIMPLY_SUPPORTED:
        _d_cur = out.d_actual or out.d_assumed
        if (factored_points or factored_partials) and env and env.get("M_grid"):
            out.curtailment = compute_curtailment_single_envelope(
                out.rebar, inp.L, _d_cur, inp.db_assume, inp.fy, inp.fc, inp.b,
                PHI_FLEXURE, env["M_grid"], env["x_grid"])
        else:
            out.curtailment = compute_curtailment_single(
                out.rebar, inp.L, _d_cur, inp.db_assume, inp.point_loads, inp.partial_udls)
    else:
        out.curtailment = None

    return out


# ============================================================================
# Session 3A · Multi-span continuous beam — ACI Moment Coefficient method
# Ref: DRMK Ch.2 ตารางที่ 2.8 / รูปที่ 2.8 + ตัวอย่างที่ 8.5 (PDF p.47-49, 217)
#      [[Formula - RC Continuous Beam ACI Moment Coefficients (RC-SDM)]]
# Units: L (=ln clear span) in m · DL/LL in kN/m · b,h,d in cm · fc,fy in ksc
# ============================================================================


class ContinuousConditionError(CivilCalcError):
    """ACI moment-coefficient conditions (5 ข้อ) violated.
    Engineering ethics (Gemini Q2): BLOCK + warn · ห้ามคำนวณต่อเงียบ ๆ."""
    pass


# End-support condition codes (drives exterior +M / -M coefficient)
_END_COLUMN = "column"       # หล่อเนื้อเดียวกับเสา → -M=wu·ln²/16 · +M(end)=wu·ln²/14
_END_SPANDREL = "spandrel"   # ที่รองรับเป็นคานขอบ → -M=wu·ln²/24 · +M(end)=wu·ln²/14
_END_SIMPLE = "simple"       # ปลายไม่ต่อเนื่องไม่ยึดรั้ง → -M=0 · +M(end)=wu·ln²/11


@dataclass
class SpanInput:
    """One span of a continuous beam. L = clear span (m) · DL/LL = UDL kN/m.
    point_loads: list of PointLoad {kind:'DL'/'LL', P:kN, x:m from LEFT end of THIS span}."""
    L: float
    DL: float
    LL: float
    point_loads: list = field(default_factory=list)


@dataclass
class ContinuousBeamInput:
    """Continuous beam (2-4 spans) on simple interior supports · ACI coefficient (3A)."""
    b: float
    h: float
    fc: float
    fy: float
    spans: list = field(default_factory=list)   # list[SpanInput]
    end_left: str = _END_COLUMN
    end_right: str = _END_COLUMN
    cover: float = 3.0
    d_stirrup: float = 0.9
    db_assume: float = 1.6
    load_combo: LoadCombo = LoadCombo.ACI_MODERN
    # Optional overhangs (cantilevers) at the free ends · dict shape:
    #   {"L":m, "DL":kN/m, "LL":kN/m, "point_loads":[{"kind":"DL"/"LL","P":kN,"x":m_from_support}]}
    left_cantilever: dict | None = None
    right_cantilever: dict | None = None


def _grid_label(i: int) -> str:
    """0 -> 'A', 1 -> 'B', ..."""
    return chr(ord("A") + i)


def _flexure_design_for_moment(
    Mu_kNm: float, b: float, h: float, fc: float, fy: float,
    cover: float, d_stirrup: float, db_assume: float,
) -> dict:
    """Design singly-reinforced flexure for a given Mu (kN·m). Reuses Ch.3 pipeline.
    Works for both +M (bottom steel) and -M (top steel) — only the location differs."""
    out: dict = {"Mu_kNm": Mu_kNm}
    if abs(Mu_kNm) <= FLOAT_TOL:
        out.update({"As_required": 0.0, "rebar": None, "passes": True,
                    "note": "M ≈ 0 · ไม่ต้องเหล็กรับโมเมนต์ (ใส่ขั้นต่ำตาม detailing)"})
        return out
    Mu_kgcm = kNm_to_kgcm(abs(Mu_kNm))
    beta1 = compute_beta1(fc)
    rho_b = compute_rho_b(fc, fy, beta1)
    rho_min = compute_rho_min(fy)
    rho_max = compute_rho_max(rho_b)
    rebar_table = _load_rebar_table()

    def _db_cm(rb):
        return next((s["diameter_cm"] for s in rebar_table["sizes"]
                     if s["name"] == rb.main_bars[0][0]), db_assume)

    # Iterate assumed-d → actual-d so the FINAL rebar verifies with the ACTUAL effective
    # depth (bigger bars shrink d → need slightly more As). Converges in 1-3 passes.
    d = compute_effective_depth(h, cover, d_stirrup, db_assume)
    rebar = None
    As_req = rho_final = Rn = a = Mn = phi_Mn = d_actual = 0.0
    limit_notes: list[str] = []
    for _ in range(5):
        Rn = compute_Rn(Mu_kgcm, b, d, PHI_FLEXURE)
        rho_design = compute_rho_design(fc, fy, Rn)   # raises SectionTooSmallError if too small
        rho_final, limit_notes = apply_rho_limits(rho_design, rho_min, rho_max)
        As_req = compute_As(rho_final, b, d)
        rebar = select_rebar(As_req, b, cover, d_stirrup, h, rho_max)
        if rebar is None:
            out.update({"As_required": As_req, "rebar": None, "passes": False,
                        "note": "ไม่พบ rebar combo ที่ fit · ต้องขยาย b หรือ multi-layer"})
            return out
        d_actual = _rebar_d(h, cover, d_stirrup, rebar, _db_cm(rebar))
        a = compute_stress_block_depth(rebar.As_provided, fy, fc, b)
        Mn = compute_Mn(rebar.As_provided, fy, d_actual, a)
        phi_Mn = PHI_FLEXURE * Mn
        if phi_Mn >= Mu_kgcm - FLOAT_TOL:
            break
        if d_actual < d - 0.01:
            d = d_actual            # actual depth shrank → recompute As at smaller d
            continue
        # depth stable but capacity short → bump steel proportional to shortfall
        As_target = As_req * (Mu_kgcm / max(phi_Mn, 1.0)) * 1.02
        bumped = select_rebar(As_target, b, cover, d_stirrup, h, rho_max)
        if bumped is not None:
            rebar = bumped
            d_actual = _rebar_d(h, cover, d_stirrup, rebar, _db_cm(rebar))
            a = compute_stress_block_depth(rebar.As_provided, fy, fc, b)
            Mn = compute_Mn(rebar.As_provided, fy, d_actual, a)
            phi_Mn = PHI_FLEXURE * Mn
        break

    passes = phi_Mn >= Mu_kgcm - FLOAT_TOL
    notes_out = list(limit_notes)
    over_reinforced = False
    # ρ_provided ที่ความลึกจริง ต้อง ≤ ρmax — กัน over-reinforced ที่ multilayer ทำให้ d เล็กลง
    #   (เหมือน design_beam · ครอบ continuous/cantilever path · Codex P1 #26 round-4)
    if rebar and d_actual > 0:
        rho_prov = rebar.As_provided / (b * d_actual)
        if rho_prov > rho_max + 1e-9:
            passes = False
            over_reinforced = True   # marker → _safe_flexure_design ลอง doubly fallback (continuous/cantilever)
            notes_out.append(f"🔴 ρ ที่ใช้ ({rho_prov:.4f}) > ρmax ({rho_max:.4f}) ที่ความลึกจริง d={d_actual:.2f} ซม. "
                             "— over-reinforced (singly-reinforced ไม่ผ่าน) · ต้องขยายหน้าตัด หรือ ใส่เหล็กรับแรงอัด")
    out.update({"As_required": As_req, "rho_final": rho_final, "rebar": rebar,
                "Rn": Rn, "notes": notes_out,
                "d_actual": d_actual, "a_stress_block": a, "Mn": Mn, "phi_Mn": phi_Mn,
                "passes": passes, "_over_reinforced": over_reinforced,
                "safety_margin_pct": (phi_Mn - Mu_kgcm) / Mu_kgcm * 100.0})
    return out


def _safe_flexure_design(Mu_kNm, b, h, fc, fy, cover, d_stirrup, db_assume, comp_on_top=True):
    """_flexure_design_for_moment that never raises: section inadequate → degrade gracefully.

    เมื่อ singly over-reinforced (raise SectionTooSmallError/OverReinforcedError หรือ ρ_prov>ρmax
    ที่ความลึกจริง · marker `_over_reinforced`) → **ลอง doubly fallback** (เสริมเหล็กรับแรงอัด)
    แทนการ fail ทันที · ครอบทุกหน้า: +M ช่วง (comp_on_top=True · เหล็กอัดบน) · −M หัวเสา/คานยื่น
    (comp_on_top=False · เหล็กอัดล่าง). (Cantilevers commonly produce large hogging moments.)"""
    res, over, err = None, False, None
    try:
        res = _flexure_design_for_moment(Mu_kNm, b, h, fc, fy, cover, d_stirrup, db_assume)
        over = bool(res.get("_over_reinforced"))
    except (SectionTooSmallError, OverReinforcedError) as exc:
        over, err = True, exc
    if over:
        doubly = _doubly_design_for_moment(
            Mu_kNm, b, h, fc, fy, cover, d_stirrup, db_assume, comp_on_top)
        if doubly is not None:
            return doubly                        # doubly ช่วยได้ → ผ่าน (override singly-fail)
    if res is not None:
        return res                               # singly result (ผ่าน หรือ fail ที่ doubly ก็ช่วยไม่ได้)
    return {"Mu_kNm": Mu_kNm, "As_required": None, "rebar": None, "passes": False,
            "d_actual": None, "phi_Mn": 0.0, "rho_final": 0.0,
            "note": f"หน้าตัดไม่พอแม้เสริมเหล็กคู่ (doubly): {err}"}


def _doubly_design_for_moment(
    Mu_kNm, b, h, fc, fy, cover, d_stirrup, db_assume, comp_on_top=True,
):
    """ออกแบบหน้าตัดเสริมเหล็กคู่ (doubly) สำหรับโมเมนต์เดียว — flexure core ของคานต่อเนื่อง/คานยื่น.

    Mirror ของ doubly branch ใน design_beam (fixed-point bar-stable + consistency gate +
    strain-compatibility · ตรง pattern PR #27) แต่ **standalone** → design_beam (single-span)
    ไม่ถูกแตะ = byte-identical (New Module · zero-reg by construction).

    หน้าวางเหล็กอัด:
      comp_on_top=True  → +M ช่วง (เหล็กดึงล่าง · เหล็กอัดบน)
      comp_on_top=False → −M หัวเสา/คานยื่น (เหล็กดึงบน · เหล็กอัดล่าง)
    **สูตร flexure เป็น face-agnostic** (d = h − ระยะหุ้มเหล็กดึง · d′ = ระยะหุ้มเหล็กอัด เท่ากันทั้งสองหน้า
    ตาม DRMK Ex 3.10) → comp_on_top ใช้กำกับ "หน้าวาง" สำหรับ display เท่านั้น ไม่ใช่ input ของ math.

    คืน dict (รูปร่างเดียวกับ _flexure_design_for_moment + doubly fields) หรือ None ถ้า doubly ช่วยไม่ได้
    (caller จะคง failing singly dict).
    """
    Mu_kgcm = kNm_to_kgcm(abs(Mu_kNm))
    beta1 = compute_beta1(fc)
    rho_max = compute_rho_max(compute_rho_b(fc, fy, beta1))
    rebar_table = _load_rebar_table()

    def _db_cm(rb):
        return next((s["diameter_cm"] for s in rebar_table["sizes"]
                     if s["name"] == rb.main_bars[0][0]), db_assume)

    # fixed-point: req(d,d′) → เลือกเหล็ก → อัปเดต d,d′ เป็น geometry "เหล็กจริง" → วน จนชุดเหล็กนิ่ง
    d_cur = compute_effective_depth(h, cover, d_stirrup, db_assume)
    d_prime = cover + d_stirrup + db_assume / 2.0
    dr = rb = rbc = prev_key = None
    for _ in range(12):
        dr = compute_doubly_reinforced(Mu_kgcm, b, d_cur, d_prime, fc, fy, beta1, rho_max)
        if dr is None:
            break
        rb = select_rebar(dr["As"], b, cover, d_stirrup, h)          # เหล็กดึง · multilayer · ข้าม ρmax filter (ตั้งใจ)
        rbc = select_rebar(dr["As_prime"], b, cover, d_stirrup, h)    # เหล็กอัด
        if rb is None or rbc is None:
            dr = None
            break
        key = (tuple(rb.main_bars), tuple(rbc.main_bars))
        d_cur = _rebar_d(h, cover, d_stirrup, rb, _db_cm(rb))
        d_prime = h - _rebar_d(h, cover, d_stirrup, rbc, _db_cm(rbc))
        if key == prev_key:               # ชุดเหล็กไม่เปลี่ยน → จุดนิ่ง
            break
        prev_key = key
    # recompute requirement ที่ geometry เหล็กจริง (d_cur/d′ ชุดล่าสุด)
    if dr is not None and rb is not None and rbc is not None:
        dr = compute_doubly_reinforced(Mu_kgcm, b, d_cur, d_prime, fc, fy, beta1, rho_max)
    # consistency gate: เหล็กที่เลือก "พอ" กับ req ที่ geometry จริงไหม · ไม่ผ่าน/ไม่ลู่เข้า → None (fail conservative)
    if (dr is None or rb is None or rbc is None
            or rb.As_provided < dr["As"] - 0.05
            or rbc.As_provided < dr["As_prime"] - 0.05):
        return None
    # verify φMn จากเหล็กที่จัดจริง (strain compatibility เต็ม · DRMK Ex 3.8)
    Mn, a, fs_prime, fs_t, t_yields = analyze_doubly_capacity(
        rb.As_provided, rbc.As_provided, b, d_cur, d_prime, fc, fy, beta1)
    phi_Mn = PHI_FLEXURE * Mn
    passes = (phi_Mn >= Mu_kgcm - FLOAT_TOL) and t_yields   # ductility: เหล็กดึงต้องครากที่เหล็กจัดจริง
    comp_yields = fs_prime >= fy - 1.0
    rho_final = (rb.As_provided / (b * d_cur)) if d_cur > 0 else 0.0
    _yld = "คราก" if comp_yields else f"ไม่คราก (fs′={fs_prime:.0f} ksc)"
    _face = "บน" if comp_on_top else "ล่าง"
    notes = [
        f"หน้าตัดเสริมเหล็กคู่ (doubly · Mu เกินกำลัง singly ที่ ρmax): เหล็กดึง As={dr['As']:.2f} ซม.² "
        f"(As1={dr['As1']:.2f}+As2={dr['As2']:.2f}) · เหล็กอัด{_face} As′={dr['As_prime']:.2f} ซม.² ({_yld}) "
        f"· d′={d_prime:.1f} ซม. · DRMK book p70 · เหล็กอัดต้องมีปลอกยึดทุกมุม (ระยะ ≤16db′) · ควรขยายหน้าตัดก่อนถ้าทำได้"
    ]
    if not t_yields:
        notes.append(
            f"🔴 เหล็กดึงไม่คราก (fs={fs_t:.0f} < fy={fy:.0f} ksc) ที่เหล็กจัดจริง — over-reinforced หลังเลือกเหล็ก "
            "· φ=0.90 ใช้ไม่ได้ (ไม่ ductile) · ต้องขยายหน้าตัด")
    return {
        "Mu_kNm": Mu_kNm, "As_required": dr["As"], "rho_final": rho_final, "rebar": rb,
        "notes": notes, "d_actual": d_cur, "a_stress_block": a, "Mn": Mn, "phi_Mn": phi_Mn,
        "passes": passes,
        "safety_margin_pct": ((phi_Mn - Mu_kgcm) / Mu_kgcm * 100.0) if Mu_kgcm > FLOAT_TOL else 0.0,
        "is_doubly": True, "As1": dr["As1"], "As2": dr["As2"],
        "As_prime_required": dr["As_prime"], "rebar_compression": rbc,
        "fs_prime_ksc": fs_prime, "comp_steel_yields": comp_yields, "comp_on_top": comp_on_top,
    }


def _fmt_main_bars(rebar) -> str:
    """Format main reinforcement as count×size (e.g. '2DB16 + 1DB10'). NOT '@' (Gemini Q4)."""
    if rebar is None or not rebar.main_bars:
        return "—"
    return " + ".join(f"{n}{name}" for name, n in rebar.main_bars)


# ============================================================================
# Session 3C · EXACT continuous-beam analysis (Three-Moment + point loads)
# Handles UDL + point loads + unequal spans · simple end supports · constant EI.
# Produces continuous V(x), M(x) (for SFD/BMD diagrams) + per-span envelope design.
# Verified: 2 eq spans UDL M=−wL²/8 · 3 eq spans −wL²/10 · 2 eq + central P → M_B=−3PL/16
# Refs: พงฬ์นธี Ch.6 (continuous-beam behaviour/BMD · p.164) · Clapeyron three-moment
# ============================================================================


def _solve_linear(A: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (pure-Python · small systems)."""
    n = len(b)
    if n == 0:
        return []
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            raise CivilCalcError("Three-Moment: ระบบสมการ singular (ตรวจ input ช่วง/โหลด)")
        M[col], M[piv] = M[piv], M[col]
        for r in range(n):
            if r != col:
                f = M[r][col] / M[col][col]
                for c in range(col, n + 1):
                    M[r][c] -= f * M[col][c]
    return [M[i][n] / M[i][i] for i in range(n)]


def _span_load_terms(L: float, w: float, pts: list[tuple[float, float]]) -> tuple[float, float]:
    """6·A·x̄/L of the simple-beam M-diagram, measured from LEFT and from RIGHT support.
    pts = [(P_kN, a_m_from_left), ...]. UDL: wL³/4 both sides.
    Point load P at a (b=L−a): from-left = P·a·b·(L+a)/L · from-right = P·a·b·(L+b)/L."""
    tL = w * L ** 3 / 4.0
    tR = w * L ** 3 / 4.0
    for P, a in pts:
        bb = L - a
        if L > 0:
            tL += P * a * bb * (L + a) / L
            tR += P * a * bb * (L + bb) / L
    return tL, tR


def solve_continuous_moments(Ls, ws, pts_per_span, M0=0.0, Mn=0.0) -> list[float]:
    """Three-Moment with general loads → support moments (kN·m · sagging+).
    Ends default 0 (simple supports); pass M0/Mn for KNOWN end moments from an
    overhang/cantilever (hogging → negative). len(result)=len(Ls)+1.
    Interior supports come out negative (hogging)."""
    n = len(Ls)
    if n == 0:
        return [M0]
    if n == 1:
        return [M0, Mn]
    terms = [_span_load_terms(Ls[i], ws[i], pts_per_span[i]) for i in range(n)]
    nu = n - 1
    A = [[0.0] * nu for _ in range(nu)]
    bvec = [0.0] * nu
    for i in range(1, n):
        r = i - 1
        Ll, Lr = Ls[i - 1], Ls[i]
        A[r][r] = 2.0 * (Ll + Lr)
        # RHS = −(term_from_left of LEFT span + term_from_right of RIGHT span)
        bvec[r] = -(terms[i - 1][0] + terms[i][1])
        if i - 1 >= 1:
            A[r][r - 1] = Ll
        else:
            bvec[r] -= Ll * M0       # known end moment at LEFT end → move to RHS
        if i + 1 <= n - 1:
            A[r][r + 1] = Lr
        else:
            bvec[r] -= Lr * Mn       # known end moment at RIGHT end → move to RHS
    x = _solve_linear(A, bvec)
    return [M0] + x + [Mn]


# kept for backward-compat / tests (UDL-only wrapper)
def solve_three_moment(Ls, ws):
    return solve_continuous_moments(Ls, ws, [[] for _ in Ls])


def _span_VM(L, w, pts, mL, mR, nsamp=40):
    """Sample V(x) and M(x) along one span (UDL w + point loads pts + end moments mL,mR sagging+).
    Returns dict: X[], V[], M[] (kN, kN·m) · V_left · V_right · M_pos(max sag) · x_Mpos · V_absmax."""
    R_L0 = w * L / 2.0 + (sum(P * (L - a) for P, a in pts) / L if L > 0 else 0.0)
    corr = (mR - mL) / L if L > 0 else 0.0

    def V_ss(x):
        return R_L0 - w * x - sum(P for P, a in pts if a < x - FLOAT_TOL)

    def M_ss(x):
        return R_L0 * x - w * x * x / 2.0 - sum(P * (x - a) for P, a in pts if a <= x + FLOAT_TOL)

    xs = {L * k / nsamp for k in range(nsamp + 1)}
    for P, a in pts:                      # capture shear jump at each point load
        xs.add(max(0.0, a - 1e-4)); xs.add(min(L, a + 1e-4)); xs.add(a)
    xs = sorted(xs)
    X, V, M = [], [], []
    for x in xs:
        X.append(x)
        V.append(corr + V_ss(x))
        M.append(mL + (mR - mL) * (x / L if L > 0 else 0) + M_ss(x))
    M_pos = max(M) if M else 0.0
    x_Mpos = X[M.index(M_pos)] if M else 0.0
    return {"X": X, "V": V, "M": M,
            "V_left": corr + V_ss(0.0), "V_right": corr + V_ss(L),
            "M_pos": max(M_pos, 0.0), "x_Mpos": x_Mpos,
            "V_absmax": max((abs(v) for v in V), default=0.0)}


def _cantilever_VM(Lc, w, pts, side, nsamp=24):
    """Sample V(x),M(x) of an overhang (statically determinate · hogging throughout).
    pts = [(Pu_kN, a_m_from_support), ...] · a measured from support toward the free tip.
    side='L' (tip left of support) or 'R'. Returns by distance-from-support s∈[0,Lc]:
    S[], V[] (kN · signed for SFD), M[] (kN·m · ≤0 hogging) + V_face, M_end (at support)."""
    if Lc <= 0:
        return {"S": [], "V": [], "M": [], "V_face": 0.0, "M_end": 0.0}
    pts = pts or []
    sset = {Lc * k / nsamp for k in range(nsamp + 1)}
    for _P, a in pts:
        sset.add(max(0.0, a - 1e-4)); sset.add(min(Lc, a + 1e-4)); sset.add(a)
    ss = sorted(sset)
    sign = -1.0 if str(side).upper().startswith("L") else 1.0
    S, V, M = [], [], []
    for s in ss:
        out_w = w * (Lc - s)                                  # UDL outboard of section
        out_p = sum(P for P, a in pts if a > s - FLOAT_TOL)   # point loads outboard
        Mmag = w * (Lc - s) ** 2 / 2.0 + sum(P * (a - s) for P, a in pts if a > s - FLOAT_TOL)
        S.append(s)
        V.append(sign * (out_w + out_p))
        M.append(-Mmag)                                       # hogging → negative
    V_face = w * Lc + sum(P for P, a in pts)
    M_end = -(w * Lc ** 2 / 2.0 + sum(P * a for P, a in pts))
    return {"S": S, "V": V, "M": M, "V_face": V_face, "M_end": M_end}


def dev_length_top_tension_cm(db_cm: float, fy_ksc: float, fc_ksc: float) -> float:
    """Tension development length Ld (cm) for TOP bars · ว.ส.ท. วิธีกำลัง simplified
    (DRMK ตาราง 8.1 · case-1: spacing≥db + stirrups · ψt=1.3 top-bar effect). Min 30 cm.
    Validated: DRMK Ex 8.2 (DB25 top · f'c=240 · fy=4000) → 159.4 cm."""
    if db_cm <= 0 or fc_ksc <= 0:
        return 30.0
    C = 0.15 if db_cm <= 2.0 + FLOAT_TOL else 0.19   # ≤DB20 : ≥DB25
    psi_t = 1.3                                       # top-bar effect (weaker concrete below)
    ld = C * fy_ksc * psi_t / math.sqrt(fc_ksc) * db_cm
    return max(ld, 30.0)


def _factor_pt(kind: str, P: float, combo: LoadCombo) -> float:
    """Factor a point load magnitude by load combo."""
    if combo == LoadCombo.ACI_LEGACY:
        f = LOAD_FACTOR_DEAD_LEGACY if kind.upper() == "DL" else LOAD_FACTOR_LIVE_LEGACY
    else:
        f = LOAD_FACTOR_DEAD if kind.upper() == "DL" else LOAD_FACTOR_LIVE
    return f * P


def analyze_continuous_beam(inp: ContinuousBeamInput) -> dict:
    """EXACT analysis → support moments + per-span V(x)/M(x) samples + reactions.
    All loads factored. Returns raw analysis (no steel design)."""
    spans = inp.spans
    n = len(spans)
    if n < 2:
        raise ContinuousConditionError("ต้องมีอย่างน้อย 2 ช่วง (คานต่อเนื่อง)")
    Ls, ws, pts = [], [], []
    for i, s in enumerate(spans):
        if s.L <= 0:
            raise InvalidInputError(f"ช่วง {_grid_label(i)}-{_grid_label(i+1)}: ความยาวต้อง > 0")
        if s.DL < 0 or s.LL < 0:
            raise InvalidInputError(f"ช่วง {_grid_label(i)}-{_grid_label(i+1)}: น้ำหนักต้องไม่ติดลบ")
        Ls.append(s.L)
        ws.append(compute_Wu(s.DL, s.LL, inp.load_combo))
        sp_pts = []
        for p in (s.point_loads or []):
            kind = p["kind"] if isinstance(p, dict) else p.kind
            P = p["P"] if isinstance(p, dict) else p.P
            x = p["x"] if isinstance(p, dict) else p.x
            if x < -FLOAT_TOL or x > s.L + FLOAT_TOL:
                raise PointLoadOutOfRangeError(f"ช่วง {_grid_label(i)}-{_grid_label(i+1)}: จุดโหลด x={x} นอกช่วง [0,{s.L}]")
            sp_pts.append((_factor_pt(kind, P, inp.load_combo), max(0.0, min(s.L, x))))
        pts.append(sp_pts)

    # --- optional cantilevers (overhang) → factored loads + known end moments ---
    def _parse_cant(cant, label):
        if not cant:
            return None
        get = ((lambda k, d=0.0: cant.get(k, d)) if isinstance(cant, dict)
               else (lambda k, d=0.0: getattr(cant, k, d)))
        Lc = get("L")
        if not Lc or Lc <= 0:
            raise InvalidInputError(f"คานยื่น{label}: ความยาวต้อง > 0")
        DL, LL = get("DL"), get("LL")
        if DL < 0 or LL < 0:
            raise InvalidInputError(f"คานยื่น{label}: น้ำหนักต้องไม่ติดลบ")
        wc = compute_Wu(DL, LL, inp.load_combo)
        cpts = []
        for p in (get("point_loads", []) or []):
            kind = p["kind"] if isinstance(p, dict) else p.kind
            P = p["P"] if isinstance(p, dict) else p.P
            x = p["x"] if isinstance(p, dict) else p.x
            if x < -FLOAT_TOL or x > Lc + FLOAT_TOL:
                raise PointLoadOutOfRangeError(f"คานยื่น{label}: จุดโหลด x={x} นอกช่วง [0,{Lc}]")
            cpts.append((_factor_pt(kind, P, inp.load_combo), max(0.0, min(Lc, x))))
        return {"L": Lc, "w": wc, "DL": DL, "LL": LL, "pts": cpts}

    cant_L = _parse_cant(inp.left_cantilever, "ซ้าย")
    cant_R = _parse_cant(inp.right_cantilever, "ขวา")
    M0 = _cantilever_VM(cant_L["L"], cant_L["w"], cant_L["pts"], "L")["M_end"] if cant_L else 0.0
    Mn = _cantilever_VM(cant_R["L"], cant_R["w"], cant_R["pts"], "R")["M_end"] if cant_R else 0.0

    Ms = solve_continuous_moments(Ls, ws, pts, M0, Mn)
    vm = [_span_VM(Ls[i], ws[i], pts[i], Ms[i], Ms[i + 1]) for i in range(n)]

    # reactions: R_i = V_left(span i) − V_right(span i−1) · + cantilever total load at ends
    reactions = []
    for sidx in range(n + 1):
        R = 0.0
        if sidx < n:
            R += vm[sidx]["V_left"]
        if sidx > 0:
            R -= vm[sidx - 1]["V_right"]
        reactions.append(R)
    if cant_L:
        reactions[0] += cant_L["w"] * cant_L["L"] + sum(P for P, a in cant_L["pts"])
    if cant_R:
        reactions[n] += cant_R["w"] * cant_R["L"] + sum(P for P, a in cant_R["pts"])

    return {"n": n, "Ls": Ls, "ws": ws, "pts": pts, "Ms": Ms, "vm": vm,
            "reactions": reactions, "cant_L": cant_L, "cant_R": cant_R}


def _design_one_cantilever(cant, side, inp, adj_span_L):
    """Design an overhang: top steel (Mu at support), shear at FACE (no d-reduction · Gemini Q3),
    Ld anchorage into back span, min-depth Lc/8 advisory. Returns display dict + warnings."""
    side_label = "ซ้าย" if str(side).upper().startswith("L") else "ขวา"
    s = _cantilever_VM(cant["L"], cant["w"], cant["pts"], side)
    M_end, V_face = s["M_end"], s["V_face"]
    Mu_top = abs(M_end)                                    # kN·m · TOP steel (hogging)
    top = _safe_flexure_design(Mu_top, inp.b, inp.h, inp.fc, inp.fy,
                               inp.cover, inp.d_stirrup, inp.db_assume, comp_on_top=False)
    d_act = top.get("d_actual") or compute_effective_depth(inp.h, inp.cover, inp.d_stirrup, inp.db_assume)
    try:
        sd = design_shear(Wu_kN_m=cant["w"], L_m=cant["L"], R_A_kN=V_face, R_B_kN=0.0,
                          factored_points=None, b_cm=inp.b, d_cm=d_act, fc_ksc=inp.fc,
                          fyt_ksc=_FYT_STIRRUP_DEFAULT_KSC, phi=PHI_SHEAR,
                          vu_design_override_kN=V_face)
    except SectionTooSmallForShearError as exc:
        sd = {"branch": "FAIL", "passes": False, "error": str(exc),
              "shop_drawing_notation": "หน้าตัดไม่พอ · ต้องขยาย"}

    warnings: list[str] = []
    ld_cm = None
    backspan_short = False
    if top.get("rebar") and top["rebar"].main_bars:
        rebar_table = _load_rebar_table()
        dbs = [next((sz["diameter_cm"] for sz in rebar_table["sizes"] if sz["name"] == nm), inp.db_assume)
               for nm, _c in top["rebar"].main_bars]
        ld_cm = dev_length_top_tension_cm(max(dbs), inp.fy, inp.fc)
        if adj_span_L * 100.0 < ld_cm - FLOAT_TOL:
            backspan_short = True
            warnings.append(f"🔴 ช่วงข้างเคียง ({adj_span_L:.2f} ม.) < Ld ({ld_cm/100:.2f} ม.) — "
                            f"ไม่มีที่พอฝังเหล็กบนคานยื่น{side_label} · ต้องขยายช่วงหรือลด Lc")
    md_factor = (0.4 + inp.fy / 7000.0) if abs(inp.fy - 4000.0) > FLOAT_TOL else 1.0
    h_min = cant["L"] * 100.0 / 8.0 * md_factor
    md_ok = inp.h >= h_min - FLOAT_TOL
    if not md_ok:
        warnings.append(f"🟡 h={inp.h:.0f} ซม. < ขั้นต่ำคานยื่น Lc/8 = {h_min:.1f} ซม. "
                        f"(DRMK ตาราง 3.1) · เสี่ยงแอ่นตัวเกิน")
    if cant["L"] >= 2.0:
        warnings.append(f"ℹ️ คานยื่น{side_label} ยาว {cant['L']:.2f} ม. (≥2 ม.) — "
                        f"ควรตรวจระยะแอ่นจริงถ้ารับผนัง/กระจก/พื้นเปราะ หรือ LL/DL สูง")
    if adj_span_L > 0 and cant["L"] / adj_span_L > 0.5:
        warnings.append(f"🟡 Lc/ช่วงข้างเคียง = {cant['L']/adj_span_L:.2f} > 0.5 — "
                        f"เสี่ยงแรงถอน (uplift) + ที่ฝังเหล็กไม่พอ · ตรวจละเอียด")
    return {
        "side": ("L" if str(side).upper().startswith("L") else "R"), "side_label": side_label,
        "L": cant["L"], "wu_kNm": cant["w"], "wu_ton_m": round(cant["w"] * KN_TO_TON, 3),
        "n_points": len(cant["pts"]),
        "Mu_tonm": round(Mu_top * KNM_TO_TONM, 3), "M_end_tonm": round(M_end * KNM_TO_TONM, 3),
        "Vu_face_ton": round(V_face * KN_TO_TON, 3),
        "top": top, "top_bars": _fmt_main_bars(top.get("rebar")), "shear": sd,
        "is_doubly": bool(top.get("is_doubly")),
        "comp_bars": _fmt_main_bars(top.get("rebar_compression")) if top.get("is_doubly") else "—",
        "Ld_cm": (round(ld_cm, 1) if ld_cm else None),
        "Ld_note": (f"เหล็กบนต่อเนื่องเข้าช่วงข้างเคียง ≥ Ld = {ld_cm/100:.2f} ม. (วัดจากหน้าเสา) · งอฉาก 90° ปลาย 12db"
                    if ld_cm else None),
        "h_min_cm": round(h_min, 1), "min_depth_ok": md_ok,
        "warnings": warnings,
        "passes": bool(top.get("passes")) and bool(sd.get("passes")) and not backspan_short,
    }


def compute_curtailment(spans: list, supports: list, Ls: list,
                        h_cm: float, cover_cm: float, d_stirrup_cm: float,
                        db_default_cm: float, point_loads_per_span: list = None) -> dict:
    """ระยะหยุดเหล็กตามมาตรฐาน รูปที่ 8.32 (มงคล C8 Bond · p215) + extension check.

    New module · อ่าน output ที่ design เสร็จแล้ว (spans/supports) → คืนจุดตัดจริงต่อ bar group
    ไม่แตะ flexure/shear core (zero-regression by construction · parity-safe).
    ระยะหน่วย ม. · top วัดจากหน้าเสา · bottom L/8 วัดจากศูนย์กลางเสา.
    ที่มา: [[Formula - Bar Curtailment & Cutoff Positions (RC-SDM)]] · ALL_SDM_BasicBOOK_DRMK บท 8.
    """
    n = len(Ls)

    def _db_from(elem):  # ขนาดเหล็กใหญ่สุด (ซม.) · "DB25" → 2.5
        rb = elem.get("rebar") if elem else None
        if rb and getattr(rb, "main_bars", None):
            dias = []
            for name, _c in rb.main_bars:
                digits = "".join(ch for ch in str(name) if ch.isdigit())
                if digits:
                    dias.append(int(digits) / 10.0)
            if dias:
                return max(dias)
        return db_default_cm

    def _d_from(elem):
        if elem and elem.get("d_actual"):
            return elem["d_actual"]
        return compute_effective_depth(h_cm, cover_cm, d_stirrup_cm, db_default_cm)

    top_out = []
    for s in supports:
        # รวมทุก support ที่มีเหล็กบน · interior = 2 ข้าง · exterior+คานยื่น = 1 ข้าง (ช่วงใน)
        #   support ปลายแบบธรรมดา (ไม่มีคานยื่น) M_neg=0 → top=None → ถูกข้ามเอง (Codex P2)
        if not s.get("top") or not s["top"].get("rebar"):
            continue
        idx = ord(s["label"]) - ord("A")
        adj = []
        if idx - 1 >= 0:
            adj.append(Ls[idx - 1])
        if idx < n:
            adj.append(Ls[idx])
        if not adj:                                 # ไม่มีช่วงข้างเคียง (ไม่ควรเกิด) → ข้าม
            continue
        is_ext = (idx == 0 or idx == n)             # exterior + มี top = ฝั่งนอกเป็นคานยื่น
        d_cm, db_cm = _d_from(s["top"]), _db_from(s["top"])
        Ln = max(adj)                               # clear span ≈ span (engine ไม่โมเดลกว้างเสา · conservative)
        ext = max(d_cm / 100.0, 12.0 * db_cm / 100.0, Ln / 16.0)   # ม. · เลยจุดดัดกลับ (บน)
        cut_half = max(adj) / 4.0                   # ครึ่งบน ยื่น L/4 (เข้าช่วงใน)
        cut_third = max(max(adj) / 3.0, cut_half + ext)            # ≥1/3 ยื่น L/3 + ต้องเลยจุดดัดกลับ
        top_out.append({
            "support": s["label"], "exterior_cantilever": is_ext,
            "L_left_m": round(Ls[idx - 1], 3) if idx - 1 >= 0 else None,
            "L_right_m": round(Ls[idx], 3) if idx < n else None,
            "cut_half_m": round(cut_half, 3), "cut_third_m": round(cut_third, 3),
            "ext_min_m": round(ext, 3),
            "note": (f"เหล็กบน {s.get('top_bars', '')}: ครึ่งหนึ่งยื่น L/4={cut_half:.2f} ม. · "
                     f"≥1/3 ยื่น {cut_third:.2f} ม. (เลยจุดดัดกลับ ≥{ext:.2f}) · วัดจากหน้าเสา"
                     + (" เข้าช่วงใน · ฝั่งคานยื่นเหล็กบนวิ่งเต็ม + Ld (ดู cantilevers)" if is_ext else "")),
        })

    bot_out = []
    for sp in spans:
        if not sp.get("bottom") or not sp["bottom"].get("rebar"):
            continue
        L = sp["L"]
        d_cm, db_cm = _d_from(sp["bottom"]), _db_from(sp["bottom"])
        ext = max(d_cm / 100.0, 12.0 * db_cm / 100.0)              # ม. · เลยจุดดัดกลับ (ล่าง)
        bot_out.append({
            "span": sp["label"], "L_m": round(L, 3),
            "cut_eighth_m": round(L / 8.0, 3), "into_support_m": 0.15,
            "ext_min_m": round(ext, 3),
            "note": (f"เหล็กล่าง {sp.get('bottom_bars', '')}: ครึ่งหนึ่งตัดที่ L/8={L / 8.0:.2f} ม.(จากศูนย์เสา) · "
                     f"≥1/4 ยื่นเข้าเสา 0.15 ม. · เลยจุดดัดกลับ ≥{ext:.2f} ม."),
        })

    # เงื่อนไขใช้ได้ของ รูปที่ 8.32: UDL + ช่วงใกล้เคียงกัน (DRMK p215) · นอกเงื่อนไข = flag (Codex P2)
    #   จุดโหลด/ช่วงไม่เท่า → จุดดัดกลับเลื่อนจาก UDL · ค่า L/4·L/8 เป็นค่าประมาณ ต้องตรวจ envelope จริง
    warns = []
    if any(len(p or []) > 0 for p in (point_loads_per_span or [])):
        warns.append("⚠️ มีจุดโหลด → จุดดัดกลับเลื่อนจาก UDL · ค่าตัด รูปที่ 8.32 เป็นค่าประมาณ · "
                     "วิศวกรต้องตรวจจุดหยุดเหล็กจาก moment envelope จริง")
    if len(Ls) >= 2 and min(Ls) > 0 and (max(Ls) / min(Ls)) > 1.5:
        warns.append(f"⚠️ ช่วงไม่ใกล้เคียงกัน (ยาวสุด/สั้นสุด = {max(Ls) / min(Ls):.2f} > 1.5) → "
                     f"รูปที่ 8.32 ใช้กับช่วงใกล้เท่า · ตรวจจุดดัดกลับจริง")
    applicable = not warns

    return {
        "method": "มาตรฐานหยุดเหล็ก รูปที่ 8.32 (มงคล C8 Bond) · ช่วงใกล้เท่า + UDL",
        "datum": "ระยะ ม. · เหล็กบนวัดจากหน้าเสา · เหล็กล่าง L/8 วัดจากศูนย์กลางเสา",
        "applicable": applicable,   # True = เข้าเงื่อนไข รูปที่ 8.32 (UDL + ช่วงใกล้เท่า) · False = ดู warnings
        "warnings": warns,
        "top": top_out, "bottom": bot_out,
        "citations": [
            "หยุดเหล็กบน: ครึ่งยื่น L/4 · ≥1/3 ยื่น max(L₁/3,L₂/3) (มงคล รูปที่ 8.32)",
            "หยุดเหล็กล่าง: ครึ่งตัดที่ L/8 · ≥1/4 ยื่นเข้าเสา 15 ซม. (มงคล รูปที่ 8.32)",
            "ยื่นเลยจุดดัดกลับ ≥ max(d, 12db) ล่าง · max(d, 12db, Ln/16) บน (ว.ส.ท./ACI · มงคล C8 หน้า 210-215)",
        ],
    }


def compute_curtailment_single(rebar, L_m: float, d_cm: float, db_default_cm: float,
                               point_loads: list = None, partial_udls: list = None) -> dict:
    """ระยะหยุดเหล็กล่าง คานช่วงเดียว (simply-supported · DRMK รูป 8.23 + มาตรฐาน).

    เหล็กล่าง (+M): ครึ่งตัดที่ L/8 จากเสา · ≥1/4 วิ่งเข้า support (ACI คานช่วงเดียว) ·
    ยกเว้นที่จุดรองรับช่วงเดียว ไม่ต้องยื่นเลย d (ext ใช้เฉพาะจุดตัดในช่วง).
    คานช่วงเดียวไม่มีเหล็กบนรับแรง (top=[]). New module · ไม่แตะ flexure core.
    ที่มา: [[Formula - Bar Curtailment & Cutoff Positions (RC-SDM)]] · DRMK บท 8 รูป 8.23.
    """
    if not rebar or not getattr(rebar, "main_bars", None):
        return None
    dias = []
    for name, _c in rebar.main_bars:
        digits = "".join(ch for ch in str(name) if ch.isdigit())
        if digits:
            dias.append(int(digits) / 10.0)
    db_cm = max(dias) if dias else db_default_cm
    ext = max(d_cm / 100.0, 12.0 * db_cm / 100.0)   # ม. · ที่จุดตัดในช่วง (ไม่ใช่ที่ support · ยกเว้น)
    warns = []
    if (point_loads and len(point_loads) > 0) or (partial_udls and len(partial_udls) > 0):
        warns.append("⚠️ มีจุดโหลด/น้ำหนักแผ่บางช่วง → จุดตัดเลื่อนจาก UDL เต็มช่วง · ค่าตัดเป็นค่าประมาณ · "
                     "วิศวกรต้องตรวจจุดหยุดเหล็กจาก moment envelope จริง")
    # เลือกเส้นที่ตัดที่ L/8 — เส้นเล็กสุดก่อน + คุม 3 เงื่อนไข (Codex P1+P2):
    #   (1) เก็บ ≥2 มุมวิ่งเต็ม (convention)  (2) ตัด ≤ ครึ่ง (count · รูป 8.32)
    #   (3) remaining As ≥ 7/16 = 43.75% ของ total As (M ที่ L/8 · mixed-size ต้องคิดพื้นที่ ไม่ใช่จำนวน)
    def _bar_area(nm):
        digits = "".join(ch for ch in str(nm) if ch.isdigit())
        dbq = (int(digits) / 10.0) if digits else db_default_cm
        return math.pi / 4.0 * dbq * dbq
    bars = [(_bar_area(nm), nm) for nm, cnt in rebar.main_bars for _ in range(cnt)]
    n_total = len(bars)
    total_As = sum(a for a, _ in bars) or 1.0
    MIN_FRAC = 7.0 / 16.0                                        # 0.4375 · M ที่ L/8 (UDL)
    cut_idx, rem_As, rem_cnt = [], total_As, n_total
    for i in sorted(range(n_total), key=lambda j: bars[j][0]):   # เส้นเล็กสุดก่อน
        if rem_cnt - 1 < 2:                                      # เก็บ ≥2 มุม
            break
        if len(cut_idx) + 1 > n_total // 2:                      # ตัด ≤ ครึ่ง (count)
            break
        if rem_As - bars[i][0] < MIN_FRAC * total_As - 1e-9:     # remaining As ≥ 43.75%
            break
        cut_idx.append(i); rem_As -= bars[i][0]; rem_cnt -= 1
    n_extra, n_cont = len(cut_idx), n_total - len(cut_idx)
    _cs = {}
    for i in cut_idx:
        _cs[bars[i][1]] = _cs.get(bars[i][1], 0) + 1
    cut_str = " + ".join(f"{c}-{nm}" for nm, c in _cs.items())   # เบอร์ที่ตัด (เล็กสุด)
    if n_extra > 0:
        bot = {
            "span": "กลางช่วง", "L_m": round(L_m, 3), "n_continuous_past_L8": n_cont, "n_extra_cut": n_extra,
            "cut_bars": cut_str, "cut_eighth_m": round(L_m / 8.0, 3), "into_support_m": 0.15, "ext_min_m": round(ext, 3),
            "note": (f"ต่อเนื่องผ่าน L/8 {n_cont} เส้น (As ≥43.75% · M ที่ L/8) · "
                     f"ตัด {cut_str} (เบอร์เล็กสุด) ที่ L/8={L_m / 8.0:.2f} ม.(จากศูนย์เสา) · เลยจุดตัด ≥{ext:.2f} ม. (support ยกเว้น)"),
        }
    else:
        bot = {
            "span": "กลางช่วง", "L_m": round(L_m, 3), "n_continuous_past_L8": n_total, "n_extra_cut": 0,
            "cut_bars": "", "cut_eighth_m": None, "into_support_m": 0.15, "ext_min_m": round(ext, 3),
            "note": f"เหล็ก {n_total} เส้นวิ่งเต็มช่วง · ไม่ตัด (ตัดแล้ว As < 43.75% · M ที่ L/8)",
        }
    return {
        "method": "ระยะหยุดเหล็กล่าง คานช่วงเดียว (DRMK รูป 8.23 · simply-supported)",
        "datum": "ระยะ ม. · เหล็กล่าง L/8 วัดจากศูนย์กลางเสา · ที่ support ไม่ต้องยื่น d (ยกเว้นช่วงเดียว)",
        "applicable": not warns, "warnings": warns,
        "top": [],   # คานช่วงเดียวไม่มีเหล็กบนรับแรง
        "bottom": [bot],
        "citations": [
            "เหล็กหลัก 2 เส้นวิ่งเต็ม · เสริมตัดที่ L/8 · ≥1/4 +As เข้า support (มาตรฐาน · DRMK รูป 8.23)",
            "ยื่นเลยจุดตัด ≥ max(d, 12db) · ยกเว้นที่จุดรองรับช่วงเดียว (DRMK C8 หน้า 210)",
        ],
    }


def _find_moment_crossing(x_grid: list, m_grid: list, target: float, x_peak: float, direction: int):
    """หา x (ม.) ที่ M(x) = target โดยเดินจากจุด peak ไปทาง direction (-1 ซ้าย / +1 ขวา).
    Linear-interp ระหว่าง sample (ตำแหน่งจริง ไม่ใช่จุดใกล้สุด · Fix-2).
    คืน None ถ้า M ≥ target ตลอดทาง (เหล็กที่เหลือไม่พอ → cut bar ต้องวิ่งถึง support)."""
    n = len(x_grid)
    if n < 2:
        return None
    pk = min(range(n), key=lambda i: abs(x_grid[i] - x_peak))
    seq = list(range(pk, -1, -1)) if direction < 0 else list(range(pk, n))
    for a, b in zip(seq, seq[1:]):
        m0, m1 = m_grid[a], m_grid[b]
        if (m0 - target) * (m1 - target) <= 0.0 and abs(m0 - m1) > 1e-9:   # M ลดผ่าน target
            t = (m0 - target) / (m0 - m1)
            return x_grid[a] + t * (x_grid[b] - x_grid[a])
    return None


def compute_curtailment_single_envelope(rebar, L_m: float, d_cm: float, db_default_cm: float,
                                        fy_ksc: float, fc_ksc: float, b_cm: float, phi: float,
                                        m_grid: list, x_grid: list) -> dict:
    """ระยะหยุดเหล็กล่างคานช่วงเดียว จาก moment envelope จริง (เคสจุดโหลด/partial UDL · applicable=false ของ fig 8.23).

    Theoretical cutoff (ACI 12.10.3 · DRMK C8 §1): x ที่ Mu(x) = φMn ของเหล็กที่เหลือ → ยื่นเลย ≥ max(d,12db).
    เลือกเหล็กตัดแบบเดียวกับ fig 8.23 (เล็กก่อน · เก็บ≥2มุม · ≤ครึ่ง · As เหลือ≥43.75%) แต่ **ตำแหน่งจาก envelope จริง**
    (ไม่ใช่ L/8 ค่าประมาณ) → คืน cut_left_m/cut_right_m (asymmetric) + cut_eighth_m เฉลี่ย (fallback display เดิม) · applicable=True.
    New module · ไม่แตะ flexure/compute_curtailment_single เดิม. ที่มา: [[Formula - Bar Curtailment & Cutoff Positions (RC-SDM)]] §1-2.
    """
    if not rebar or not getattr(rebar, "main_bars", None) or not m_grid or not x_grid:
        return None

    def _bar_area(nm):
        digits = "".join(ch for ch in str(nm) if ch.isdigit())
        dbq = (int(digits) / 10.0) if digits else db_default_cm
        return math.pi / 4.0 * dbq * dbq

    dias = []
    for name, _c in rebar.main_bars:
        digits = "".join(ch for ch in str(name) if ch.isdigit())
        if digits:
            dias.append(int(digits) / 10.0)
    db_cm = max(dias) if dias else db_default_cm
    ext = max(d_cm / 100.0, 12.0 * db_cm / 100.0)   # ม. · ยื่นเลย theoretical cutoff

    bars = [(_bar_area(nm), nm) for nm, cnt in rebar.main_bars for _ in range(cnt)]
    n_total = len(bars)
    total_As = sum(a for a, _ in bars) or 1.0
    MIN_FRAC = 7.0 / 16.0
    cut_idx, rem_As, rem_cnt = [], total_As, n_total
    for i in sorted(range(n_total), key=lambda j: bars[j][0]):   # เล็กสุดก่อน
        if rem_cnt - 1 < 2:                                      # เก็บ ≥2 มุม
            break
        if len(cut_idx) + 1 > n_total // 2:                      # ตัด ≤ ครึ่ง
            break
        if rem_As - bars[i][0] < MIN_FRAC * total_As - 1e-9:     # As เหลือ ≥ 43.75%
            break
        cut_idx.append(i); rem_As -= bars[i][0]; rem_cnt -= 1
    n_extra, n_cont = len(cut_idx), n_total - len(cut_idx)
    _cs = {}
    for i in cut_idx:
        _cs[bars[i][1]] = _cs.get(bars[i][1], 0) + 1
    cut_str = " + ".join(f"{c}-{nm}" for nm, c in _cs.items())

    if n_extra == 0:
        bot = {"span": "กลางช่วง", "L_m": round(L_m, 3), "n_continuous_past_L8": n_total, "n_extra_cut": 0,
               "cut_bars": "", "cut_eighth_m": None, "cut_left_m": None, "cut_right_m": None,
               "into_support_m": 0.15, "ext_min_m": round(ext, 3),
               "note": f"เหล็ก {n_total} เส้นวิ่งเต็มช่วง · ไม่ตัด (ตัดแล้ว As < 43.75%)"}
    else:
        # ตำแหน่งตัดจริง: x ที่ Mu(x) = φMn ของเหล็กที่เหลือ (parity · ใช้ compute_Mn เดียวกับ engine)
        a_rem = compute_stress_block_depth(rem_As, fy_ksc, fc_ksc, b_cm)
        phiMn_rem = phi * compute_Mn(rem_As, fy_ksc, d_cm, a_rem) / 10197.0   # kN·m (หน่วยเดียวกับ m_grid)
        m_peak = max(m_grid)
        x_peak = x_grid[m_grid.index(m_peak)]
        xL = _find_moment_crossing(x_grid, m_grid, phiMn_rem, x_peak, -1)
        xR = _find_moment_crossing(x_grid, m_grid, phiMn_rem, x_peak, +1)
        aL = max(0.0, xL - ext) if xL is not None else 0.0            # ปลายซ้าย (ยื่นเลย cutoff ไปทาง support)
        bR = min(L_m, xR + ext) if xR is not None else L_m            # ปลายขวา
        cut_left_m = round(aL, 3)
        cut_right_m = round(max(0.0, L_m - bR), 3)
        bot = {"span": "กลางช่วง", "L_m": round(L_m, 3), "n_continuous_past_L8": n_cont, "n_extra_cut": n_extra,
               "cut_bars": cut_str, "cut_left_m": cut_left_m, "cut_right_m": cut_right_m,
               "cut_eighth_m": round((cut_left_m + cut_right_m) / 2.0, 3),   # เฉลี่ย · fallback display เดิมที่อ่าน symmetric
               "into_support_m": 0.15, "ext_min_m": round(ext, 3),
               "note": (f"ต่อเนื่อง {n_cont} เส้น · ตัด {cut_str} จาก moment envelope จริง: "
                        f"ปลายซ้ายห่าง support {cut_left_m:.2f} ม. · ปลายขวา {cut_right_m:.2f} ม. (เลย theoretical cutoff ≥{ext:.2f})")}
    return {
        "method": "ระยะหยุดเหล็กล่าง จาก moment envelope จริง (theoretical cutoff · ACI 12.10.3)",
        "datum": "ระยะ ม. · วัดจากศูนย์เสาแต่ละข้าง · ปลายเหล็กตัดยื่นเลย theoretical cutoff ≥ max(d,12db)",
        "applicable": True, "warnings": [],   # คำนวณจริงจาก envelope = exact (ไม่ใช่ค่าประมาณ · Fix-5)
        "top": [], "bottom": [bot],
        "citations": [
            "จุดตัดทฤษฎี: M(x) = φMn ของเหล็กที่เหลือ · ยื่นเลย ≥ max(d,12db) (ACI 12.10.3 · มงคล C8)",
            "เลือกเหล็กตัด: เล็กก่อน · เก็บ≥2มุม · ≤ครึ่ง · As เหลือ≥43.75% (DRMK รูป 8.23)",
        ],
    }


def compute_curtailment_continuous_envelope(spans_out: list, supports_out: list, vm: list,
                                            h_cm: float, cover_cm: float, d_stirrup_cm: float,
                                            db_default_cm: float, fy_ksc: float, fc_ksc: float,
                                            b_cm: float, phi: float) -> dict:
    """ระยะหยุดเหล็กล่าง (+M · A2a) + เหล็กบน (−M · A2b) คานต่อเนื่อง จาก moment envelope จริง ต่อช่วง/หัวเสา.
    (พี่น้อง continuous ของ compute_curtailment_single_envelope). เคสมีจุดโหลด ที่ fig 8.32 เป็นค่าประมาณ.

    bottom (+M) ต่อช่วง i: vm[i] (M(x)/X · kN·m sagging+) หา x ที่ Mu(x)=φMn ของเหล็กที่เหลือ → cut_left_m/cut_right_m asymmetric.
    top (−M · A2b) ต่อ interior support: **sign กลับ** (target = −φMn ของเหล็กบนที่เก็บ) · walk จาก support node
      เข้าช่วงซ้าย (vm[idx-1] x=L) + ขวา (vm[idx] x=0) → cut_half (cut group · M=−φMn_kept) + cut_third (inflection M=0) + ext.
      ยื่นเลย ≥ max(d,12db,Ln/16) (§3) · เลือกตัด ≤ครึ่ง·เก็บ≥2 (≥1/3 เหลือ §3 · ไม่ใช้ 43.75% bottom-specific).
    New module · ไม่แตะ flexure/compute_curtailment* เดิม (zero-reg by construction · parity: compute_Mn ÷10197 เดียวกับ engine).
    ที่มา: [[Formula - Bar Curtailment & Cutoff Positions (RC-SDM)]] §1-4 · ACI 12.10.3.
    """
    if not spans_out or not vm:
        return None
    n_spans = len(spans_out)

    def _bar_area(nm):
        digits = "".join(ch for ch in str(nm) if ch.isdigit())
        dbq = (int(digits) / 10.0) if digits else db_default_cm
        return math.pi / 4.0 * dbq * dbq

    bot_out = []
    for i, sp in enumerate(spans_out):
        if i >= len(vm):
            break
        bottom = sp.get("bottom") if sp else None
        rebar = bottom.get("rebar") if bottom else None
        if not rebar or not getattr(rebar, "main_bars", None):
            continue
        L = sp["L"]
        m_grid, x_grid = vm[i].get("M") or [], vm[i].get("X") or []
        d_cm = bottom.get("d_actual") or compute_effective_depth(h_cm, cover_cm, d_stirrup_cm, db_default_cm)
        dias = []
        for name, _c in rebar.main_bars:
            digits = "".join(ch for ch in str(name) if ch.isdigit())
            if digits:
                dias.append(int(digits) / 10.0)
        db_cm = max(dias) if dias else db_default_cm
        ext = max(d_cm / 100.0, 12.0 * db_cm / 100.0)   # ม. · ยื่นเลย theoretical cutoff

        bars = [(_bar_area(nm), nm) for nm, cnt in rebar.main_bars for _ in range(cnt)]
        n_total = len(bars)
        total_As = sum(a for a, _ in bars) or 1.0
        MIN_FRAC = 7.0 / 16.0
        cut_idx, rem_As, rem_cnt = [], total_As, n_total
        for j in sorted(range(n_total), key=lambda k: bars[k][0]):   # เล็กสุดก่อน
            if rem_cnt - 1 < 2:                                      # เก็บ ≥2 มุม
                break
            if len(cut_idx) + 1 > n_total // 2:                     # ตัด ≤ ครึ่ง
                break
            if rem_As - bars[j][0] < MIN_FRAC * total_As - 1e-9:    # As เหลือ ≥ 43.75%
                break
            cut_idx.append(j); rem_As -= bars[j][0]; rem_cnt -= 1
        n_extra, n_cont = len(cut_idx), n_total - len(cut_idx)
        _cs = {}
        for j in cut_idx:
            _cs[bars[j][1]] = _cs.get(bars[j][1], 0) + 1
        cut_str = " + ".join(f"{c}-{nm}" for nm, c in _cs.items())

        if n_extra == 0 or not m_grid or not x_grid:
            bot_out.append({
                "span": sp["label"], "L_m": round(L, 3),
                "n_continuous_past_L8": n_total, "n_extra_cut": 0, "cut_bars": "",
                "cut_eighth_m": None, "cut_left_m": None, "cut_right_m": None,
                "into_support_m": 0.15, "ext_min_m": round(ext, 3),
                "note": f"เหล็ก {n_total} เส้นวิ่งเต็มช่วง · ไม่ตัด (ตัดแล้ว As < 43.75%)"})
            continue
        # ตำแหน่งตัดจริง: x ที่ Mu(x) = φMn ของเหล็กที่เหลือ (parity · compute_Mn เดียวกับ engine · kN·m)
        a_rem = compute_stress_block_depth(rem_As, fy_ksc, fc_ksc, b_cm)
        phiMn_rem = phi * compute_Mn(rem_As, fy_ksc, d_cm, a_rem) / 10197.0   # kN·m (หน่วยเดียวกับ vm.M)
        m_peak = max(m_grid)
        x_peak = x_grid[m_grid.index(m_peak)]
        xL = _find_moment_crossing(x_grid, m_grid, phiMn_rem, x_peak, -1)
        xR = _find_moment_crossing(x_grid, m_grid, phiMn_rem, x_peak, +1)
        if xL is None and xR is None:                                 # เหล็กที่เหลือไม่พอตลอดช่วง → ตัดไม่ได้ · วิ่งเต็ม (conservative)
            bot_out.append({
                "span": sp["label"], "L_m": round(L, 3),
                "n_continuous_past_L8": n_total, "n_extra_cut": 0, "cut_bars": "",
                "cut_eighth_m": None, "cut_left_m": None, "cut_right_m": None,
                "into_support_m": 0.15, "ext_min_m": round(ext, 3),
                "note": f"เหล็ก {n_total} เส้นวิ่งเต็มช่วง · ไม่ตัด (เหล็กที่เหลือไม่พอตลอดช่วงจาก envelope)"})
            continue
        aL = max(0.0, xL - ext) if xL is not None else 0.0            # ปลายซ้าย (ยื่นเลย cutoff ไปทาง support)
        bR = min(L, xR + ext) if xR is not None else L                # ปลายขวา
        cut_left_m = round(aL, 3)
        cut_right_m = round(max(0.0, L - bR), 3)
        bot_out.append({
            "span": sp["label"], "L_m": round(L, 3),
            "n_continuous_past_L8": n_cont, "n_extra_cut": n_extra, "cut_bars": cut_str,
            "cut_left_m": cut_left_m, "cut_right_m": cut_right_m,
            "cut_eighth_m": round((cut_left_m + cut_right_m) / 2.0, 3),   # เฉลี่ย · fallback display เดิมที่อ่าน symmetric
            "into_support_m": 0.15, "ext_min_m": round(ext, 3),
            "note": (f"ต่อเนื่อง {n_cont} เส้น · ตัด {cut_str} จาก moment envelope จริง: "
                     f"ปลายซ้ายห่าง support {cut_left_m:.2f} ม. · ปลายขวา {cut_right_m:.2f} ม. (เลย theoretical cutoff ≥{ext:.2f})")})

    # --- A2b: เหล็กบน (−M hogging) จาก envelope จริง ต่อ interior support · sign กลับ (target = −φMn_kept) ---
    top_out = []
    for s in (supports_out or []):
        if not s.get("top") or not s["top"].get("rebar"):
            continue
        rebar_t = s["top"]["rebar"]
        if not getattr(rebar_t, "main_bars", None):
            continue
        idx = ord(s["label"]) - ord("A")
        # A2b: envelope เฉพาะ interior support (2 ข้างเป็น main span จริง) · exterior+คานยื่น top คง fig-8.32
        #   เพราะ top คานยื่น = วิ่งเต็ม+Ld (determinate · ไม่ใช่ envelope crossing) → ฝั่งนอกไม่ได้ envelope-check (Codex P2)
        if idx == 0 or idx == n_spans:
            continue
        has_left = (idx - 1 >= 0) and (idx - 1 < n_spans)    # span ซ้าย = idx-1
        has_right = idx < n_spans                            # span ขวา = idx
        if not (has_left and has_right):                     # interior ต้องมีครบ 2 ข้าง
            continue
        is_ext = False
        d_t = s["top"].get("d_actual") or compute_effective_depth(h_cm, cover_cm, d_stirrup_cm, db_default_cm)
        dias_t = []
        for name, _c in rebar_t.main_bars:
            digits = "".join(ch for ch in str(name) if ch.isdigit())
            if digits:
                dias_t.append(int(digits) / 10.0)
        db_t = max(dias_t) if dias_t else db_default_cm
        Ln = max([spans_out[idx - 1]["L"] if has_left else 0.0, spans_out[idx]["L"] if has_right else 0.0])
        ext_t = max(d_t / 100.0, 12.0 * db_t / 100.0, Ln / 16.0)   # บน: +Ln/16 (§3)
        # เลือกตัด: เก็บ ≥2 มุม · ตัด ≤ ครึ่ง (เหลือ ≥1/3 ยื่นเลยจุดดัดกลับ §3 · ไม่ใช้ 43.75% = bottom-specific)
        bars_t = [(_bar_area(nm), nm) for nm, cnt in rebar_t.main_bars for _ in range(cnt)]
        nt = len(bars_t)
        cut_t, remc_t = [], nt
        for j in sorted(range(nt), key=lambda k: bars_t[k][0]):
            if remc_t - 1 < 2:
                break
            if len(cut_t) + 1 > nt // 2:
                break
            cut_t.append(j); remc_t -= 1
        rem_As_t = sum(bars_t[j][0] for j in range(nt) if j not in cut_t) or 1.0
        _cst = {}
        for j in cut_t:
            _cst[bars_t[j][1]] = _cst.get(bars_t[j][1], 0) + 1
        cut_str_t = " + ".join(f"{c}-{nm}" for nm, c in _cst.items())
        a_kept = compute_stress_block_depth(rem_As_t, fy_ksc, fc_ksc, b_cm)
        phiMn_kept = phi * compute_Mn(rem_As_t, fy_ksc, d_t, a_kept) / 10197.0   # kN·m (บวก · target hogging = −ค่านี้)

        def _top_side(span_i, x_peak, direction):
            """คืน (cut_half_m, cut_third_m) ระยะจาก support (centerline) เข้าช่วง span_i.
            cut_half = cut group (M=−φMn_kept)+ext · cut_third = inflection (M=0)+ext · None→วิ่งเต็มช่วง."""
            mg, xg = vm[span_i].get("M") or [], vm[span_i].get("X") or []
            Lsp = spans_out[span_i]["L"]
            if not mg or not xg:
                return None, round(Lsp, 3)
            xc_half = _find_moment_crossing(xg, mg, -phiMn_kept, x_peak, direction)
            xc_infl = _find_moment_crossing(xg, mg, 0.0, x_peak, direction)
            ch = (abs(x_peak - xc_half) + ext_t) if (xc_half is not None and len(cut_t) > 0) else None
            ct = (abs(x_peak - xc_infl) + ext_t) if xc_infl is not None else Lsp   # ไม่มี inflection → วิ่งเต็มช่วง (conservative)
            ch = round(min(ch, Lsp), 3) if ch is not None else None
            ct = round(min(ct, Lsp), 3)
            return ch, ct

        cut_half_L = cut_third_L = cut_half_R = cut_third_R = None
        if has_left:
            cut_half_L, cut_third_L = _top_side(idx - 1, spans_out[idx - 1]["L"], -1)   # x_peak = ปลายขวาของช่วง idx-1 = หัวเสานี้
        if has_right:
            cut_half_R, cut_third_R = _top_side(idx, 0.0, +1)                            # x_peak = ปลายซ้ายของช่วง idx
        _gov = max([v for v in (cut_third_L, cut_third_R) if v is not None], default=0.0)
        top_out.append({
            "support": s["label"], "exterior_cantilever": is_ext, "envelope": True,
            "L_left_m": round(spans_out[idx - 1]["L"], 3) if has_left else None,
            "L_right_m": round(spans_out[idx]["L"], 3) if has_right else None,
            "cut_half_left_m": cut_half_L, "cut_third_left_m": cut_third_L,
            "cut_half_right_m": cut_half_R, "cut_third_right_m": cut_third_R,
            "n_cut": len(cut_t), "cut_bars": cut_str_t, "ext_min_m": round(ext_t, 3),
            # คงคีย์เดิมเป็น fallback (เผื่อ consumer อ่าน cut_half_m/cut_third_m เก่า) = ฝั่งที่ยื่นไกลสุด
            "cut_half_m": max([v for v in (cut_half_L, cut_half_R) if v is not None], default=None),
            "cut_third_m": round(_gov, 3),
            "note": (f"เหล็กบน {s.get('top_bars', '')}: ตัด {cut_str_t or '—'} จาก −M envelope จริง · "
                     f"ยื่นจากหน้าเสา ซ้าย(ตัด {cut_half_L}/เก็บถึง {cut_third_L}) · ขวา({cut_half_R}/{cut_third_R}) ม. "
                     f"(เลยจุดดัดกลับ ≥{ext_t:.2f})" + (" · ฝั่งคานยื่นวิ่งเต็ม+Ld" if is_ext else "")),
        })

    if not bot_out and not top_out:
        return None
    return {
        "method": "ระยะหยุดเหล็ก คานต่อเนื่อง จาก moment envelope จริง (theoretical cutoff · ACI 12.10.3)",
        "bottom": bot_out, "top": top_out,
        "citations": [
            "จุดตัดทฤษฎี: M(x) = φMn ของเหล็กที่เหลือ ต่อช่วง/หัวเสา · ยื่นเลย ≥ max(d,12db[,Ln/16] บน) (ACI 12.10.3 · มงคล C8)",
            "เหล็กล่าง: เก็บ≥2มุม·≤ครึ่ง·As≥43.75% (รูป 8.23) · เหล็กบน: ≤ครึ่ง·เหลือ≥1/3 ยื่นเลยจุดดัดกลับ (§3)",
        ],
    }


def design_continuous_beam_exact(inp: ContinuousBeamInput) -> dict:
    """EXACT continuous-beam design (Three-Moment + point loads + cantilevers). Returns design + diagram data."""
    az = analyze_continuous_beam(inp)
    n, Ls, ws, pts, Ms, vm = az["n"], az["Ls"], az["ws"], az["pts"], az["Ms"], az["vm"]
    cant_L, cant_R = az["cant_L"], az["cant_R"]

    spans_out = []
    for i in range(n):
        M_pos = vm[i]["M_pos"]
        Vu = vm[i]["V_absmax"]
        bottom = _safe_flexure_design(
            M_pos, inp.b, inp.h, inp.fc, inp.fy, inp.cover, inp.d_stirrup, inp.db_assume,
            comp_on_top=True)   # +M ช่วง · เหล็กดึงล่าง · ถ้า doubly → เหล็กอัดบน
        d_act = bottom.get("d_actual") or compute_effective_depth(inp.h, inp.cover, inp.d_stirrup, inp.db_assume)
        R_hi = max(abs(vm[i]["V_left"]), abs(vm[i]["V_right"]))
        R_lo = min(abs(vm[i]["V_left"]), abs(vm[i]["V_right"]))
        try:
            sd = design_shear(Wu_kN_m=ws[i], L_m=Ls[i], R_A_kN=R_hi, R_B_kN=R_lo,
                              factored_points=None, b_cm=inp.b, d_cm=d_act,
                              fc_ksc=inp.fc, fyt_ksc=_FYT_STIRRUP_DEFAULT_KSC, phi=PHI_SHEAR)
        except SectionTooSmallForShearError as exc:
            sd = {"branch": "FAIL", "passes": False, "error": str(exc),
                  "shop_drawing_notation": "หน้าตัดไม่พอ · ต้องขยาย"}
        # Serviceability · ความลึกน้อยที่สุดต่อช่วง (DRMK ตาราง 3.1): ช่วงริม=ต่อเนื่องปลายเดียว L/18.5 · ช่วงใน=สองด้าน L/21
        _md_kind_i = "one_end" if (i == 0 or i == n - 1) else "both_ends"
        _h_min_i = min_beam_depth(Ls[i], _md_kind_i, inp.fy)
        spans_out.append({
            "label": f"{_grid_label(i)}-{_grid_label(i+1)}", "L": Ls[i], "wu_kNm": ws[i],
            "M_pos_kNm": M_pos, "M_pos_tonm": M_pos * KNM_TO_TONM,
            "x_at_M_pos_m": vm[i]["x_Mpos"], "pos_denom": None,
            "Vu_kN": Vu, "Vu_ton": Vu * KN_TO_TON,
            "n_points": len(pts[i]),
            "bottom": bottom, "bottom_bars": _fmt_main_bars(bottom.get("rebar")),
            "is_doubly": bool(bottom.get("is_doubly")),
            "comp_bars": _fmt_main_bars(bottom.get("rebar_compression")) if bottom.get("is_doubly") else "—",
            "shear": sd,
            "h_min_cm": round(_h_min_i, 1), "md_ok": inp.h >= _h_min_i - FLOAT_TOL, "md_kind": _md_kind_i,
        })

    supports_out = []
    for sidx in range(n + 1):
        Mneg = -Ms[sidx]
        if Mneg <= FLOAT_TOL:
            supports_out.append({"label": _grid_label(sidx), "M_neg_kNm": 0.0, "M_neg_tonm": 0.0,
                                 "neg_denom": None, "top": None, "top_bars": "—",
                                 "desc": ("ปลายอิสระ (M⁻=0)" if sidx in (0, n) else f"ที่รองรับ {_grid_label(sidx)}")})
            continue
        top = _safe_flexure_design(
            Mneg, inp.b, inp.h, inp.fc, inp.fy, inp.cover, inp.d_stirrup, inp.db_assume,
            comp_on_top=False)   # −M หัวเสา · เหล็กดึงบน · ถ้า doubly → เหล็กอัดล่าง
        supports_out.append({
            "label": _grid_label(sidx), "M_neg_kNm": Mneg, "M_neg_tonm": Mneg * KNM_TO_TONM,
            "neg_denom": None, "desc": f"ที่รองรับ {_grid_label(sidx)}",
            "top": top, "top_bars": _fmt_main_bars(top.get("rebar")),
            "is_doubly": bool(top.get("is_doubly")),
            "comp_bars": _fmt_main_bars(top.get("rebar_compression")) if top.get("is_doubly") else "—"})

    reactions = [{"label": _grid_label(i), "R_kN": az["reactions"][i],
                  "R_ton": az["reactions"][i] * KN_TO_TON} for i in range(n + 1)]
    uplift = [_grid_label(i) for i in range(n + 1) if az["reactions"][i] < -FLOAT_TOL]

    interior = [s for s in supports_out if s["top"] and 0 < (ord(s["label"]) - ord("A")) < n]
    gov = max(interior, key=lambda s: s["M_neg_kNm"], default=None)
    rec_top = None
    if gov and gov["top"].get("rebar"):
        gidx = ord(gov["label"]) - ord("A")
        adj = ([Ls[gidx - 1]] if gidx - 1 >= 0 else []) + ([Ls[gidx]] if gidx < n else [])
        cutoff = max(adj) / 4.0 if adj else 0.0
        rec_top = {"bars": _fmt_main_bars(gov["top"]["rebar"]), "governing_support": gov["label"],
                   "M_neg_tonm": gov["M_neg_tonm"], "cutoff_each_side_m": cutoff,
                   "note": f"แนะนำใช้เหล็กบน {_fmt_main_bars(gov['top']['rebar'])} พาดผ่านทุกหัวเสาภายใน "
                           f"· ยื่นจากกึ่งกลางเสา L/4 = {cutoff:.2f} ม. ต่อข้าง"}

    # cantilever design rows (top steel + shear-at-face + Ld + advisories)
    cantilevers_out = []
    if cant_L:
        cantilevers_out.append(_design_one_cantilever(cant_L, "L", inp, Ls[0]))
    if cant_R:
        cantilevers_out.append(_design_one_cantilever(cant_R, "R", inp, Ls[-1]))
    cant_warnings = [w for c in cantilevers_out for w in c["warnings"]]

    all_pass = (all(s["bottom"].get("passes") for s in spans_out)
                and all((s["top"] is None or s["top"].get("passes")) for s in supports_out)
                and all(s["shear"].get("passes") for s in spans_out)
                and all(c["passes"] for c in cantilevers_out)
                and not uplift)

    # ---- diagram sample arrays (global x from left end) in Thai units ----
    total_L = sum(Ls)
    diag_x, diag_V, diag_M = [], [], []
    # left overhang: tip at x=−Lc → support A at x=0 (iterate tip→support so x ascends)
    if cant_L:
        sL = _cantilever_VM(cant_L["L"], cant_L["w"], cant_L["pts"], "L")
        for k in range(len(sL["S"]) - 1, -1, -1):
            diag_x.append(round(-sL["S"][k], 4))
            diag_V.append(round(sL["V"][k] * KN_TO_TON, 4))
            diag_M.append(round(sL["M"][k] * KNM_TO_TONM, 4))
    xc = 0.0
    for i in range(n):
        for k in range(len(vm[i]["X"])):
            diag_x.append(round(xc + vm[i]["X"][k], 4))
            diag_V.append(round(vm[i]["V"][k] * KN_TO_TON, 4))      # ตัน
            diag_M.append(round(vm[i]["M"][k] * KNM_TO_TONM, 4))    # ตัน·ม
        xc += Ls[i]
    # right overhang: last support at x=total_L → tip at x=total_L+Lc
    if cant_R:
        sR = _cantilever_VM(cant_R["L"], cant_R["w"], cant_R["pts"], "R")
        for k in range(len(sR["S"])):
            diag_x.append(round(total_L + sR["S"][k], 4))
            diag_V.append(round(sR["V"][k] * KN_TO_TON, 4))
            diag_M.append(round(sR["M"][k] * KNM_TO_TONM, 4))
    # node x (supports) + per-span load descriptors for the schematic
    node_x, xc2 = [0.0], 0.0
    for L in Ls:
        xc2 += L; node_x.append(round(xc2, 4))
    span_loads = []
    for i in range(n):
        span_loads.append({
            "wu_ton_m": round(ws[i] * KN_TO_TON, 3),
            "points": [{"x": round(a, 3), "Pu_ton": round(P * KN_TO_TON, 3)} for P, a in pts[i]],
        })
    # cantilever geometry + loads for schematic (global x · point x_global)
    cantilever_geo = {
        "left": ({"L": cant_L["L"], "tip_x": round(-cant_L["L"], 4),
                  "wu_ton_m": round(cant_L["w"] * KN_TO_TON, 3),
                  "points": [{"x_global": round(-a, 3), "Pu_ton": round(P * KN_TO_TON, 3)} for P, a in cant_L["pts"]]}
                 if cant_L else None),
        "right": ({"L": cant_R["L"], "tip_x": round(total_L + cant_R["L"], 4),
                   "wu_ton_m": round(cant_R["w"] * KN_TO_TON, 3),
                   "points": [{"x_global": round(total_L + a, 3), "Pu_ton": round(P * KN_TO_TON, 3)} for P, a in cant_R["pts"]]}
                  if cant_R else None),
    }

    # ระยะหยุดเหล็ก: baseline มาตรฐาน รูปที่ 8.32 (fig-8.32 fixed L/8·L/4·L/3) เสมอ
    cur = compute_curtailment(
        spans_out, supports_out, Ls, inp.h, inp.cover, inp.d_stirrup, inp.db_assume,
        # รวมจุดโหลดคานยื่นด้วย: คานยื่นมีจุดโหลด → exterior support moment ≠ UDL → flag (Codex P2)
        point_loads_per_span=(list(pts) + [c["pts"] for c in (cant_L, cant_R) if c and c.get("pts")]))
    # A2a: เมื่อมี "จุดโหลด" (ในช่วง/คานยื่น) → fig-8.32 (L/8) เป็นค่าประมาณ → override เหล็กล่างด้วย moment envelope จริง (exact)
    #   route เฉพาะกรณีจุดโหลด (เหมือน single #21 บน factored_points) · ช่วงไม่เท่า-UDL ล้วนคง fig-8.32 (textbook standard เดิม)
    #   เหล็กบน (−M) ยังคง fig-8.32 (A2b จะคำนวณ envelope ต่อ) · applicable คง False เพราะบนยัง approx (honest flag)
    has_point_loads = any(len(p) > 0 for p in pts) or any(
        c and c.get("pts") for c in (cant_L, cant_R))
    if cur and not cur.get("applicable") and has_point_loads:
        env = compute_curtailment_continuous_envelope(
            spans_out, supports_out, vm, inp.h, inp.cover, inp.d_stirrup, inp.db_assume,
            inp.fy, inp.fc, inp.b, PHI_FLEXURE)
        if env and env.get("bottom"):
            cur["bottom"] = env["bottom"]
            cur["bottom_exact"] = True
            cur["citations"] = cur["citations"] + env["citations"]
            # A2b: merge เหล็กบน envelope (interior เท่านั้น) ทับ fig-8.32 ตาม support label · exterior+คานยื่น คง fig-8.32 (Codex P2)
            n_top_supports = len(cur.get("top") or [])
            env_top = {t["support"]: t for t in (env.get("top") or [])}
            if env_top:
                cur["top"] = [env_top.get(t["support"], t) for t in cur["top"]]
            # top_exact เฉพาะเมื่อ envelope คลุม "ทุก" support ที่มีเหล็กบน (ไม่มี exterior คานยื่นเหลือ fig-8.32)
            top_all_exact = bool(env_top) and len(env_top) == n_top_supports
            if top_all_exact:
                cur["top_exact"] = True
            if cur.get("bottom_exact") and cur.get("top_exact"):
                # บน-ล่าง exact ครบ (ไม่มีคานยื่น top) → ลบ half-state · applicable=True · ไม่มี ⚠️
                cur["applicable"] = True
                cur["warnings"] = []
                cur["method"] = cur["method"] + " · เหล็กบน-ล่างคำนวณจาก moment envelope จริง (exact ทั้งหมด)"
            elif env_top:                               # interior top exact แต่ยังมี exterior/คานยื่น top = fig-8.32 + full+Ld (honest)
                cur["method"] = cur["method"] + " · เหล็กล่าง + เหล็กบนหัวเสาในคำนวณจาก moment envelope จริง (exact)"
                cur["warnings"] = [
                    "✅ เหล็กล่าง (+M) + เหล็กบนหัวเสาภายใน (−M) คำนวณจาก moment envelope จริง (exact · asymmetric)",
                    "⚠️ เหล็กบนฝั่งคานยื่น/ปลาย ใช้มาตรฐาน รูปที่ 8.32 + วิ่งเต็ม+Ld — ตรวจระยะฝัง (anchorage) คานยื่นแยก",
                ]
            else:                                       # ไม่มี interior top envelope (เช่นไม่มี interior support) · เหล็กล่าง exact เท่านั้น
                cur["method"] = cur["method"] + " · เหล็กล่างคำนวณจาก moment envelope จริง (exact)"
                cur["warnings"] = [
                    "✅ เหล็กล่าง (+M) คำนวณจาก moment envelope จริง — ระยะตัดแม่นยำ (อาจไม่สมมาตร ซ้าย≠ขวา)",
                    "⚠️ เหล็กบน (−M) ยังใช้มาตรฐาน รูปที่ 8.32 (ค่าประมาณเมื่อมีจุดโหลด) · ควรตรวจ moment envelope",
                ]

    # Serviceability · รวมช่วงที่ตื้นกว่าความลึกขั้นต่ำ (DRMK ตาราง 3.1 · advisory · ไม่เปลี่ยน passes)
    _md_fail = [s for s in spans_out if not s.get("md_ok", True)]
    min_depth_warnings = [
        (f"🟡 ตื้นเกิน: ช่วง {s['label']} h={inp.h:.0f} ซม. < ความลึกขั้นต่ำ "
         f"{'L/18.5' if s.get('md_kind') == 'one_end' else 'L/21'} = {s['h_min_cm']:.1f} ซม. "
         f"(DRMK ตาราง 3.1 · {'ช่วงริม·ต่อเนื่องปลายเดียว' if s.get('md_kind') == 'one_end' else 'ช่วงใน·ต่อเนื่องสองด้าน'}) "
         f"— เสี่ยงแอ่นตัวเกิน · ต้องคำนวณระยะแอ่นจริง (ตาราง 10.3) หรือเพิ่มความลึก")
        for s in _md_fail
    ]
    # คานยื่น (overhang) ที่ตื้นกว่า Lc/8 → รวมเข้า headline ด้วย (consistency กับช่วงเดียว · P3 self-review)
    _cant_md_fail = [c for c in cantilevers_out if not c.get("min_depth_ok", True)]
    for c in _cant_md_fail:
        min_depth_warnings += [w for w in c.get("warnings", []) if "Lc/8" in w or "ขั้นต่ำคานยื่น" in w]
    min_depth_ok_all = (not _md_fail) and (not _cant_md_fail)

    return {
        "method": "Three-Moment Equation (วิเคราะห์แม่นยำ)",
        "min_depth_ok": min_depth_ok_all, "min_depth_warnings": min_depth_warnings,
        "n_spans": n, "b": inp.b, "h": inp.h, "fc": inp.fc, "fy": inp.fy,
        "end_left": inp.end_left, "end_right": inp.end_right,
        "spans": spans_out, "supports": supports_out, "reactions": reactions,
        "uplift_supports": uplift, "recommended_top": rec_top, "passes": all_pass,
        "curtailment": cur,
        "support_moments_tonm": [round(m * KNM_TO_TONM, 3) for m in Ms],
        "total_L": round(total_L, 4), "node_x": node_x, "span_loads": span_loads,
        "diagram": {"x": diag_x, "V_ton": diag_V, "M_tonm": diag_M},
        "cantilevers": cantilevers_out, "cantilever_geo": cantilever_geo,
        "cantilever_warnings": cant_warnings, "has_cantilever": bool(cant_L or cant_R),
        "citations": [
            "วิเคราะห์แม่นยำ: สมการสามโมเมนต์ (Clapeyron) · EI คงที่ · ปลายเป็นจุดรองรับธรรมดา",
            "รองรับ UDL + จุดโหลด + คานยื่น (overhang · โมเมนต์ปลายรู้ค่า) · ช่วงไม่เท่ากันได้",
            "คานยื่น: เหล็กบน (hogging · DRMK รูป 3.16) · เฉือนที่หน้าเสา (ไม่ลด d) · Ld ตรวจ anchorage",
            "verified: 2 ช่วงเท่า −wL²/8 · 3 ช่วงเท่า −wL²/10 · จุดกลาง −3PL/16 · ยื่น UDL −wLc²/2 · ยื่นจุดปลาย −P·Lc",
        ] + (["⚠️ ผลคิดบนสมมติฐานโหลดเต็มทุกช่วง — คานยื่น: ควรตรวจ pattern loading (โหลดยื่น+0.9D ช่วงใน) สำหรับ uplift/+M สูงสุด"]
             if (cant_L or cant_R) else []),
    }


# ----------------------------------------------------------------------------
# Markdown rendering (for SKILL.md to inline output)
# ----------------------------------------------------------------------------


def render_output_markdown(out: BeamOutput, beam_name: str = "B?") -> str:
    """Render BeamOutput as Thai-language Markdown · matches SKILL.md template."""
    inp = out.input
    grade = next(
        (g for g, fy in THAI_STEEL_GRADES.items() if abs(fy - inp.fy) < FLOAT_TOL),
        "?",
    )

    # rebar string
    if out.rebar:
        rebar_str = " + ".join(f"{n}-{name}" for name, n in out.rebar.main_bars)
        as_provided = out.rebar.As_provided
    else:
        rebar_str = "ไม่พบ combo · ขยายหน้าตัด"
        as_provided = 0.0

    verdict = "✅ ผ่าน" if out.passes else "❌ ไม่ผ่าน"

    md = f"""> ⚠️ ผลคำนวณ preliminary · ต้องตรวจสอบโดยวิศวกร ก.ว. ก่อนใช้งานจริง

## TL;DR ({beam_name})

ใช้ **{rebar_str}** · ρ = {out.rho_final*100:.3f}% · φMn = {out.phi_Mn:,.0f} kg·cm · **{verdict}** · safe margin {out.safety_margin_pct:+.1f}%

## Inputs

- b = {inp.b} cm · h = {inp.h} cm · d = {out.d_actual:.2f} cm (cover {inp.cover} + stirrup {inp.d_stirrup} + db/2)
- L = {inp.L} m · support = {inp.support.value}
- f'c = {inp.fc} ksc · fy = {inp.fy:.0f} ksc (Grade {grade})
- DL = {inp.DL} kN/m · LL = {inp.LL} kN/m · combo = {inp.load_combo.value}

## Calc trace

### Step 1 · Effective depth (assumed)
d = h − cover − d_stirrup − db/2 = {inp.h} − {inp.cover} − {inp.d_stirrup} − {inp.db_assume/2} = **{out.d_assumed:.2f} cm**

### Step 2 · β1 (Whitney stress block factor)
β1 = **{out.beta1:.3f}** (f'c = {inp.fc} ksc)  [ref: มงคล Eq 3.7]

### Step 3 · ρb (balanced ratio)
ρb = (0.85 · β1 · f'c / fy) · (6120 / (6120 + fy)) = **{out.rho_b:.5f}**  [ref: มงคล Eq 3.12]

### Step 4 · Limits
ρmin = 14/fy = **{out.rho_min:.5f}**  [มงคล Eq 3.16]
ρmax = 0.75·ρb = **{out.rho_max:.5f}**  [มงคล Eq 3.13 · ว.ส.ท. compliance]

### Step 5-6 · Required strength + design ρ
Wu = {LOAD_FACTOR_DEAD}·DL + {LOAD_FACTOR_LIVE}·LL = **{out.Wu:.3f} kN/m**
Mu = Wu·L²/{ {SupportType.SIMPLY_SUPPORTED: 8, SupportType.CANTILEVER: 2, SupportType.CONTINUOUS: 10}[inp.support] } = **{out.Mu:.3f} kN·m** ({out.Mu_kg_cm:,.0f} kg·cm)
Rn = Mu / (φ·b·d²) = **{out.Rn:.3f} ksc**
ρ_design = (0.85·f'c/fy)·[1 − √(1 − 2Rn/0.85f'c)] = **{out.rho_design:.5f}**

### Step 7 · Limit check
{('· '.join(out.notes) if out.notes else 'ρmin ≤ ρ ≤ ρmax · OK')}
ρ_final = **{out.rho_final:.5f}**

### Step 8 · As required
As_req = ρ·b·d = **{out.As_required:.3f} cm²**

### Step 9 · Rebar selection
{rebar_str} → As_provided = **{as_provided:.3f} cm²** ≥ As_req {('✅' if as_provided >= out.As_required - FLOAT_TOL else '❌')}
Min clear spacing = {out.rebar.spacing_min_clear if out.rebar else 0} cm

### Step 10-11 · Final verification
d_actual = **{out.d_actual:.2f} cm** (after rebar selection)
a = (As·fy)/(0.85·f'c·b) = **{out.a_stress_block:.2f} cm**
Mn = As·fy·(d − a/2) = **{out.Mn:,.0f} kg·cm**
φMn = {PHI_FLEXURE}·Mn = **{out.phi_Mn:,.0f} kg·cm**  {'≥' if out.passes else '<'} Mu = {out.Mu_kg_cm:,.0f} kg·cm

## ผ่าน/ไม่ผ่าน

- ρmin ({out.rho_min:.5f}) ≤ ρ_actual ({out.rho_final:.5f}) ≤ ρmax ({out.rho_max:.5f}) → **{'ผ่าน' if (out.rho_min - FLOAT_TOL) <= out.rho_final <= (out.rho_max + FLOAT_TOL) else 'ไม่ผ่าน'}**
- φMn ({out.phi_Mn:,.0f}) ≥ Mu ({out.Mu_kg_cm:,.0f}) → **{'ผ่าน' if out.passes else 'ไม่ผ่าน'}** (margin {out.safety_margin_pct:+.1f}%)

## ที่มา (Citations)

""" + "\n".join(f"- {c}" for c in out.citations)

    if out.warnings:
        md += "\n\n## ⚠️ Warnings\n\n" + "\n".join(f"- {w}" for w in out.warnings)

    # Thai-baan summary
    n_bars_total = sum(n for _, n in out.rebar.main_bars) if out.rebar else 0
    main_size = out.rebar.main_bars[0][0] if out.rebar else "?"
    if out.passes:
        baan = (
            f"\n\n## ผลการคำนวณบ้านๆ (Thai-baan summary)\n\n"
            f"ใช้เหล็ก {rebar_str} (เหล็กเสริมรับแรงดึงด้านล่างของคาน) · เหล็กพอแล้ว · "
            f"ความปลอดภัยเหลือ {out.safety_margin_pct:.0f}% · "
            f"ใส่เหล็กแบบนี้คานจะรับน้ำหนักได้ตามที่ออกแบบ · "
            f"รอวิศวกร ก.ว. เช็คอีกที"
        )
    else:
        baan = (
            f"\n\n## ผลการคำนวณบ้านๆ (Thai-baan summary)\n\n"
            f"❌ เหล็กไม่พอ · ต้องปรับการออกแบบใหม่ · ดู section error scenarios ใน SKILL.md"
        )

    md += baan
    return md


if __name__ == "__main__":
    # Quick smoke test
    inp = BeamInput(
        b=25, h=50, L=4.5, fc=240, fy=4000,
        DL=2.5, LL=3.0, cover=3.0, d_stirrup=0.9, db_assume=1.6,
    )
    out = design_beam(inp)
    print(render_output_markdown(out, "B1"))
