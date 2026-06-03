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

    # verification
    a_stress_block: float = 0.0     # cm
    Mn: float = 0.0                 # nominal moment (kg·cm)
    phi_Mn: float = 0.0             # design moment capacity (kg·cm)
    safety_margin_pct: float = 0.0  # (φMn − Mu) / Mu × 100

    # status
    passes: bool = False
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["input"] = self.input.to_dict()
        if self.rebar:
            d["rebar"] = asdict(self.rebar)
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
    """d = h − cover − d_stirrup − db/2 (single layer assumption · MVP)"""
    return h - cover - d_stirrup - db / 2.0


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
    max_bars_per_layer: int = 6,
) -> Optional[RebarSelection]:
    """Pick a practical rebar combination satisfying As_provided ≥ As_required.

    Strategy: try uniform-size combos first (3-DB16 · 4-DB16 · ...) then 2-size mixes.
    Constraint: bars must fit within b with min clear spacing.

    Returns RebarSelection or None if no realistic combo found (caller should enlarge section).
    """
    table = _load_rebar_table()
    sizes = table["sizes"]  # list of {"name": "DB16", "diameter_cm": 1.6, "area_cm2": 2.011}

    available = b - 2 * cover - 2 * d_stirrup
    if available <= 0:
        return None

    best: Optional[RebarSelection] = None

    # 1) Try single-size combos (cheaper · cleaner)
    for size in sizes:
        db = size["diameter_cm"]
        area_per_bar = size["area_cm2"]
        # min clear spacing = max(db, 2.5 cm)
        min_clear = max(db, 2.5)
        for n in range(2, max_bars_per_layer + 1):
            if n * area_per_bar < As_required:
                continue
            # check fit: n bars + (n-1) clear spacing + n*db ≤ available
            required_width = n * db + (n - 1) * min_clear
            if required_width > available:
                continue
            # accept
            combo = RebarSelection(
                main_bars=[(size["name"], n)],
                As_provided=n * area_per_bar,
                spacing_min_clear=min_clear,
                fits_in_one_layer=True,
            )
            # prefer combo closest to As_required (minimize over-provision)
            if best is None or combo.As_provided < best.As_provided:
                best = combo
            break  # found smallest n for this size · move to next size

    # 2) Try 2-size mixes (e.g., 3-DB16 + 2-DB12) for efficiency
    for big in sizes:
        for small in sizes:
            if small["diameter_cm"] >= big["diameter_cm"]:
                continue
            for n_big in range(2, 5):
                for n_small in range(1, 3):
                    total_area = n_big * big["area_cm2"] + n_small * small["area_cm2"]
                    if total_area < As_required:
                        continue
                    n_total = n_big + n_small
                    if n_total > max_bars_per_layer:
                        continue
                    # check fit
                    min_clear = max(big["diameter_cm"], 2.5)
                    required_width = n_total * big["diameter_cm"] + (n_total - 1) * min_clear
                    # (use big db for conservative spacing)
                    if required_width > available:
                        continue
                    combo = RebarSelection(
                        main_bars=[
                            (big["name"], n_big),
                            (small["name"], n_small),
                        ],
                        As_provided=total_area,
                        spacing_min_clear=min_clear,
                        fits_in_one_layer=True,
                        notes=["mixed-size combo · check production detailing"],
                    )
                    if best is None or combo.As_provided < best.As_provided:
                        best = combo

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

    # Step 6 · ρ_design (may raise SectionTooSmallError)
    out.rho_design = compute_rho_design(inp.fc, inp.fy, out.Rn)

    # Step 7 · limit check (may raise OverReinforcedError)
    out.rho_final, limit_notes = apply_rho_limits(out.rho_design, out.rho_min, out.rho_max)
    out.notes.extend(limit_notes)

    # Step 8 · As_req
    out.As_required = compute_As(out.rho_final, inp.b, out.d_assumed)

    # Step 9 · rebar selection
    out.rebar = select_rebar(
        out.As_required, inp.b, inp.cover, inp.d_stirrup
    )
    if out.rebar is None:
        out.notes.append("ไม่พบ rebar combo ที่ fit ในหน้าตัดนี้ · ต้องขยาย b หรือ ใช้ multi-layer (เกิน MVP)")
        out.passes = False
        return out

    # Step 10 · d_actual after rebar selection
    db_actual = out.rebar.main_bars[0][0]  # use primary bar
    rebar_table = _load_rebar_table()
    db_actual_cm = next(
        (s["diameter_cm"] for s in rebar_table["sizes"] if s["name"] == db_actual),
        inp.db_assume,
    )
    out.d_actual = compute_effective_depth(inp.h, inp.cover, inp.d_stirrup, db_actual_cm)

    # Step 11 · final check (flexure)
    out.a_stress_block = compute_stress_block_depth(
        out.rebar.As_provided, inp.fy, inp.fc, inp.b
    )
    out.Mn = compute_Mn(out.rebar.As_provided, inp.fy, out.d_actual, out.a_stress_block)
    out.phi_Mn = PHI_FLEXURE * out.Mn
    out.passes_flexure = out.phi_Mn >= out.Mu_kg_cm - FLOAT_TOL
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
        rebar = select_rebar(As_req, b, cover, d_stirrup)
        if rebar is None:
            out.update({"As_required": As_req, "rebar": None, "passes": False,
                        "note": "ไม่พบ rebar combo ที่ fit · ต้องขยาย b หรือ multi-layer"})
            return out
        d_actual = compute_effective_depth(h, cover, d_stirrup, _db_cm(rebar))
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
        bumped = select_rebar(As_target, b, cover, d_stirrup)
        if bumped is not None:
            rebar = bumped
            d_actual = compute_effective_depth(h, cover, d_stirrup, _db_cm(rebar))
            a = compute_stress_block_depth(rebar.As_provided, fy, fc, b)
            Mn = compute_Mn(rebar.As_provided, fy, d_actual, a)
            phi_Mn = PHI_FLEXURE * Mn
        break

    out.update({"As_required": As_req, "rho_final": rho_final, "rebar": rebar,
                "Rn": Rn, "notes": limit_notes,
                "d_actual": d_actual, "a_stress_block": a, "Mn": Mn, "phi_Mn": phi_Mn,
                "passes": phi_Mn >= Mu_kgcm - FLOAT_TOL,
                "safety_margin_pct": (phi_Mn - Mu_kgcm) / Mu_kgcm * 100.0})
    return out


def _safe_flexure_design(Mu_kNm, b, h, fc, fy, cover, d_stirrup, db_assume):
    """_flexure_design_for_moment that never raises: section inadequate (over-reinforced /
    too small for singly-reinforced) → graceful failing dict instead of crashing the run.
    (Cantilevers commonly produce large hogging moments → must degrade, not crash.)"""
    try:
        return _flexure_design_for_moment(Mu_kNm, b, h, fc, fy, cover, d_stirrup, db_assume)
    except (SectionTooSmallError, OverReinforcedError) as exc:
        return {"Mu_kNm": Mu_kNm, "As_required": None, "rebar": None, "passes": False,
                "d_actual": None, "phi_Mn": 0.0, "rho_final": 0.0,
                "note": f"หน้าตัดไม่พอสำหรับ singly-reinforced: {exc}"}


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
                               inp.cover, inp.d_stirrup, inp.db_assume)
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
        "Ld_cm": (round(ld_cm, 1) if ld_cm else None),
        "Ld_note": (f"เหล็กบนต่อเนื่องเข้าช่วงข้างเคียง ≥ Ld = {ld_cm/100:.2f} ม. (วัดจากหน้าเสา) · งอฉาก 90° ปลาย 12db"
                    if ld_cm else None),
        "h_min_cm": round(h_min, 1), "min_depth_ok": md_ok,
        "warnings": warnings,
        "passes": bool(top.get("passes")) and bool(sd.get("passes")) and not backspan_short,
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
            M_pos, inp.b, inp.h, inp.fc, inp.fy, inp.cover, inp.d_stirrup, inp.db_assume)
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
        spans_out.append({
            "label": f"{_grid_label(i)}-{_grid_label(i+1)}", "L": Ls[i], "wu_kNm": ws[i],
            "M_pos_kNm": M_pos, "M_pos_tonm": M_pos * KNM_TO_TONM,
            "x_at_M_pos_m": vm[i]["x_Mpos"], "pos_denom": None,
            "Vu_kN": Vu, "Vu_ton": Vu * KN_TO_TON,
            "n_points": len(pts[i]),
            "bottom": bottom, "bottom_bars": _fmt_main_bars(bottom.get("rebar")),
            "shear": sd,
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
            Mneg, inp.b, inp.h, inp.fc, inp.fy, inp.cover, inp.d_stirrup, inp.db_assume)
        supports_out.append({
            "label": _grid_label(sidx), "M_neg_kNm": Mneg, "M_neg_tonm": Mneg * KNM_TO_TONM,
            "neg_denom": None, "desc": f"ที่รองรับ {_grid_label(sidx)}",
            "top": top, "top_bars": _fmt_main_bars(top.get("rebar"))})

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

    return {
        "method": "Three-Moment Equation (วิเคราะห์แม่นยำ)",
        "n_spans": n, "b": inp.b, "h": inp.h, "fc": inp.fc, "fy": inp.fy,
        "end_left": inp.end_left, "end_right": inp.end_right,
        "spans": spans_out, "supports": supports_out, "reactions": reactions,
        "uplift_supports": uplift, "recommended_top": rec_top, "passes": all_pass,
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
