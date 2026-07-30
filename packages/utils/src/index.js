// Depends on a sibling member. In the workspace this resolves to
// ../../packages/core by path; for an outside consumer it resolves from the
// registry. The import statement is identical either way.
const core = require("@zedtest/ws-core");

module.exports.shout = (who) => `${core.greet(who).toUpperCase()}!`;
module.exports.MEMBER = "ws-utils";
module.exports.CORE_MEMBER = core.MEMBER;
