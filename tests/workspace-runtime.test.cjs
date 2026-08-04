const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const ROOT = path.resolve(__dirname, "..");

function stageWorkspace({ linkCore = true, linkUtils = true } = {}) {
  const staged = fs.mkdtempSync(path.join(os.tmpdir(), "zed-workspace-contract-"));
  fs.cpSync(path.join(ROOT, "packages"), path.join(staged, "packages"), {
    recursive: true,
  });
  fs.cpSync(path.join(ROOT, "apps"), path.join(staged, "apps"), {
    recursive: true,
  });

  const scope = path.join(staged, "node_modules", "@zedtest");
  fs.mkdirSync(scope, { recursive: true });
  if (linkCore) {
    fs.symlinkSync(
      path.join(staged, "packages", "core"),
      path.join(scope, "ws-core"),
      "dir",
    );
  }
  if (linkUtils) {
    fs.symlinkSync(
      path.join(staged, "packages", "utils"),
      path.join(scope, "ws-utils"),
      "dir",
    );
  }
  return staged;
}

function runCli(root) {
  return spawnSync(process.execPath, ["apps/cli/bin/cli.js"], {
    cwd: root,
    encoding: "utf8",
  });
}

test("ws-core exposes the stable leaf API", () => {
  const core = require(path.join(ROOT, "packages", "core", "src", "index.js"));
  assert.equal(core.MEMBER, "ws-core");
  assert.equal(core.greet("zed"), "hello zed from ws-core");
});

test("hoisted workspace links execute the complete two-hop chain", (t) => {
  const staged = stageWorkspace();
  t.after(() => fs.rmSync(staged, { recursive: true, force: true }));

  const result = runCli(staged);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(
    result.stdout,
    [
      "HELLO WORKSPACE FROM WS-CORE!",
      "OK: member -> member -> member resolved by path",
      "",
    ].join("\n"),
  );
});

test("missing direct ws-utils wiring fails closed", (t) => {
  const staged = stageWorkspace({ linkUtils: false });
  t.after(() => fs.rmSync(staged, { recursive: true, force: true }));

  const result = runCli(staged);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Cannot find module '@zedtest\/ws-utils'/);
});

test("missing transitive ws-core wiring fails closed", (t) => {
  const staged = stageWorkspace({ linkCore: false });
  t.after(() => fs.rmSync(staged, { recursive: true, force: true }));

  const result = runCli(staged);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Cannot find module '@zedtest\/ws-core'/);
});

test("hoisted links resolve to the intended member directories", (t) => {
  const staged = stageWorkspace();
  t.after(() => fs.rmSync(staged, { recursive: true, force: true }));

  const scope = path.join(staged, "node_modules", "@zedtest");
  assert.equal(
    fs.realpathSync(path.join(scope, "ws-core")),
    fs.realpathSync(path.join(staged, "packages", "core")),
  );
  assert.equal(
    fs.realpathSync(path.join(scope, "ws-utils")),
    fs.realpathSync(path.join(staged, "packages", "utils")),
  );
});

test("workspace CLI output is deterministic across fresh processes", (t) => {
  const staged = stageWorkspace();
  t.after(() => fs.rmSync(staged, { recursive: true, force: true }));

  const first = runCli(staged);
  const second = runCli(staged);
  assert.equal(first.status, 0, first.stderr);
  assert.equal(second.status, 0, second.stderr);
  assert.equal(second.stdout, first.stdout);
});
