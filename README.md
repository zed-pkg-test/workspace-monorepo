# workspace-monorepo

**One repo, several independent packages** — the `[workspace]` mechanism, which
is a different thing from `[targets]`:

| | `[targets]` | `[workspace]` |
| --- | --- | --- |
| Models | one package shipping several languages | one repo shipping several packages |
| Manifests | exactly one, at the repo root | one per member, plus the root |
| Fixture | [`polyglot-lib`](https://github.com/zed-pkg-test/polyglot-lib), [`awkward-lib`](https://github.com/zed-pkg-test/awkward-lib) | this repo |

```
.zpkg.toml              [workspace] members = ["packages/*", "apps/*"]
packages/core/          zedtest/ws-core    (no dependencies)
packages/utils/         zedtest/ws-utils   -> ws-core
apps/cli/               zedtest/ws-cli     -> ws-utils, and a [bin]
```

`members` are glob patterns. `zed install` from any member walks up to the root,
resolves every member against one store, writes one `.zpkg.lock`, and links
member→member dependencies straight to the member source directory. An edit in
`packages/core` is visible to `apps/cli` with no publish step in between — while
the manifests still say `"zedtest/ws-core" = "^0.1.0"`, so the same member
published standalone resolves through the registry without changing shape.

## What is verified

Member resolution works. From `apps/cli`, against a registry that does not
contain these packages at all:

```console
$ zed install
installed zedtest/ws-core@workspace
installed zedtest/ws-utils@workspace
2 package(s) in zed_modules/ (symlinked from the global store)

$ ls -l zed_modules/zedtest/
ws-core  -> /…/workspace-monorepo/packages/core
ws-utils -> /…/workspace-monorepo/packages/utils
```

The `@workspace` version and the symlink targets are the proof: both resolved by
path, transitively (`ws-cli` never names `ws-core`), with no registry round-trip.

## The gap this fixture exists to catch

Workspace members are placed on disk but **omitted from the adapter wiring and
from the paths index**. Verified against `zed 0.1.0` and Node 22:

```console
$ cat .zed/paths.json
{ "modules_dir": "zed_modules", "packages": [] }     # <- empty

$ ls .zed/
paths.json                                            # <- no node_path

$ node bin/cli.js
Error: Cannot find module '@zedtest/ws-utils'
```

A registry install of the same dependency writes `node_modules/@org/name` links
and `.zed/node_path`; a workspace install writes neither, so a Node, Python, Go
or Dart consumer inside a workspace receives source it cannot import.

In `zed-cli`, the registry install loop pushes each package into
`wired_packages` and `wired_roots` — the inputs to `write_paths_index` and
`write_toolchain_wiring`. The `workspace_links` loop that runs just after it
creates the symlink and collects `[bin]` entries, but pushes to neither. That
omission is the whole bug.

There is a second, subtler part. Node resolves modules from a symlink's
**realpath**, so links have to be hoisted to the *workspace root*, not the
consuming member: from `packages/utils/`, Node searches
`packages/utils/node_modules`, `packages/node_modules`, `<root>/node_modules` —
never `apps/cli/node_modules`. Linking at the member fixes the direct dependency
and still fails the transitive one:

```console
$ # links in apps/cli/node_modules
Error: Cannot find module '@zedtest/ws-core'
Require stack:
- /…/workspace-monorepo/packages/utils/src/index.js

$ # links in <workspace root>/node_modules
HELLO WORKSPACE FROM WS-CORE!
OK: member -> member -> member resolved by path
```

So the design is sound and the member graph resolves correctly — only the wiring
step is missing, and when it is added it must hoist to the workspace root. The CI
here asserts the current (broken) behaviour explicitly; **when it is fixed those
steps should fail**, and the fixture should be updated rather than deleted.

## License

MIT
