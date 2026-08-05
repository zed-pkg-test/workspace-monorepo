from __future__ import annotations

import json
import stat
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REPOSITORY = "https://github.com/zed-pkg-test/workspace-monorepo"
EXPECTED_MEMBERS = {
    "zedtest/ws-core": Path("packages/core"),
    "zedtest/ws-utils": Path("packages/utils"),
    "zedtest/ws-cli": Path("apps/cli"),
}


def read_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def package_identity(manifest: dict) -> str:
    package = manifest["package"]
    return f"{package['org']}/{package['name']}"


def discover_members() -> dict[str, Path]:
    root_manifest = read_toml(ROOT / ".zpkg.toml")
    discovered: dict[str, Path] = {}
    for pattern in root_manifest["workspace"]["members"]:
        for directory in sorted(ROOT.glob(pattern)):
            manifest_path = directory / ".zpkg.toml"
            if manifest_path.is_file():
                discovered[package_identity(read_toml(manifest_path))] = (
                    directory.relative_to(ROOT)
                )
    return discovered


def dependency_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for identity, relative in discover_members().items():
        manifest = read_toml(ROOT / relative / ".zpkg.toml")
        graph[identity] = set((manifest.get("dependencies") or {}).keys())
    return graph


def transitive_dependencies(graph: dict[str, set[str]], start: str) -> set[str]:
    result: set[str] = set()
    stack = list(graph[start])
    while stack:
        dependency = stack.pop()
        if dependency in result:
            continue
        result.add(dependency)
        stack.extend(graph.get(dependency, set()))
    return result


class WorkspaceRootContractTests(unittest.TestCase):
    def test_root_package_identity_is_stable(self) -> None:
        manifest = read_toml(ROOT / ".zpkg.toml")
        self.assertEqual(package_identity(manifest), "zedtest/workspace-monorepo")
        self.assertEqual(manifest["package"]["version"], "0.1.0")

    def test_member_globs_are_explicit_and_ordered(self) -> None:
        manifest = read_toml(ROOT / ".zpkg.toml")
        self.assertEqual(
            manifest["workspace"]["members"],
            ["packages/*", "apps/*"],
        )

    def test_member_globs_resolve_to_exact_fixture_set(self) -> None:
        self.assertEqual(discover_members(), EXPECTED_MEMBERS)

    def test_every_member_path_stays_below_workspace_root(self) -> None:
        root = ROOT.resolve()
        for relative in discover_members().values():
            with self.subTest(member=relative.as_posix()):
                resolved = (ROOT / relative).resolve()
                self.assertTrue(resolved.is_relative_to(root))
                self.assertNotEqual(resolved, root)

    def test_every_member_has_a_manifest_and_package_json(self) -> None:
        for relative in discover_members().values():
            with self.subTest(member=relative.as_posix()):
                self.assertTrue((ROOT / relative / ".zpkg.toml").is_file())
                self.assertTrue((ROOT / relative / "package.json").is_file())

    def test_member_identities_are_unique(self) -> None:
        identities = list(discover_members())
        self.assertEqual(len(identities), len(set(identities)))

    def test_all_members_use_one_version(self) -> None:
        versions = {
            read_toml(ROOT / relative / ".zpkg.toml")["package"]["version"]
            for relative in discover_members().values()
        }
        self.assertEqual(versions, {"0.1.0"})

    def test_all_members_point_to_canonical_repository(self) -> None:
        for relative in discover_members().values():
            with self.subTest(member=relative.as_posix()):
                manifest = read_toml(ROOT / relative / ".zpkg.toml")
                self.assertEqual(
                    manifest["package"]["repository"],
                    {"vcs": "git", "url": EXPECTED_REPOSITORY},
                )


class WorkspaceDependencyGraphTests(unittest.TestCase):
    def test_core_is_the_dependency_leaf(self) -> None:
        self.assertEqual(dependency_graph()["zedtest/ws-core"], set())

    def test_utils_depends_exactly_on_core(self) -> None:
        manifest = read_toml(ROOT / "packages/utils/.zpkg.toml")
        self.assertEqual(
            manifest["dependencies"],
            {"zedtest/ws-core": "^0.1.0"},
        )

    def test_cli_depends_exactly_on_utils(self) -> None:
        manifest = read_toml(ROOT / "apps/cli/.zpkg.toml")
        self.assertEqual(
            manifest["dependencies"],
            {"zedtest/ws-utils": "^0.1.0"},
        )

    def test_every_dependency_is_another_workspace_member(self) -> None:
        graph = dependency_graph()
        members = set(graph)
        for package, dependencies in graph.items():
            with self.subTest(package=package):
                self.assertLessEqual(dependencies, members)

    def test_dependency_graph_is_acyclic(self) -> None:
        graph = dependency_graph()
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                self.fail(f"workspace dependency cycle reaches {node}")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)
        self.assertEqual(visited, set(graph))

    def test_cli_transitively_reaches_core(self) -> None:
        self.assertEqual(
            transitive_dependencies(dependency_graph(), "zedtest/ws-cli"),
            {"zedtest/ws-utils", "zedtest/ws-core"},
        )

    def test_only_consumers_request_node_wiring(self) -> None:
        adapters = {}
        for identity, relative in discover_members().items():
            manifest = read_toml(ROOT / relative / ".zpkg.toml")
            adapters[identity] = (manifest.get("install") or {}).get("adapter")
        self.assertEqual(
            adapters,
            {
                "zedtest/ws-core": None,
                "zedtest/ws-utils": "node",
                "zedtest/ws-cli": "node",
            },
        )


class WorkspaceRuntimeMetadataTests(unittest.TestCase):
    def test_package_json_names_match_zed_identities(self) -> None:
        for identity, relative in discover_members().items():
            with self.subTest(package=identity):
                package_json = json.loads(
                    (ROOT / relative / "package.json").read_text(encoding="utf-8")
                )
                self.assertEqual(package_json["name"], f"@{identity}")

    def test_package_json_versions_match_zed_versions(self) -> None:
        for identity, relative in discover_members().items():
            with self.subTest(package=identity):
                manifest = read_toml(ROOT / relative / ".zpkg.toml")
                package_json = json.loads(
                    (ROOT / relative / "package.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    package_json["version"],
                    manifest["package"]["version"],
                )

    def test_cli_bin_metadata_matches_zed_manifest(self) -> None:
        manifest = read_toml(ROOT / "apps/cli/.zpkg.toml")
        package_json = json.loads(
            (ROOT / "apps/cli/package.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["bin"], {"ws-cli": "bin/cli.js"})
        self.assertEqual(package_json["bin"], manifest["bin"])

    def test_cli_entrypoint_exists_and_is_executable(self) -> None:
        entrypoint = ROOT / "apps/cli/bin/cli.js"
        self.assertTrue(entrypoint.is_file())
        self.assertTrue(entrypoint.stat().st_mode & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
