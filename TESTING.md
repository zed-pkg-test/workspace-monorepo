# Workspace fixture tests

This fixture has two complementary test layers.

## Named contract tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.cjs
```

The Python suite checks the workspace manifest, member discovery, package
identity, dependency graph, version alignment, repository metadata, Node
adapter declarations, and executable metadata.

The Node suite copies the fixture into a fresh temporary directory for each
runtime scenario. It verifies the complete `ws-cli -> ws-utils -> ws-core`
chain, deterministic output, correct symlink targets, and fail-closed behavior
when either the direct or transitive workspace link is absent. It never writes
`node_modules` into the checked-out fixture.

## Real zed CLI E2E

`.github/workflows/ci.yml` remains the product boundary. It builds the current
Rust CLI, installs from `apps/cli` against an empty registry, verifies
workspace-path resolution, records the known adapter-wiring gap, and proves the
same chain works when the expected root wiring is supplied.

The named tests make fixture regressions fast and diagnosable; the existing
workflow continues to prove the actual `zed install` behavior.
