#!/usr/bin/env python3
"""
Receiving-Side Exact-Q Asymmetric Half-Span Checkerboard Load (`Issue #1`),
MEP-Hole Alternating Diagonal Bracing, and Carbon End-Interlock Volkersen Anchor Pull
(`Issue #3`) Audit for `aska-physical/funi-floors` (`origin/main @ 00eba18ceea0adf6`).

Evidence classification (`aska-physical/dock#8`): MODEL / CHECKER (pure-Q exact algebra;
NOT a physical bench measurement — per Issue #3, final sleeve length & wedge angle await
anchor pull-out tests). Zero floats on trust paths. Zero bare `assert`s (`-O` safe).
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

CERT_SCHEMA = "aska-physical.funi-floors.checkerboard-bracing-interlock-audit.v1"
UPSTREAM_REPO = "aska-physical/funi-floors"
UPSTREAM_MAIN_SHA = "00eba18ceea0adf69f7dc12ca47d151622faa32a"
HERE = Path(__file__).resolve().parent
DEFAULT_CERT_PATH = HERE / "funi_floors_bio_certificate.json"

MAX_JSON_DEPTH = 32
MAX_JSON_BYTES = 2_000_000
MAX_INT_DIGITS = 400
MAX_INT_BITS = 1329
MAX_SEQ_LEN = 256
_HEX_LOWER = frozenset("0123456789abcdef")
_CERT_KEYS = frozenset({"schema", "upstream_repo", "upstream_main_sha", "payload_sha256", "certificate_sha256", "payload"})


class FuniBioAuditError(ValueError):
    """Fail-closed typed error (never stripped under python3 -O)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


# ---------------------------------------------------------------------------
# Strict Input Hardening & Iterative Zero-Float Canonical JSON
# ---------------------------------------------------------------------------

def require_int(val: Any, label: str = "int", *, lo: int | None = None, hi: int | None = None) -> int:
    if type(val) is not int:
        raise FuniBioAuditError("INVALID_INT_TYPE", f"{label} must be strict int")
    if lo is not None and val < lo:
        raise FuniBioAuditError("INT_BELOW_MIN", f"{label} below min {lo}")
    if hi is not None and val > hi:
        raise FuniBioAuditError("INT_ABOVE_MAX", f"{label} above max {hi}")
    return val


def require_rat(val: Any, label: str = "rational") -> Fraction:
    if type(val) is Fraction:
        return val
    if type(val) is int:
        return Fraction(val, 1)
    raise FuniBioAuditError("INVALID_RATIONAL_TYPE", f"{label} must be strict int or Fraction")


def require_nonneg_rat(val: Any, label: str = "nonneg_rational") -> Fraction:
    q = require_rat(val, label)
    if q < 0:
        raise FuniBioAuditError("NEGATIVE_RATIONAL", f"{label} must be >= 0")
    return q


def require_pos_rat(val: Any, label: str = "pos_rational") -> Fraction:
    q = require_rat(val, label)
    if q <= 0:
        raise FuniBioAuditError("NON_POSITIVE_RATIONAL", f"{label} must be > 0")
    return q


def require_seq(val: Any, label: str = "seq", *, min_len: int = 1, max_len: int = MAX_SEQ_LEN) -> tuple[Any, ...]:
    if type(val) not in (list, tuple):
        raise FuniBioAuditError("INVALID_SEQ_TYPE", f"{label} must be strict list or tuple")
    n = len(val)
    if n < min_len:
        raise FuniBioAuditError("SEQ_TOO_SHORT", f"{label} length {n} < {min_len}")
    if n > max_len:
        raise FuniBioAuditError("SEQ_TOO_LONG", f"{label} length {n} > {max_len}")
    return tuple(val)


def fmt_q(q: Fraction) -> str:
    r = require_rat(q, "q")
    if r.denominator == 1:
        return str(r.numerator)
    return f"{r.numerator}/{r.denominator}"


def validate_json_value(obj: Any, *, max_depth: int = MAX_JSON_DEPTH) -> None:
    """Iterative zero-float, depth-capped, strict-key JSON tree validator (zero recursion)."""
    limit = require_int(max_depth, "max_depth", lo=1, hi=128)
    stack: list[tuple[Any, int]] = [(obj, 0)]
    while stack:
        cur, depth = stack.pop()
        if depth > limit:
            raise FuniBioAuditError("MAX_DEPTH_EXCEEDED", f"JSON nesting exceeds {limit}")
        t = type(cur)
        if t is dict:
            for k, v in cur.items():
                if type(k) is not str:
                    raise FuniBioAuditError("NON_STR_KEY", "dict keys must be strict str")
                stack.append((v, depth + 1))
        elif t is list:
            for item in cur:
                stack.append((item, depth + 1))
        elif t is int:
            if cur.bit_length() > MAX_INT_BITS:
                raise FuniBioAuditError("INT_TOO_LARGE", "integer exceeds bit-length cap")
        elif t in (str, bool) or cur is None:
            continue
        elif t is float:
            raise FuniBioAuditError("FLOAT_FORBIDDEN", "float values are forbidden")
        else:
            raise FuniBioAuditError("UNSUPPORTED_JSON_TYPE", f"unsupported type {t.__name__}")


def _reject_float_token(tok: str) -> Any:
    raise FuniBioAuditError("JSON_FLOAT_FORBIDDEN", f"float literal forbidden: {tok!r}")


def _reject_constant_token(tok: str) -> Any:
    raise FuniBioAuditError("JSON_CONSTANT_FORBIDDEN", f"non-RFC8259 constant forbidden: {tok!r}")


def _parse_capped_int_token(tok: str) -> int:
    digits = tok[1:] if tok.startswith("-") else tok
    if len(digits) > MAX_INT_DIGITS:
        raise FuniBioAuditError("INT_DIGIT_LIMIT", f"integer token exceeds {MAX_INT_DIGITS} digits")
    return int(tok)


def _pairs_no_dup(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise FuniBioAuditError("JSON_DUPLICATE_KEY", f"duplicate JSON key: {k!r}")
        out[k] = v
    return out


def parse_strict_json(text: str) -> Any:
    if type(text) is not str:
        raise FuniBioAuditError("INVALID_JSON_INPUT", "JSON input must be strict str")
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise FuniBioAuditError("JSON_TOO_LARGE", "JSON input exceeds byte cap")
    if not text.strip():
        raise FuniBioAuditError("EMPTY_JSON", "JSON input must be non-empty")
    try:
        parsed = json.loads(
            text,
            parse_int=_parse_capped_int_token,
            parse_float=_reject_float_token,
            parse_constant=_reject_constant_token,
            object_pairs_hook=_pairs_no_dup,
        )
    except FuniBioAuditError:
        raise
    except (ValueError, RecursionError) as exc:
        raise FuniBioAuditError("JSON_PARSE_ERROR", str(exc)) from exc
    validate_json_value(parsed)
    return parsed


def canonical_json_bytes(obj: Any) -> bytes:
    validate_json_value(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Part A: Exact-Q Half-Span Checkerboard Arch Thrust-Line (`Issue #1`) &
#         Maxwell-Calladine MEP-Hole Diagonal Bracing (`verify.py:109-110`)
# ---------------------------------------------------------------------------

def evaluate_checkerboard_arch_q(
    span_m: Any,
    width_m: Any,
    rise_m: Any,
    q_perm_kPa: Any,
    q_live_left_kPa: Any,
    q_live_right_kPa: Any,
    section_depth_m: Any,
) -> dict[str, Any]:
    """
    Exact-Q crown-hinge (3-hinged) parabolic arch equilibrium under arbitrary left/right half-span loading:
      - Symmetric mean w_avg = width * (q_perm + (q_L + q_R)/2) gives exact funicular thrust
        H = w_avg * L^2 / (8 * f) with zero crown moment M(L/2) = 0.
      - Antisymmetric checkerboard difference w_asym = width * (q_L - q_R) produces exact
        quarter-span bending M(L/4) = +w_asym * L^2 / 64, M(3L/4) = -w_asym * L^2 / 64,
        and thrust-line eccentricity e(L/4) = |M(L/4)| / H vs middle-third kern h / 6.
    """
    L = require_pos_rat(span_m, "span_m")
    w = require_pos_rat(width_m, "width_m")
    f = require_pos_rat(rise_m, "rise_m")
    q0 = require_pos_rat(q_perm_kPa, "q_perm_kPa")
    qL = require_nonneg_rat(q_live_left_kPa, "q_live_left_kPa")
    qR = require_nonneg_rat(q_live_right_kPa, "q_live_right_kPa")
    h = require_pos_rat(section_depth_m, "section_depth_m")

    wL = w * (q0 + qL)
    wR = w * (q0 + qR)
    w_avg = (wL + wR) / Fraction(2)
    w_asym = wL - wR

    # Direct statics reactions: R_A = (3*wL + wR)*L / 8, R_B = (wL + 3*wR)*L / 8
    r_a = (3 * wL + wR) * L / Fraction(8)
    h_thrust = w_avg * L * L / (Fraction(8) * f)

    # Quarter-span x = L/4: z(L/4) = 3*f/4; M_beam(L/4) = R_A*(L/4) - wL*(L/4)^2/2
    z_q = Fraction(3, 4) * f
    m_beam_q = r_a * (L / Fraction(4)) - wL * (L * L) / Fraction(32)
    m_net_q = m_beam_q - h_thrust * z_q
    m_formula = w_asym * L * L / Fraction(64)

    # Crown x = L/2: z(L/2) = f; M_beam(L/2) = R_A*(L/2) - wL*(L/2)^2/2
    m_crown = (r_a * (L / Fraction(2)) - wL * (L * L) / Fraction(8)) - h_thrust * f

    ecc_q = abs(m_net_q) / h_thrust
    kern_half = h / Fraction(6)
    half_depth = h / Fraction(2)
    # Inter-cassette shear key demand across half-span boundary: V_key = |w_asym| * L / 8
    v_key_kN = abs(w_asym) * L / Fraction(8)
    return {
        "H_thrust_kN": fmt_q(h_thrust),
        "M_quarter_kNm": fmt_q(m_net_q),
        "M_quarter_closed_form_exact": m_net_q == m_formula,
        "M_crown_zero_exact": m_crown == 0,
        "eccentricity_quarter_m": fmt_q(ecc_q),
        "middle_third_kern_m": fmt_q(kern_half),
        "section_half_depth_m": fmt_q(half_depth),
        "inside_middle_third_kern": ecc_q <= kern_half,
        "inside_physical_section": ecc_q <= half_depth,
        "inter_cassette_shear_key_demand_kN": fmt_q(v_key_kN),
    }


def _matrix_rank_q(rows: list[list[Fraction]], ncols: int) -> int:
    mat = [r[:] for r in rows]
    r = 0
    nrows = len(mat)
    for c in range(ncols):
        piv = -1
        for i in range(r, nrows):
            if mat[i][c] != 0:
                piv = i
                break
        if piv < 0:
            continue
        if piv != r:
            mat[r], mat[piv] = mat[piv], mat[r]
        pv = mat[r][c]
        nz = [(j, mat[r][j] / pv) for j in range(c, ncols) if mat[r][j] != 0]
        for j, v in nz:
            mat[r][j] = v
        for i in range(r + 1, nrows):
            if mat[i][c] != 0:
                f = mat[i][c]
                row_i = mat[i]
                for j, v in nz:
                    row_i[j] -= f * v
        r += 1
        if r == nrows:
            break
    return r


def analyze_mep_web_bracing_q(n_bays: int, pattern: str) -> dict[str, Any]:
    """
    Exact-Q Maxwell-Calladine rigidity audit of a 2D ribbed floor web strip (1-row x n_bays
    cells around MEP duct cutouts) comparing:
      - 'unbraced': open Vierendeel MEP holes (n_bays floppy shear modes, zero antisymmetric shear energy)
      - 'alternating_half': Euplectella-style checkerboard every-other-bay 45-deg diagonals
        (cuts floppy modes in half, blocks global antisymmetric shear)
      - 'full_octagonal_45': single 45-deg diagonal brace per MEP bay (0 floppy modes, statically determinate)
      - 'full_x_45': crossed 45-deg X-braces per MEP bay (0 floppy modes, n_bays redundant self-stresses).
    """
    nb = require_int(n_bays, "n_bays", lo=2, hi=8)
    if pattern not in ("unbraced", "alternating_half", "full_octagonal_45", "full_x_45"):
        raise FuniBioAuditError("UNKNOWN_WEB_PATTERN", f"unknown web pattern: {pattern!r}")

    n_verts = 2 * (nb + 1)
    ncols = 2 * n_verts

    def vid(row_y: int, col_x: int) -> int:
        return row_y * (nb + 1) + col_x

    rows: list[list[Fraction]] = []
    # Bottom & top chord horizontal bars
    for ry in (0, 1):
        for cx in range(nb):
            u, v = vid(ry, cx), vid(ry, cx + 1)
            row = [Fraction(0)] * ncols
            row[2 * u] = Fraction(-1)
            row[2 * v] = Fraction(1)
            rows.append(row)
    # Vertical web posts between MEP openings
    for cx in range(nb + 1):
        u, v = vid(0, cx), vid(1, cx)
        row = [Fraction(0)] * ncols
        row[2 * u + 1] = Fraction(-1)
        row[2 * v + 1] = Fraction(1)
        rows.append(row)

    n_diags = 0
    for cx in range(nb):
        u00, u10, u01, u11 = vid(0, cx), vid(0, cx + 1), vid(1, cx), vid(1, cx + 1)
        add_slash = False
        add_back = False
        if pattern == "alternating_half" and cx % 2 == 0:
            add_slash = True
        elif pattern == "full_octagonal_45":
            add_slash = True
        elif pattern == "full_x_45":
            add_slash = True
            add_back = True
        if add_slash:
            row = [Fraction(0)] * ncols
            row[2 * u00] = Fraction(-1)
            row[2 * u00 + 1] = Fraction(-1)
            row[2 * u11] = Fraction(1)
            row[2 * u11 + 1] = Fraction(1)
            rows.append(row)
            n_diags += 1
        if add_back:
            row = [Fraction(0)] * ncols
            row[2 * u10] = Fraction(1)
            row[2 * u10 + 1] = Fraction(-1)
            row[2 * u01] = Fraction(-1)
            row[2 * u01 + 1] = Fraction(1)
            rows.append(row)
            n_diags += 1

    rk = _matrix_rank_q(rows, ncols)
    internal_dofs = ncols - 3  # 3 planar rigid motions
    floppy = internal_dofs - rk
    self_stresses = len(rows) - rk

    # Pure global shear mode u_x(row_y, cx) = row_y, u_y = 0
    shear_vec: list[Fraction] = []
    for ry in (0, 1):
        for _ in range(nb + 1):
            shear_vec.extend([Fraction(ry), Fraction(0)])
    shear_energy = sum(
        (sum((v * shear_vec[j] for j, v in enumerate(row) if v != 0), Fraction(0)) ** 2 for row in rows),
        Fraction(0),
    )
    return {
        "pattern": pattern,
        "n_bays": nb,
        "n_diagonals": n_diags,
        "rank": rk,
        "floppy_modes": floppy,
        "self_stresses": self_stresses,
        "global_shear_energy": fmt_q(shear_energy),
        "zero_floppy_gate_pass": floppy == 0,
    }


# ---------------------------------------------------------------------------
# Part B: Exact-Q Carbon End-Interlock Volkersen Anchor Pull (`Issue #3`)
# ---------------------------------------------------------------------------

def solve_interlock_volkersen_q(
    bay_lengths_mm: Any,
    alpha_total: Any,
    rib_thrust_kN: Any,
) -> dict[str, Any]:
    """
    Exact-Q symmetric carbon-sleeve-on-carbon-rib discrete Volkersen tridiagonal solver
    (`r = 1`: -T_{i-1} + (2 + 2*lambda_i) T_i - T_{i+1} = lambda_i * W, T_0 = 0, T_m = W).
    """
    bays_raw = require_seq(bay_lengths_mm, "bay_lengths_mm", min_len=1, max_len=32)
    bays = [require_pos_rat(d, f"bay_lengths_mm[{i}]") for i, d in enumerate(bays_raw)]
    alpha = require_pos_rat(alpha_total, "alpha_total")
    w = require_pos_rat(rib_thrust_kN, "rib_thrust_kN")
    l_sleeve = sum(bays, Fraction(0))
    lams = [alpha * d / l_sleeve for d in bays]
    n = len(bays)

    c_p = [Fraction(0)] * n
    d_p = [Fraction(0)] * n
    for i in range(n):
        diag = Fraction(2) + 2 * lams[i]
        rhs_i = lams[i] * w + (w if i == n - 1 else Fraction(0))
        if i == 0:
            c_p[0] = Fraction(-1) / diag
            d_p[0] = rhs_i / diag
        else:
            denom = diag + c_p[i - 1]
            c_p[i] = Fraction(-1) / denom
            d_p[i] = (rhs_i + d_p[i - 1]) / denom
    T = [Fraction(0)] * n
    T[n - 1] = d_p[n - 1]
    for i in range(n - 2, -1, -1):
        T[i] = d_p[i] - c_p[i] * T[i + 1]

    Ts = [Fraction(0)] + T + [w]
    res_ok = all(
        (-Ts[i] + (Fraction(2) + 2 * lams[i]) * Ts[i + 1] - Ts[i + 2]) == lams[i] * w
        for i in range(n)
    )
    forces = [Ts[i + 1] - Ts[i] for i in range(n + 1)]
    return {
        "n_pins": n + 1,
        "sleeve_length_mm": l_sleeve,
        "pin_forces_kN": forces,
        "peak_pin_force_kN": max(forces),
        "force_sum_exact": sum(forces, Fraction(0)) == w,
        "tridiagonal_residual_zero": res_ok,
    }


def evaluate_interlock_gate_q(
    bay_lengths_mm: Any,
    *,
    hole_diam_mm: Any,
    alpha_total: Any,
    rib_thrust_kN: Any,
    pin_capacity_kN: Any,
    intact_rib_tear_kN: Any,
) -> dict[str, Any]:
    """
    Receiving-side carbon end-interlock pass/fail gate (`Issue #3`, 700 kN per rib end):
    checks BOTH Volkersen lead-pin bearing/shear capacity AND net-section rib ligament tear.
    """
    dh = require_pos_rat(hole_diam_mm, "hole_diam_mm")
    w = require_pos_rat(rib_thrust_kN, "rib_thrust_kN")
    f_cap = require_pos_rat(pin_capacity_kN, "pin_capacity_kN")
    t0 = require_pos_rat(intact_rib_tear_kN, "intact_rib_tear_kN")

    sol = solve_interlock_volkersen_q(bay_lengths_mm, alpha_total, w)
    m = sol["n_pins"]
    l_sl = sol["sleeve_length_mm"]
    unif_pin = w / Fraction(m)
    peak_pin = sol["peak_pin_force_kN"]
    lig_frac = Fraction(1) - Fraction(m) * dh / l_sl
    tear_cap = t0 * lig_frac

    pin_ok = peak_pin <= f_cap
    tear_ok = tear_cap >= w
    return {
        "n_pins": m,
        "sleeve_length_mm": fmt_q(l_sl),
        "uniform_pin_load_kN": fmt_q(unif_pin),
        "peak_pin_load_kN": fmt_q(peak_pin),
        "pin_capacity_kN": fmt_q(f_cap),
        "net_ligament_fraction": fmt_q(lig_frac),
        "net_rib_tear_capacity_kN": fmt_q(tear_cap),
        "uniform_assumption_passes": unif_pin <= f_cap,
        "volkersen_pin_gate_passes": pin_ok,
        "ligament_tear_gate_passes": tear_ok,
        "receiving_interlock_gate_pass": all((sol["tridiagonal_residual_zero"], sol["force_sum_exact"], pin_ok, tear_ok)),
    }


def build_study_payload() -> dict[str, Any]:
    """Build deterministic exact-Q receiving-side payload for aska-physical/funi-floors Issues #1 & #3."""
    # Issue #1: L = 9 m, w = 3 m, f = 285/1000 m, q_perm = 291/100 kPa (1.91 dead + 1.00 SDL), q_live = 15 kPa
    L_m = Fraction(9)
    w_m = Fraction(3)
    f_m = Fraction(285, 1000)
    q_perm = Fraction(291, 100)
    q_live = Fraction(15)
    t_shell_m = Fraction(55, 1000)
    h_ribbed_m = Fraction(380, 1000)

    sym_shell_pass = evaluate_checkerboard_arch_q(L_m, w_m, f_m, q_perm, q_live, q_live, t_shell_m)
    asym_unribbed_fail = evaluate_checkerboard_arch_q(L_m, w_m, f_m, q_perm, q_live, Fraction(0), t_shell_m)
    asym_ribbed_pass = evaluate_checkerboard_arch_q(L_m, w_m, f_m, q_perm, q_live, Fraction(0), h_ribbed_m)

    web_unbraced = analyze_mep_web_bracing_q(4, "unbraced")
    web_alt_half = analyze_mep_web_bracing_q(4, "alternating_half")
    web_full_45 = analyze_mep_web_bracing_q(4, "full_octagonal_45")
    web_full_x = analyze_mep_web_bracing_q(4, "full_x_45")

    # Issue #3: nominal 700 kN/rib reference input (upstream certificate thrust is 2,857 kN / 4 = 714.2 kN/rib;
    # all three pass/fail gates hold identically at 714.2 kN/rib: uniform peak 280.58 > 260 kN FAIL,
    # graded peak 249.97 <= 260 kN & 714.2 <= 720 kN PASS, 6-pin tear 480 < 714.2 kN FAIL).
    # Sleeve = 400 mm, d_h = 40 mm, alpha = 4, pin_cap = 260 kN, intact_rib_tear = 1,200 kN.
    single_480_shortfall = Fraction(700) - Fraction(480)
    interlock_unif_4_fail = evaluate_interlock_gate_q(
        [Fraction(400, 3)] * 3,
        hole_diam_mm=Fraction(40),
        alpha_total=Fraction(4),
        rib_thrust_kN=Fraction(700),
        pin_capacity_kN=Fraction(260),
        intact_rib_tear_kN=Fraction(1200),
    )
    interlock_graded_4_pass = evaluate_interlock_gate_q(
        [Fraction(400, 6), Fraction(800, 3), Fraction(400, 6)],
        hole_diam_mm=Fraction(40),
        alpha_total=Fraction(4),
        rib_thrust_kN=Fraction(700),
        pin_capacity_kN=Fraction(260),
        intact_rib_tear_kN=Fraction(1200),
    )
    interlock_overperf_6_fail = evaluate_interlock_gate_q(
        [Fraction(80)] * 5,
        hole_diam_mm=Fraction(40),
        alpha_total=Fraction(4),
        rib_thrust_kN=Fraction(700),
        pin_capacity_kN=Fraction(260),
        intact_rib_tear_kN=Fraction(1200),
    )

    all_passed = all((
        sym_shell_pass["M_quarter_closed_form_exact"],
        sym_shell_pass["M_crown_zero_exact"],
        sym_shell_pass["inside_middle_third_kern"],
        asym_unribbed_fail["M_quarter_closed_form_exact"],
        asym_unribbed_fail["M_quarter_kNm"] == "3645/64",
        asym_unribbed_fail["eccentricity_quarter_m"] == "285/5552",
        not asym_unribbed_fail["inside_middle_third_kern"],
        not asym_unribbed_fail["inside_physical_section"],
        asym_ribbed_pass["inside_middle_third_kern"],
        asym_ribbed_pass["inside_physical_section"],
        web_unbraced["floppy_modes"] == 4,
        web_unbraced["global_shear_energy"] == "0",
        web_alt_half["floppy_modes"] == 2,
        web_alt_half["global_shear_energy"] == "2",
        web_full_45["zero_floppy_gate_pass"],
        web_full_x["zero_floppy_gate_pass"],
        single_480_shortfall == Fraction(220),
        interlock_unif_4_fail["uniform_assumption_passes"],
        not interlock_unif_4_fail["volkersen_pin_gate_passes"],
        not interlock_unif_4_fail["receiving_interlock_gate_pass"],
        interlock_graded_4_pass["peak_pin_load_kN"] == "245",
        interlock_graded_4_pass["receiving_interlock_gate_pass"],
        not interlock_overperf_6_fail["ligament_tear_gate_passes"],
        not interlock_overperf_6_fail["receiving_interlock_gate_pass"],
    ))

    return {
        "evidence_label": "model_checker_exact_Q_not_bench_measurement",
        "upstream_anchors": {
            "repo": UPSTREAM_REPO,
            "main_sha": UPSTREAM_MAIN_SHA,
            "issues_bridged": "Issue #1 (half-span 15/0 kPa checkerboard arch bending), Issue #3 (700 kN/rib carbon end-interlock), verify.py:109-110,280-282",
        },
        "part_a_checkerboard_arch_and_mep_bracing": {
            "symmetric_15_15_unribbed_shell_passes": sym_shell_pass,
            "asymmetric_15_0_unribbed_55mm_shell_fails": asym_unribbed_fail,
            "asymmetric_15_0_ribbed_380mm_cassette_passes": asym_ribbed_pass,
            "mep_web_rigidity_comparison": [web_unbraced, web_alt_half, web_full_45, web_full_x],
        },
        "part_b_carbon_end_interlock_issue3": {
            "single_480kN_dowel_shortfall_kN": fmt_q(single_480_shortfall),
            "single_480kN_dowel_insufficient_for_700kN_rib": single_480_shortfall == Fraction(220),
            "uniform_4pin_sleeve_volkersen_fails": interlock_unif_4_fail,
            "graded_end_dense_4pin_sleeve_passes": interlock_graded_4_pass,
            "over_perforated_6pin_sleeve_tear_fails": interlock_overperf_6_fail,
        },
        "all_passed": all_passed,
    }


# ---------------------------------------------------------------------------
# Fail-Closed Certificate Builder, Checker & CLI
# ---------------------------------------------------------------------------

def _require_sha256_hex(val: Any, label: str) -> str:
    if type(val) is not str:
        raise FuniBioAuditError("INVALID_DIGEST_TYPE", f"{label} must be strict str")
    if len(val) != 64:
        raise FuniBioAuditError("INVALID_DIGEST_LEN", f"{label} must have length 64")
    if any(ch not in _HEX_LOWER for ch in val):
        raise FuniBioAuditError("INVALID_DIGEST_HEX", f"{label} must be lowercase hex")
    return val


_DARWIN_SYSTEM_ROOT_ALIASES: tuple[tuple[str, str], ...] = (
    ("/var", "/private/var"),
    ("/tmp", "/private/tmp"),
    ("/etc", "/private/etc"),
)


def _normalize_darwin_system_prefix(path: Path, *, allow_exact: bool = False) -> Path:
    """Map verified root-owned macOS /var, /tmp, /etc aliases to /private/* without resolving user symlinks."""
    if sys.platform != "darwin" or not path.is_absolute():
        return path
    parts = path.parts
    min_parts = 2 if allow_exact else 3
    if len(parts) < min_parts or parts[0] != "/" or ".." in parts:
        return path
    top = "/" + parts[1]
    for alias, canonical in _DARWIN_SYSTEM_ROOT_ALIASES:
        if top != alias:
            continue
        try:
            st = os.lstat(alias)
            if not stat.S_ISLNK(st.st_mode) or st.st_uid != 0:
                return path
            target = os.readlink(alias)
            if target not in (canonical, canonical.lstrip("/")):
                return path
        except OSError:
            return path
        return Path(canonical, *parts[2:])
    return path


def _require_no_symlink_path(path: Path) -> None:
    norm = _normalize_darwin_system_prefix(path)
    if norm.is_symlink():
        raise FuniBioAuditError("SYMLINK_FORBIDDEN", f"symlink path forbidden: {path}")
    for parent in norm.parents:
        if parent.is_symlink():
            raise FuniBioAuditError("SYMLINK_ANCESTOR_FORBIDDEN", f"symlink ancestor forbidden: {parent}")


def build_certificate() -> dict[str, Any]:
    payload = build_study_payload()
    payload_sha256 = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    envelope = {
        "schema": CERT_SCHEMA,
        "upstream_repo": UPSTREAM_REPO,
        "upstream_main_sha": UPSTREAM_MAIN_SHA,
        "payload_sha256": payload_sha256,
        "payload": payload,
    }
    certificate_sha256 = hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()
    return {
        "schema": CERT_SCHEMA,
        "upstream_repo": UPSTREAM_REPO,
        "upstream_main_sha": UPSTREAM_MAIN_SHA,
        "payload_sha256": payload_sha256,
        "certificate_sha256": certificate_sha256,
        "payload": payload,
    }


def verify_certificate_dict(cert: Any) -> dict[str, Any]:
    if type(cert) is not dict:
        raise FuniBioAuditError("CERT_NOT_DICT", "certificate root must be a JSON object")
    if set(cert.keys()) != _CERT_KEYS:
        raise FuniBioAuditError("CERT_SCHEMA_KEYS", f"unexpected keys: {sorted(cert.keys())}")
    if cert["schema"] != CERT_SCHEMA:
        raise FuniBioAuditError("CERT_SCHEMA_MISMATCH", "schema mismatch")
    if cert["upstream_repo"] != UPSTREAM_REPO:
        raise FuniBioAuditError("CERT_REPO_MISMATCH", "upstream_repo mismatch")
    if cert["upstream_main_sha"] != UPSTREAM_MAIN_SHA:
        raise FuniBioAuditError("CERT_SHA_MISMATCH", "upstream_main_sha mismatch")

    stored_payload_sha = _require_sha256_hex(cert["payload_sha256"], "payload_sha256")
    stored_cert_sha = _require_sha256_hex(cert["certificate_sha256"], "certificate_sha256")
    computed_payload_sha = hashlib.sha256(canonical_json_bytes(cert["payload"])).hexdigest()
    if not hmac.compare_digest(stored_payload_sha, computed_payload_sha):
        raise FuniBioAuditError("PAYLOAD_SHA_MISMATCH", "payload_sha256 mismatch")

    envelope = {
        "schema": cert["schema"],
        "upstream_repo": cert["upstream_repo"],
        "upstream_main_sha": cert["upstream_main_sha"],
        "payload_sha256": stored_payload_sha,
        "payload": cert["payload"],
    }
    computed_cert_sha = hashlib.sha256(canonical_json_bytes(envelope)).hexdigest()
    if not hmac.compare_digest(stored_cert_sha, computed_cert_sha):
        raise FuniBioAuditError("CERTIFICATE_SHA_MISMATCH", "certificate_sha256 mismatch")

    expected = build_certificate()
    if not hmac.compare_digest(computed_payload_sha, expected["payload_sha256"]):
        raise FuniBioAuditError("RECOMPUTED_PAYLOAD_DRIFT", "payload digest differs from exact recomputation")

    return {
        "valid": True,
        "schema": CERT_SCHEMA,
        "payload_sha256": computed_payload_sha,
        "certificate_sha256": computed_cert_sha,
    }


def check_certificate_file(path: Path) -> dict[str, Any]:
    if not isinstance(path, Path):
        raise FuniBioAuditError("INVALID_PATH_TYPE", "path must be a pathlib.Path")
    _require_no_symlink_path(path)
    if not path.is_file():
        raise FuniBioAuditError("CERT_FILE_NOT_FOUND", f"certificate file not found: {path}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise FuniBioAuditError("CERT_FILE_TOO_LARGE", "certificate file exceeds byte cap")
    raw = path.read_bytes()
    if b"\r\n" in raw:
        raise FuniBioAuditError("CRLF_FORBIDDEN", "CRLF line endings forbidden")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FuniBioAuditError("INVALID_UTF8", f"invalid UTF-8: {exc}") from exc
    parsed = parse_strict_json(text)
    canonical_raw = canonical_json_bytes(parsed)
    if raw not in (canonical_raw, canonical_raw + b"\n"):
        raise FuniBioAuditError("NON_CANONICAL_CERT_BYTES", "certificate file is not canonical JSON")
    return verify_certificate_dict(parsed)


def write_certificate_file(path: Path) -> dict[str, Any]:
    _require_no_symlink_path(path)
    cert = build_certificate()
    raw = canonical_json_bytes(cert) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return check_certificate_file(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exact-Q checkerboard bracing & end-interlock checker for funi-floors")
    parser.add_argument("--standalone", action="store_true", help="Run full standalone exact verification")
    parser.add_argument("--json", action="store_true", help="Emit canonical JSON certificate to stdout")
    parser.add_argument("--write", nargs="?", const=str(DEFAULT_CERT_PATH), help="Write canonical certificate")
    parser.add_argument("--check", type=str, help="Fail-closed verification of a certificate JSON file")
    args = parser.parse_args(argv)

    try:
        if args.check is not None:
            res = check_certificate_file(Path(args.check))
            print(
                f"OK {CERT_SCHEMA} payload_sha256={res['payload_sha256']} "
                f"certificate_sha256={res['certificate_sha256']}"
            )
            return 0
        if args.write is not None:
            res = write_certificate_file(Path(args.write))
            print(
                f"WROTE {CERT_SCHEMA} payload_sha256={res['payload_sha256']} "
                f"certificate_sha256={res['certificate_sha256']}"
            )
            return 0
        cert = build_certificate()
        if args.json:
            sys.stdout.buffer.write(canonical_json_bytes(cert) + b"\n")
            return 0
        print(
            f"OK {CERT_SCHEMA} payload_sha256={cert['payload_sha256']} "
            f"certificate_sha256={cert['certificate_sha256']} "
            f"all_passed={cert['payload']['all_passed']}"
        )
        return 0
    except (FuniBioAuditError, ValueError, RecursionError, OSError) as exc:
        print(f"REJECT {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
