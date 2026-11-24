"""Regression and Zone-B hardening test suite for aska-physical/funi-floors.

Runs with stdlib-only under ``-I -B``, ``-I -O -B``, and ``-I -B -W error`` (zero bare ``assert``s).
If ``sympy`` is not installed in a clean-room environment, stubs ``sympy`` solely to import
the pure-numeric functions and ``main()`` from ``verify.py`` without altering any symbolic checks.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import math
import os
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import verify_guards  # noqa: E402


class _EvilPath(type(Path("."))):
    """Adversarial Path subclass that must be rejected by coerce_exact_path."""


class _FloatSubclass(float):
    """Adversarial float subclass that must be rejected by require_finite."""


def _import_verify_module():
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


class TestVerifyGuardsUnit(unittest.TestCase):
    def test_constants_pinned(self) -> None:
        self.assertEqual(verify_guards.MAX_JSON_BYTES, 10485760)
        self.assertEqual(verify_guards.MAX_JSON_DEPTH, 64)
        self.assertEqual(verify_guards.MAX_INT_DIGITS, 1000)

    def test_require_finite_and_strict_min_max(self) -> None:
        val_int = verify_guards.require_finite(5, "x")
        self.assertIs(type(val_int), float)
        self.assertEqual(val_int, 5.0)
        self.assertEqual(verify_guards.require_finite(-2.25, "y"), -2.25)

        for bad in (
            True,
            False,
            None,
            "1.0",
            1 + 0j,
            float("nan"),
            float("inf"),
            float("-inf"),
            10**400,
            -(10**400),
            _FloatSubclass(1.0),
        ):
            with self.assertRaises(ValueError):
                verify_guards.require_finite(bad, "bad")

        verify_guards.require_all_finite(a=1, b=-2.5)
        with self.assertRaisesRegex(ValueError, "cover_mm"):
            verify_guards.require_all_finite(a=1.0, cover_mm=float("inf"))

        self.assertEqual(verify_guards.strict_finite_min(35.0, 50.0), 35.0)
        self.assertEqual(verify_guards.strict_finite_min(50.0, 35.0), 35.0)
        self.assertEqual(verify_guards.strict_finite_min(10, 10.0), 10.0)
        self.assertEqual(verify_guards.strict_finite_max(0.0, 155.0), 155.0)
        self.assertEqual(verify_guards.strict_finite_max(155.0, 0.0), 155.0)
        self.assertEqual(verify_guards.strict_finite_max(-2.0, -2), -2.0)

        for pair in (
            (35.0, float("nan")),
            (float("nan"), 35.0),
            (0.0, float("inf")),
            (float("-inf"), 0.0),
            (1.0, True),
            (False, 1.0),
        ):
            with self.assertRaises(ValueError):
                verify_guards.strict_finite_min(*pair)
            with self.assertRaises(ValueError):
                verify_guards.strict_finite_max(*pair)

    def test_coerce_exact_path(self) -> None:
        p1 = verify_guards.coerce_exact_path("results/certificate.json")
        self.assertEqual(p1, Path("results/certificate.json"))
        p2 = Path("results/certificate.json")
        self.assertIs(verify_guards.coerce_exact_path(p2), p2)

        for bad in ("", "a\x00b", Path("a\x00b"), _EvilPath("results/certificate.json"), b"abc", 42, None):
            with self.assertRaises(ValueError):
                verify_guards.coerce_exact_path(bad)

    def test_reject_symlinks_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real_dir = root / "real"
            real_dir.mkdir()
            real_file = real_dir / "ok.json"
            real_file.write_text("{}\n", encoding="utf-8")

            verify_guards.reject_symlinks_on_path(real_file)

            file_link = root / "link.json"
            file_link.symlink_to(real_file)
            with self.assertRaises(ValueError):
                verify_guards.reject_symlinks_on_path(file_link)

            broken_link = root / "broken.json"
            broken_link.symlink_to(root / "does_not_exist.json")
            with self.assertRaises(ValueError):
                verify_guards.reject_symlinks_on_path(broken_link)

            dir_link = root / "dir_link"
            dir_link.symlink_to(real_dir)
            with self.assertRaises(ValueError):
                verify_guards.reject_symlinks_on_path(dir_link / "ok.json")

            traversal = dir_link / ".." / "real" / "ok.json"
            with self.assertRaises(ValueError):
                verify_guards.reject_symlinks_on_path(traversal)

    def test_strict_loads_json_zone_b_matrix(self) -> None:
        self.assertEqual(verify_guards.strict_loads_json('{"a": 1, "b": [-2.5, "ok"]}'), {"a": 1, "b": [-2.5, "ok"]})

        # Exact max_bytes boundary
        exact_10 = '{"a":1234}'
        self.assertEqual(len(exact_10), 10)
        self.assertEqual(verify_guards.strict_loads_json(exact_10, max_bytes=10), {"a": 1234})
        with self.assertRaisesRegex(ValueError, "text length out of bounds"):
            verify_guards.strict_loads_json(exact_10 + " ", max_bytes=10)

        # Non-str, empty, BOM, CR/CRLF
        for bad in (b"{}", None, 123):
            with self.assertRaisesRegex(ValueError, "must be str"):
                verify_guards.strict_loads_json(bad)
        with self.assertRaisesRegex(ValueError, "text length out of bounds"):
            verify_guards.strict_loads_json("")
        with self.assertRaisesRegex(ValueError, "UTF-8 BOM rejected"):
            verify_guards.strict_loads_json("\ufeff{}")
        for cr_bad in ("{}\r", "{\r\n}"):
            with self.assertRaisesRegex(ValueError, "CR/CRLF"):
                verify_guards.strict_loads_json(cr_bad)

        # Duplicate keys (top-level and nested)
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json('{"k": 1, "k": 2}')
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json('{"outer": {"k": 1, "k": 2}}')

        # Non-finite JSON constants and float overflow
        for bad_num in ("NaN", "Infinity", "-Infinity", "1e500", "-1e500"):
            with self.assertRaises(ValueError):
                verify_guards.strict_loads_json(f'{{"x": {bad_num}}}')

        # Integer digit limit boundary (both positive and negative)
        max_pos = "9" * 1000
        max_neg = "-" + max_pos
        self.assertEqual(verify_guards.strict_loads_json(f'{{"n": {max_pos}}}')["n"], int(max_pos))
        self.assertEqual(verify_guards.strict_loads_json(f'{{"n": {max_neg}}}')["n"], int(max_neg))
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json(f'{{"n": {"9" * 1001}}}')
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json(f'{{"n": -{"9" * 1001}}}')

        # Depth boundary: lists and dicts at 64 (pass) vs 65 (fail)
        list_64 = "[" * 64 + "0" + "]" * 64
        list_65 = "[" * 65 + "0" + "]" * 65
        self.assertIsInstance(verify_guards.strict_loads_json(list_64), list)
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json(list_65)

        dict_64 = '{"a":' * 64 + "0" + "}" * 64
        dict_65 = '{"a":' * 65 + "0" + "}" * 65
        self.assertIsInstance(verify_guards.strict_loads_json(dict_64), dict)
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json(dict_65)

        # Custom max_depth boundary
        self.assertEqual(verify_guards.strict_loads_json("[[1]]", max_depth=2), [[1]])
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json("[[[1]]]", max_depth=2)

        # Malformed JSON and extreme RecursionError nesting
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json("{")
        with self.assertRaises(ValueError):
            verify_guards.strict_loads_json("[" * 5000 + "]" * 5000)

    def test_strict_parse_json_bytes(self) -> None:
        utf8_omega = b'{"a":"\xce\xa9"}'
        self.assertEqual(len(utf8_omega), 10)
        self.assertEqual(verify_guards.strict_parse_json_bytes(utf8_omega, max_bytes=10), {"a": "\u03a9"})
        # 10 UTF-8 bytes but only 9 str chars -> specifically exercises pre-decode byte-length guard
        with self.assertRaisesRegex(ValueError, "byte length out of bounds"):
            verify_guards.strict_parse_json_bytes(utf8_omega, max_bytes=9)
        with self.assertRaisesRegex(ValueError, "byte length out of bounds"):
            verify_guards.strict_parse_json_bytes(b"")

        self.assertEqual(verify_guards.strict_parse_json_bytes(b"[1]", max_depth=1), [1])
        with self.assertRaises(ValueError):
            verify_guards.strict_parse_json_bytes(b"[[1]]", max_depth=1)

        for bad in ("{}", bytearray(b"{}")):
            with self.assertRaisesRegex(ValueError, "must be bytes"):
                verify_guards.strict_parse_json_bytes(bad)
        with self.assertRaisesRegex(ValueError, "UTF-8 BOM rejected"):
            verify_guards.strict_parse_json_bytes(b"\xef\xbb\xbf{}")
        with self.assertRaisesRegex(ValueError, "CR/CRLF"):
            verify_guards.strict_parse_json_bytes(b"{}\r")
        with self.assertRaisesRegex(ValueError, "invalid UTF-8"):
            verify_guards.strict_parse_json_bytes(b"\xff\xfe")

    def test_read_regular_bytes_and_strict_read_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = root / "good.json"
            good.write_bytes(b'{"a":1}\n')
            self.assertEqual(verify_guards.strict_read_json(good), {"a": 1})
            self.assertEqual(verify_guards.strict_read_json(str(good)), {"a": 1})
            self.assertEqual(verify_guards._read_regular_bytes(good, max_bytes=8), b'{"a":1}\n')

            with self.assertRaisesRegex(ValueError, "file size out of bounds"):
                verify_guards.strict_read_json(good, max_bytes=7)
            with self.assertRaises(ValueError):
                verify_guards.strict_read_json(good, max_depth=0)

            empty = root / "empty.json"
            empty.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "file size out of bounds"):
                verify_guards._read_regular_bytes(empty)

            missing = root / "missing.json"
            with self.assertRaisesRegex(ValueError, "cannot stat"):
                verify_guards.strict_read_json(missing)

            with self.assertRaisesRegex(ValueError, "not a regular file"):
                verify_guards.strict_read_json(root)

            fifo = root / "pipe.json"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                verify_guards.strict_read_json(fifo)
            with self.assertRaisesRegex(ValueError, "not a regular file"):
                verify_guards.safe_write_canonical_json(fifo, {"a": 1})

            # Unreadable regular file triggers OSError guard on read_bytes()
            if os.geteuid() != 0:
                locked = root / "locked.json"
                locked.write_bytes(b"{}\n")
                locked.chmod(0)
                try:
                    with self.assertRaises(ValueError):
                        verify_guards._read_regular_bytes(locked)
                finally:
                    locked.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_canonical_bytes_verify_and_safe_write(self) -> None:
        payload = {"b": 1, "a": 0.0, "flag": True, "u": "\u03a9"}
        raw_ascii = verify_guards.canonical_json_bytes(payload)
        self.assertEqual(
            raw_ascii,
            (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8"),
        )
        raw_utf8 = verify_guards.canonical_json_bytes(payload, indent=1, sort_keys=False, ensure_ascii=False)
        self.assertEqual(
            raw_utf8,
            (json.dumps(payload, indent=1, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8"),
        )
        with self.assertRaises(ValueError):
            verify_guards.canonical_json_bytes({"x": float("nan")})

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "sub" / "cert.json"
            sha = verify_guards.safe_write_canonical_json(target, payload)
            self.assertEqual(sha, hashlib.sha256(raw_ascii).hexdigest())
            self.assertEqual(verify_guards.verify_canonical_json_file(target, payload), sha)

            # Overwrite existing regular file with custom formatting options
            sha_utf8 = verify_guards.safe_write_canonical_json(
                target, payload, indent=1, sort_keys=False, ensure_ascii=False
            )
            self.assertEqual(
                verify_guards.verify_canonical_json_file(
                    target, payload, indent=1, sort_keys=False, ensure_ascii=False
                ),
                sha_utf8,
            )

            # Non-object root rejected even if bytes match canonical JSON
            arr_file = root / "arr.json"
            arr_file.write_bytes(verify_guards.canonical_json_bytes([1, 2]))
            with self.assertRaises(ValueError):
                verify_guards.verify_canonical_json_file(arr_file, [1, 2])

            # Formatting and Python == coercion attacks rejected
            for tampered in (
                raw_ascii + b" ",
                raw_ascii.replace(b"\n", b"\r\n"),
                raw_ascii.replace(b'"flag": true', b'"flag": 1'),
                raw_ascii.replace(b'"a": 0.0', b'"a": -0.0'),
                raw_ascii.replace(b'"b": 1', b'"b": 1.0'),
                (json.dumps(payload, indent=2, sort_keys=False) + "\n").encode("utf-8"),
            ):
                bad_file = root / "tampered.json"
                bad_file.write_bytes(tampered)
                with self.assertRaises(ValueError):
                    verify_guards.verify_canonical_json_file(bad_file, payload)

            # max_bytes and max_depth pass-through
            with self.assertRaises(ValueError):
                verify_guards.verify_canonical_json_file(target, payload, max_bytes=4)
            with self.assertRaises(ValueError):
                verify_guards.verify_canonical_json_file(target, payload, max_depth=0)

            # safe_write_canonical_json rejects directory, symlink file, symlink parent, EvilPath
            with self.assertRaises(ValueError):
                verify_guards.safe_write_canonical_json(root, payload)
            link_target = root / "link_out.json"
            link_target.symlink_to(target)
            with self.assertRaises(ValueError):
                verify_guards.safe_write_canonical_json(link_target, payload)
            dir_link = root / "dir_link"
            dir_link.symlink_to(root / "sub")
            with self.assertRaises(ValueError):
                verify_guards.safe_write_canonical_json(dir_link / "new.json", payload)
            with self.assertRaises(ValueError):
                verify_guards.safe_write_canonical_json(_EvilPath(target), payload)


class TestFuniFloorsVerifyIntegration(unittest.TestCase):
    def test_committed_certificate_and_numeric_reproduction(self) -> None:
        verify = _import_verify_module()
        cert_path = REPO_ROOT / "results" / "certificate.json"
        committed = verify_guards.strict_read_json(cert_path)
        sha = verify_guards.verify_canonical_json_file(cert_path, committed, indent=2, sort_keys=True)
        self.assertEqual(len(sha), 64)

        cass = verify.solve_funicular_cassette()
        self.assertEqual(cass, committed["funicular_cassette_9mx3m_313psf"])

        ei_active = cass["EI_2way_dyn_MNm2_per_m"] * 1e6
        vib_active = verify.evaluate_dg11_vibration(9.0, cass["dead_mass_kg_m2"], 1.0, ei_active, 0.03)
        vib_passive = verify.evaluate_dg11_vibration(9.0, cass["dead_mass_kg_m2"], 1.0, 8.40e6, 0.025)
        self.assertEqual(vib_active, committed["dg11_vibration_benchmark"]["active_prestressed_cassette"])
        self.assertEqual(vib_passive, committed["dg11_vibration_benchmark"]["passive_cracked_shell_fails"])

        q_dead = cass["dead_mass_kg_m2"] * 9.80665 * 1e-3
        punch = verify.evaluate_punching_shear_collar(9.0, 500.0, 335.0, q_dead, 1.0, 15.0)
        punch_base = verify.evaluate_punching_shear_collar(9.0, 500.0, 210.0, 6.0, 1.0, 15.0, 40.0, 0.0, 0.0)
        self.assertEqual(punch, committed["aci318_punching_collar_313psf"]["funi_floor_with_collar"])
        self.assertEqual(punch_base, committed["aci318_punching_collar_313psf"]["baseline_250mm_pt_uncollared_fails"])

        fire = verify.evaluate_2hr_fire_endurance(9.0, 3.0, 0.285, q_dead, 1.0, 15.0)
        self.assertEqual(fire, committed["iso834_120min_fire_crossover"])

        ec_eis = verify.evaluate_carbon_and_eis_telemetry(cass["equivalent_concrete_thickness_mm"], 4, 360.0, 980.0)
        self.assertEqual(ec_eis, committed["embodied_carbon_and_eis_leak_twin"])

    def test_nan_swallowing_regressions_fail_closed(self) -> None:
        verify = _import_verify_module()
        # Explicit regressions for NaN/+Inf swallowing across public domains
        with self.assertRaises(ValueError):
            verify.solve_funicular_cassette(fc_MPa=float("nan"))
        with self.assertRaises(ValueError):
            verify.solve_funicular_cassette(T_joule_C=float("nan"))
        with self.assertRaises(ValueError):
            verify.evaluate_dg11_vibration(9.0, 200.0, 1.0, float("nan"), 0.03)
        with self.assertRaises(ValueError):
            verify.evaluate_punching_shear_collar(fc_MPa=float("nan"))
        with self.assertRaises(ValueError):
            verify.evaluate_punching_shear_collar(d_eff_mm=float("nan"))
        with self.assertRaises(ValueError):
            verify.evaluate_punching_shear_collar(fpc_collar_MPa=float("nan"))
        with self.assertRaises(ValueError):
            verify.evaluate_2hr_fire_endurance(cover_mm=float("nan"))
        with self.assertRaises(ValueError):
            verify.evaluate_2hr_fire_endurance(cover_mm=float("inf"))
        with self.assertRaises(ValueError):
            verify.evaluate_2hr_fire_endurance(cover_mm=float("-inf"))

        # Exhaustive 44-parameter x 3-poison entry-guard matrix across all 5 public numeric functions
        specs = [
            (
                verify.solve_funicular_cassette,
                {
                    "L_m": 9.0,
                    "w_cassette_m": 3.0,
                    "h_total_mm": 380.0,
                    "t_shell_mm": 55.0,
                    "h_crown_rib_mm": 115.0,
                    "f_rise_m": 0.285,
                    "q_live_kPa": 15.0,
                    "q_sdl_kPa": 1.0,
                    "fc_MPa": 50.0,
                    "n_ribs": 4,
                    "Af_per_rib_mm2": 360.0,
                    "Ef_cfrp_MPa": 195800.0,
                    "Asma_per_rib_mm2": 980.0,
                    "Esma_MPa": 165000.0,
                    "T_joule_C": 175.0,
                },
            ),
            (
                verify.evaluate_dg11_vibration,
                {
                    "L_m": 9.0,
                    "dead_mass_kg_m2": 200.0,
                    "service_live_vib_kPa": 1.0,
                    "EI_eff_Nm2_per_m": 15.0e6,
                    "beta_damping": 0.03,
                },
            ),
            (
                verify.evaluate_punching_shear_collar,
                {
                    "L_bay_m": 9.0,
                    "c_col_mm": 500.0,
                    "d_eff_mm": 335.0,
                    "q_dead_kPa": 1.91,
                    "q_sdl_kPa": 1.0,
                    "q_live_kPa": 15.0,
                    "fc_MPa": 50.0,
                    "fpc_collar_MPa": 3.8,
                    "Vp_truss_collar_kN": 480.0,
                },
            ),
            (
                verify.evaluate_2hr_fire_endurance,
                {
                    "L_m": 9.0,
                    "w_cassette_m": 3.0,
                    "f_rise_m": 0.285,
                    "q_dead_kPa": 1.91,
                    "q_sdl_kPa": 1.0,
                    "q_live_kPa": 15.0,
                    "cover_mm": 42.0,
                    "n_ribs": 4,
                    "Asma_per_rib_mm2": 980.0,
                    "Af_per_rib_mm2": 360.0,
                },
            ),
            (
                verify.evaluate_carbon_and_eis_telemetry,
                {
                    "vol_eq_313psf_mm": 74.07,
                    "n_ribs": 4,
                    "Af_mm2": 360.0,
                    "Asma_mm2": 980.0,
                    "w_m": 3.0,
                },
            ),
        ]
        for fn, defaults in specs:
            for param in defaults:
                for poison in (float("nan"), float("inf"), True):
                    kwargs = dict(defaults)
                    kwargs[param] = poison
                    with self.assertRaises(ValueError, msg=f"{fn.__name__}({param}={poison!r}) must raise ValueError"):
                        fn(**kwargs)

    def test_main_zone_b_fail_closed_and_write(self) -> None:
        verify = _import_verify_module()
        committed = verify_guards.strict_read_json(REPO_ROOT / "results" / "certificate.json")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cert_file = root / "certificate.json"
            with mock.patch.object(verify, "CERT_PATH", cert_file), mock.patch.object(
                verify, "run_verification", return_value=committed
            ):
                # Missing certificate fails closed with rc=1
                with mock.patch.object(sys, "argv", ["verify.py"]):
                    self.assertEqual(verify.main(), 1)

                # --write produces canonical file and returns 0
                with mock.patch.object(sys, "argv", ["verify.py", "--write"]):
                    self.assertEqual(verify.main(), 0)

                # Trailing space tampering fails closed with rc=1
                cert_file.write_bytes(cert_file.read_bytes() + b" ")
                with mock.patch.object(sys, "argv", ["verify.py"]):
                    self.assertEqual(verify.main(), 1)

                # Symlink target fails closed with rc=1
                real_copy = root / "real.json"
                real_copy.write_bytes(verify_guards.canonical_json_bytes(committed, indent=2, sort_keys=True))
                cert_file.unlink()
                cert_file.symlink_to(real_copy)
                with mock.patch.object(sys, "argv", ["verify.py"]):
                    self.assertEqual(verify.main(), 1)

    def test_zero_bare_asserts_and_isolated_import_guard(self) -> None:
        for rel in (
            "verify.py",
            "verify_guards.py",
            "tests/test_verify_O_safety.py",
            "tests/test_nan_and_zoneb_hardening.py",
        ):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            assert_lines = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)]
            self.assertEqual(assert_lines, [], f"unexpected bare assert in {rel}: {assert_lines}")

        # Verify verify.py imports sibling verify_guards even under python3 -I -O -B
        script = (
            "import importlib.util, sys, types; "
            "sys.modules.setdefault('sympy', types.ModuleType('sympy')); "
            f"spec = importlib.util.spec_from_file_location('verify_iso', {str(REPO_ROOT / 'verify.py')!r}); "
            "mod = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(mod); "
            "print(mod.verify_guards.MAX_JSON_DEPTH)"
        )
        proc = subprocess.run(
            [sys.executable, "-I", "-O", "-B", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "64")

    def test_darwin_system_root_alias_normalization(self) -> None:
        root_lnk = types.SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0)
        user_lnk = types.SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=1000)

        def _fake_readlink(p: str) -> str:
            if p == "/var":
                return "private/var"
            if p == "/tmp":
                return "private/tmp"
            if p == "/etc":
                return "private/etc"
            raise OSError("unexpected readlink")

        with (
            mock.patch.object(verify_guards.sys, "platform", "darwin"),
            mock.patch.object(verify_guards.os, "lstat", return_value=root_lnk),
            mock.patch.object(verify_guards.os, "readlink", side_effect=_fake_readlink),
        ):
            self.assertEqual(
                verify_guards._normalize_darwin_system_prefix(Path("/var/folders/xx/cert.json")),
                Path("/private/var/folders/xx/cert.json"),
            )
            self.assertEqual(
                verify_guards._normalize_darwin_system_prefix(Path("/tmp/cert.json")),
                Path("/private/tmp/cert.json"),
            )
            self.assertEqual(verify_guards._normalize_darwin_system_prefix(Path("/tmp")), Path("/tmp"))
            self.assertEqual(
                verify_guards._normalize_darwin_system_prefix(Path("/tmp/../etc/passwd")),
                Path("/tmp/../etc/passwd"),
            )
            fake_symlinks = {Path("/var"), Path("/tmp"), Path("/private/var/folders/xx/evil_link")}
            with mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p in fake_symlinks):
                verify_guards.reject_symlinks_on_path(Path("/var/folders/xx/cert.json"))
                verify_guards.reject_symlinks_on_path(Path("/tmp/cert.json"))
                with self.assertRaises(ValueError):
                    verify_guards.reject_symlinks_on_path(Path("/var/folders/xx/evil_link/cert.json"))
                with self.assertRaises(ValueError):
                    verify_guards.reject_symlinks_on_path(Path("/tmp"))

        with (
            mock.patch.object(verify_guards.sys, "platform", "darwin"),
            mock.patch.object(verify_guards.os, "lstat", return_value=user_lnk),
            mock.patch.object(verify_guards.os, "readlink", side_effect=_fake_readlink),
            mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == Path("/var")),
        ):
            with self.assertRaises(ValueError):
                verify_guards.reject_symlinks_on_path(Path("/var/folders/xx/cert.json"))

        with (
            mock.patch.object(verify_guards.sys, "platform", "darwin"),
            mock.patch.object(verify_guards.os, "lstat", return_value=root_lnk),
            mock.patch.object(verify_guards.os, "readlink", return_value="private/evil"),
            mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == Path("/var")),
        ):
            with self.assertRaises(ValueError):
                verify_guards.reject_symlinks_on_path(Path("/var/folders/xx/cert.json"))

        with (
            mock.patch.object(verify_guards.sys, "platform", "linux"),
            mock.patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == Path("/var")),
        ):
            with self.assertRaises(ValueError):
                verify_guards.reject_symlinks_on_path(Path("/var/folders/xx/cert.json"))


if __name__ == "__main__":
    unittest.main()
