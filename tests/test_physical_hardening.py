"""Physical & dimensional regression tests for aska-physical/funi-floors.

Covers:
  1. Dimensionally exact 45-deg CFRP web shear (explicit Ad_diag_mm2 in mm^2) and
     ACI 440.2R-17 §11.4.1.2 shear effective-strain cap (eps_fe <= 0.004).
  2. ACI 318-19 §8.4.2.3.2 / §8.4.4.2.3 unbalanced moment transfer (v_u = V_u/(b0*d) + gamma_v*M_sc*c/J_c)
     on clear span ln = 8.5 m (M_sc = 546.21 kN*m -> 107.48% utilization, FAIL).
  3. Consistent half-bay patterned rack load M(L/4) = M_beam(L/4) - H_pattern*z(L/4) against local
     section kerns (55 mm shell and 115 mm rib / T-section), proving tension at L/4 requires reinforcement.

Runs stdlib-only across ``-I -B``, ``-I -O -B``, and ``-I -B -W error`` (zero bare ``assert``s).
"""

from __future__ import annotations

import ast
import importlib
import math
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _import_verify():
    if "verify" in sys.modules:
        return sys.modules["verify"]
    try:
        return importlib.import_module("verify")
    except ModuleNotFoundError as exc:
        if exc.name != "sympy":
            raise
        stub = types.ModuleType("sympy")
        with mock.patch.dict(sys.modules, {"sympy": stub}):
            return importlib.import_module("verify")


class TestFuniFloorsPhysicalHardening(unittest.TestCase):
    def test_cfrp_web_shear_dimensionally_exact_and_aci440_capped(self) -> None:
        verify = _import_verify()
        base = verify.solve_funicular_cassette()
        self.assertEqual(base["Ad_diag_mm2"], 65.0)
        self.assertEqual(base["eps_fe_cfrp_aci440_capped"], 0.004)

        # Exact expected ACI 440.2R capped value: 22.503 + 215.985 = 238.49 kN
        expected_vc = 0.75 * 4 * (2.0 * 65.0 * 48.0) * 0.17 * math.sqrt(50.0) * 1e-3
        expected_vf = 0.75 * 4 * math.sqrt(2.0) * 65.0 * (195800.0 * 0.004) * 1e-3
        self.assertAlmostEqual(
            base["phi_V_45deg_octagonal_mep_hole_kN"],
            round(expected_vc + expected_vf, 2),
            places=2,
        )
        self.assertLess(base["phi_V_45deg_octagonal_mep_hole_kN"], 250.0)
        self.assertGreater(base["phi_V_45deg_octagonal_mep_hole_kN"], base["V_quarter_mep_demand_uls_kN"])

        # Passing 0.0065 strain must clamp to 0.004 (never return the old 373.48 kN)
        over = verify.solve_funicular_cassette(eps_fe_cfrp=0.0065)
        self.assertEqual(over["eps_fe_cfrp_aci440_capped"], 0.004)
        self.assertEqual(over["phi_V_45deg_octagonal_mep_hole_kN"], base["phi_V_45deg_octagonal_mep_hole_kN"])

        # Scaling diagonal area Ad_diag_mm2 scales the CFRP shear contribution linearly
        double_ad = verify.solve_funicular_cassette(Ad_diag_mm2=130.0)
        cfrp_1 = base["phi_V_45deg_octagonal_mep_hole_kN"] - base["phi_V_unbraced_mep_hole_kN"]
        cfrp_2 = double_ad["phi_V_45deg_octagonal_mep_hole_kN"] - double_ad["phi_V_unbraced_mep_hole_kN"]
        self.assertAlmostEqual(cfrp_2 / cfrp_1, 2.0, places=3)

        # Undersized diagonal fails quarter-span ULS demand; non-positive area/strain fail closed
        small = verify.solve_funicular_cassette(Ad_diag_mm2=20.0)
        self.assertLess(small["phi_V_45deg_octagonal_mep_hole_kN"], small["V_quarter_mep_demand_uls_kN"])
        for bad in (0.0, -10.0, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                verify.solve_funicular_cassette(Ad_diag_mm2=bad)
            with self.assertRaises(ValueError):
                verify.solve_funicular_cassette(eps_fe_cfrp=bad)

    def test_halfbay_patterned_rack_load_kern_check(self) -> None:
        verify = _import_verify()
        cass = verify.solve_funicular_cassette()
        # Consistent M(L/4) = M_beam(L/4) - H_pattern * z(L/4) = 50.132 kN*m with H_pattern = 1141.77 kN
        q_dead = cass["dead_mass_kg_m2"] * 9.80665 * 1e-3
        m_beam_q = (3.0 / 32.0) * (q_dead + 1.0) * 3.0 * 81.0 + (1.0 / 16.0) * 45.0 * 81.0
        m_expected = m_beam_q - cass["H_arch_halfbay_pattern_kN"] * (0.75 * 0.285)
        self.assertAlmostEqual(cass["M_quarter_halfbay_pattern_kNm"], m_expected, delta=0.05)
        # Honest negative finding: e = 43.91 mm exceeds BOTH 55 mm shell kern (9.17 mm) AND local 115 mm rib kern (19.17 mm; T-section 6.27 mm)
        self.assertFalse(cass["halfbay_pattern_within_shell_kern"])
        self.assertFalse(cass["halfbay_pattern_within_local_rib_kern"])
        self.assertGreater(cass["e_quarter_halfbay_pattern_mm"], cass["kern_shell_55mm_mm"])
        self.assertGreater(cass["e_quarter_halfbay_pattern_mm"], cass["kern_local_rib_115mm_mm"])
        self.assertGreater(cass["e_quarter_halfbay_pattern_mm"], cass["kern_local_t_section_bot_mm"])

    def test_aci318_unbalanced_moment_punching_shear(self) -> None:
        verify = _import_verify()
        cass = verify.solve_funicular_cassette()
        q_dead = cass["dead_mass_kg_m2"] * 9.80665 * 1e-3

        # Concentric (Mu=0) matches v0.1.0 utilization 0.8011 and passes
        conc = verify.evaluate_punching_shear_collar(9.0, 500.0, 335.0, q_dead, 1.0, 15.0)
        self.assertEqual(conc["gamma_v"], 0.4)
        self.assertEqual(conc["vu_moment_transfer_MPa"], 0.0)
        self.assertEqual(conc["vu_total_MPa"], conc["vu_concentric_MPa"])
        self.assertTrue(conc["active_collar_passes"])
        self.assertAlmostEqual(conc["utilization_active_collar"], 0.8011, places=4)

        # ACI 318-19 §8.4.2.3.2 patterned live unbalanced moment on clear span ln = 8.5 m:
        # M_sc = 0.07 * (0.5 * 1.6 * 15) * 9.0 * 8.5^2 = 546.21 kN*m (transfer stress per §8.4.4.2.3)
        mu_pat = 0.07 * (0.5 * 1.6 * 15.0) * 9.0 * (8.5**2)
        ecc = verify.evaluate_punching_shear_collar(
            9.0, 500.0, 335.0, q_dead, 1.0, 15.0, Mu_unbalanced_kNm=mu_pat
        )
        self.assertAlmostEqual(ecc["Mu_unbalanced_kNm"], 546.21, places=2)
        self.assertGreater(ecc["vu_moment_transfer_MPa"], 0.65)
        self.assertAlmostEqual(
            ecc["vu_total_MPa"],
            ecc["vu_concentric_MPa"] + ecc["vu_moment_transfer_MPa"],
            places=3,
        )
        # Honest negative finding: v0.1.0 flush collar exceeds phi*v_n (~107.48%) under ACI 318-19 §8.4.2.3.2
        self.assertGreater(ecc["utilization_active_collar"], 1.07)
        self.assertFalse(ecc["active_collar_passes"])

        # Rectangular column gamma_v monotonicity (b1 > b2 -> gamma_v > 0.40) and non-finite/non-positive guards
        rect = verify.evaluate_punching_shear_collar(
            9.0, 700.0, 335.0, q_dead, 1.0, 15.0, Mu_unbalanced_kNm=mu_pat, c_col_y_mm=400.0
        )
        self.assertGreater(rect["gamma_v"], 0.4)
        for bad in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                verify.evaluate_punching_shear_collar(Mu_unbalanced_kNm=bad)
        for bad_dim in (0.0, -50.0):
            with self.assertRaises(ValueError):
                verify.evaluate_punching_shear_collar(d_eff_mm=bad_dim)

    def test_zero_bare_asserts(self) -> None:
        for rel in ("verify.py", "tests/test_physical_hardening.py"):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            self.assertEqual([n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)], [])


if __name__ == "__main__":
    unittest.main()
