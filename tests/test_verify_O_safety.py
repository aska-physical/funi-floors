"""R5 -O-safety and fail-closed regression tests for aska-physical/funi-floors.

Zero bare ``assert`` statements; runs cleanly across ``-B``, ``-O -B``, ``-B -W error``,
and isolated ``-I`` modes (when ``sympy`` is available in the interpreter environment).
"""

from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import verify


class TestFuniFloorsOSafety(unittest.TestCase):
    def test_zero_bare_asserts_in_verify_and_tests(self) -> None:
        for rel in ("verify.py", "tests/test_verify_O_safety.py"):
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            assert_lines = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)]
            self.assertEqual(assert_lines, [], f"unexpected bare assert in {rel}: {assert_lines}")

    def test_require_helper_fails_closed_under_optimize(self) -> None:
        verify.require(True, "should pass")
        with self.assertRaises(ValueError) as ctx:
            verify.require(False, "planted failure")
        self.assertIn("planted failure", str(ctx.exception))

    def test_baseline_certificate_matches_exactly_and_main_passes(self) -> None:
        expected = json.loads((ROOT / "results" / "certificate.json").read_text(encoding="utf-8"))
        fresh = verify.run_verification()
        self.assertEqual(fresh, expected)
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["verify.py"]), redirect_stdout(buf):
            rc = verify.main()
        self.assertEqual(rc, 0)
        n_controls = len(expected["must_fail_controls"])
        self.assertIn(f"({n_controls}/{n_controls} controls): OK", buf.getvalue())

    def test_every_symbolic_theorem_guard_is_live(self) -> None:
        real_simplify = verify.sp.simplify
        for fail_idx in (1, 2, 3, 4):
            calls = [0]

            def _sabotage(expr: object, _idx: int = fail_idx) -> object:
                calls[0] += 1
                if calls[0] == _idx:
                    return verify.sp.Integer(1)
                return real_simplify(expr)

            with mock.patch.object(verify.sp, "simplify", side_effect=_sabotage):
                with self.assertRaises(ValueError, msg=f"symbolic guard #{fail_idx} must fail closed"):
                    verify.verify_symbolic_theorems()

    def test_tampered_sma_tie_fails_closed_in_process_and_under_O_subprocess(self) -> None:
        # In-process check (exercises live must-fail control guard directly)
        tampered_cass = verify.solve_funicular_cassette(Asma_per_rib_mm2=50.0)
        with mock.patch.object(verify, "solve_funicular_cassette", return_value=tampered_cass):
            with self.assertRaises(ValueError) as ctx:
                verify.run_verification()
            self.assertIn("must-fail controls not rejected", str(ctx.exception))

        # Live subprocess under python3 -I -O -B --write MUST exit non-zero and leave certificate untouched
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "repo"
            shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            vp = dst / "verify.py"
            vp.write_text(
                vp.read_text(encoding="utf-8").replace(
                    "Asma_per_rib_mm2: float = 980.0", "Asma_per_rib_mm2: float = 50.0"
                ),
                encoding="utf-8",
            )
            cert_path = dst / "results" / "certificate.json"
            before_bytes = cert_path.read_bytes()
            proc = subprocess.run(
                [sys.executable, "-I", "-O", "-B", str(vp), "--write"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0, "tampered verify.py --write passed under -I -O -B")
            self.assertIn("ValueError", proc.stderr)
            self.assertEqual(cert_path.read_bytes(), before_bytes)

    def test_empty_1ppm_perturbed_and_missing_certificate_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cert_path = Path(tmp) / "certificate.json"

            # Empty receipt {}
            cert_path.write_text("{}\n", encoding="utf-8")
            err_empty = io.StringIO()
            with (
                mock.patch.object(verify, "CERT_PATH", cert_path),
                mock.patch.object(sys, "argv", ["verify.py"]),
                redirect_stderr(err_empty),
            ):
                self.assertEqual(verify.main(), 1)
            self.assertIn("[FAIL]", err_empty.getvalue())

            # 1-ppm-style scalar perturbation
            orig = json.loads((ROOT / "results" / "certificate.json").read_text(encoding="utf-8"))
            orig["funicular_cassette_9mx3m_313psf"]["H_arch_service_kN"] += 0.01
            cert_path.write_text(json.dumps(orig, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            err_pert = io.StringIO()
            with (
                mock.patch.object(verify, "CERT_PATH", cert_path),
                mock.patch.object(sys, "argv", ["verify.py"]),
                redirect_stderr(err_pert),
            ):
                self.assertEqual(verify.main(), 1)

            # Missing certificate
            cert_path.unlink()
            err_missing = io.StringIO()
            with (
                mock.patch.object(verify, "CERT_PATH", cert_path),
                mock.patch.object(sys, "argv", ["verify.py"]),
                redirect_stderr(err_missing),
            ):
                self.assertEqual(verify.main(), 1)

            # Clean --write writes exact matching certificate
            out_w = io.StringIO()
            with (
                mock.patch.object(verify, "CERT_PATH", cert_path),
                mock.patch.object(sys, "argv", ["verify.py", "--write"]),
                redirect_stdout(out_w),
            ):
                self.assertEqual(verify.main(), 0)
            self.assertEqual(
                cert_path.read_text(encoding="utf-8"),
                (ROOT / "results" / "certificate.json").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
