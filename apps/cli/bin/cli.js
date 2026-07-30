#!/usr/bin/env node
// Consumes a member two hops away (ws-utils -> ws-core) and proves the whole
// chain resolved from workspace paths rather than the registry.
const utils = require("@zedtest/ws-utils");

const out = utils.shout("workspace");
console.log(out);
if (utils.CORE_MEMBER !== "ws-core") {
  console.error(`FAIL: transitive member did not resolve: ${utils.CORE_MEMBER}`);
  process.exit(1);
}
console.log("OK: member -> member -> member resolved by path");
