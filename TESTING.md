# Workspace fixture tests

This fixture has two complementary test layers.

## Named contract tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.cjs
```

The 19-test Python suite checks the workspace manifest, member discovery,
package identity, dependency graph, version alignment, repository metadata,
Node adapter declarations, and executable metadata.

The seven-test Node suite copies the fixture into a fresh temporary directory
for each runtime scenario. It verifies the complete
`ws-cli -> ws-utils -> ws-core` chain, deterministic output, correct symlink
targets, fail-closed behavior when either workspace link is absent, and the
current consumer-local symlink realpath boundary. It never writes
`node_modules` into the checked-out fixture.

## Real zed CLI E2E

`.github/workflows/ci.yml` remains the product boundary. It builds the current
Rust CLI and installs from `apps/cli` against an empty registry. The workflow
then verifies:

- direct and transitive workspace packages resolve by source path;
- `.zed/paths.json`, `.zed/node_path`, `zed_modules`, and consumer-local Node
  projections contain the expected package identities and source targets;
- full uninstall removes generated package and adapter projections while
  retaining the manifest and lock byte-for-byte;
- `zed install --frozen` restores the exact workspace graph without registry
  packages;
- the remaining Node limitation is specifically transitive lookup from a
  symlinked member's real path, and workspace-root wiring completes the chain.

The remaining-gap assertion is intentionally fail-closed. When root-aware Node
wiring lands in `zed`, CI will fail until this fixture is updated to assert the
new zero-touch success path.
