from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "check_infra_submodules.py"
SPEC = importlib.util.spec_from_file_location("check_infra_submodules", MODULE_PATH)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)


class RepositoryBoundaryUnitTests(unittest.TestCase):
    def test_remote_parser_supports_common_git_url_forms(self) -> None:
        cases = {
            "git@github.com:org/service-infra.git": "service-infra",
            "ssh://git@github.com/org/service.infra.git": "service.infra",
            "https://github.com/org/service_infra.git": "service_infra",
            "../service-infra.git": "service-infra",
            "https://github.com/org/application.git?x=1": "application",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(GUARD.remote_repository_name(value), expected)

    def test_missing_gitmodules_is_conforming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = pathlib.Path(directory) / ".gitmodules"
            self.assertEqual(GUARD.scan_file(missing), [])

    def test_remote_infra_is_forbidden_even_outside_apps(self) -> None:
        text = '''\
[submodule "deployment"]
    path = vendor/deployment
    url = git@github.com:org/service-infra.git
'''
        findings = GUARD.scan_text(text)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].remote_repository, "service-infra")

    def test_generic_apps_infra_path_is_forbidden(self) -> None:
        text = '''\
[submodule "deployment"]
    path = apps/infra
    url = git@github.com:org/deployment.git
'''
        findings = GUARD.scan_text(text)
        self.assertEqual(len(findings), 1)
        self.assertIn("apps path", findings[0].reasons[0])

    def test_infra_substrings_that_are_not_repository_suffixes_are_allowed(self) -> None:
        text = '''\
[submodule "apps/infrastructure-console"]
    path = apps/infrastructure-console
    url = https://github.com/org/platform-infra-client.git
'''
        self.assertEqual(GUARD.scan_text(text), [])

    def test_missing_required_field_fails_closed(self) -> None:
        text = '''\
[submodule "apps/example"]
    path = apps/example
'''
        with self.assertRaises(GUARD.GitmodulesError):
            GUARD.scan_text(text)

    def test_malformed_git_config_fails_closed(self) -> None:
        with self.assertRaises(GUARD.GitmodulesError):
            GUARD.scan_text('[submodule "broken"\npath = apps/broken\n')


class CurrentFleetSnapshotTests(unittest.TestCase):
    def test_all_known_violating_snapshots_are_rejected(self) -> None:
        fixture_dir = ROOT / "tests" / "fixtures" / "violating"
        fixtures = sorted(fixture_dir.glob("*.gitmodules"))
        self.assertEqual(len(fixtures), 12)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                findings = GUARD.scan_file(fixture)
                self.assertEqual(len(findings), 1)

    def test_representative_conforming_snapshots_are_accepted(self) -> None:
        fixture_dir = ROOT / "tests" / "fixtures" / "conforming"
        fixtures = sorted(fixture_dir.glob("*.gitmodules"))
        self.assertGreaterEqual(len(fixtures), 3)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.name):
                self.assertEqual(GUARD.scan_file(fixture), [])

    def test_cli_exit_codes_and_json_contract(self) -> None:
        good = ROOT / "tests" / "fixtures" / "conforming" / "canonical-cloud__canonical-monorepo.gitmodules"
        bad = ROOT / "tests" / "fixtures" / "violating" / "file-tunnel__ftnl-monorepo.gitmodules"

        good_run = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--json", str(good)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(good_run.returncode, 0, good_run.stderr)
        self.assertIn('"ok": true', good_run.stdout)

        bad_run = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--json", str(bad)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(bad_run.returncode, 1, bad_run.stderr)
        self.assertIn('"ok": false', bad_run.stdout)
        self.assertIn('"path": "apps/infra"', bad_run.stdout)


if __name__ == "__main__":
    unittest.main()
