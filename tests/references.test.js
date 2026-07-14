const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "assets", "references.js"), "utf8");

function loadInternals() {
    const sandbox = {
        console,
        URL,
        window: {
            __REFERENCE_LIBRARY_TEST_HOOKS__: true,
            addEventListener() {},
        },
        document: {
            querySelector() {
                return null;
            },
        },
    };
    sandbox.globalThis = sandbox;
    vm.runInNewContext(source, sandbox, {filename: "references.js"});
    return sandbox.window.__referenceLibraryInternals;
}

const internals = loadInternals();
assert(internals, "reference library test hooks should be exposed in test mode");

const parsed = internals.parseReferences(`
https://docs.px4.io/
PX4 官方文档 https://docs.px4.io/ #px4 #飞控 官方入口
https://docs.ros.org/ ROS2 教程 #ros2 从基础节点开始看
- [MAVSDK](https://mavsdk.mavlink.io/) #mavsdk SDK 文档
`);

assert.strictEqual(parsed.items.length, 4);
assert.strictEqual(parsed.warnings.length, 0);
assert.strictEqual(parsed.items[0].title, "docs.px4.io");
assert.strictEqual(parsed.items[0].url, "https://docs.px4.io/");
assert.deepStrictEqual(Array.from(parsed.items[1].tags), ["px4", "飞控"]);
assert.strictEqual(parsed.items[1].note, "官方入口");
assert.strictEqual(parsed.items[2].title, "ROS2 教程");
assert.strictEqual(parsed.items[2].note, "从基础节点开始看");
assert.strictEqual(parsed.items[3].title, "MAVSDK");

assert.strictEqual(
    internals.formatReferenceLine({
        title: "PX4 官方文档",
        url: "https://docs.px4.io/",
        tags: "px4 飞控",
        note: "官方入口",
    }),
    "- [PX4 官方文档](https://docs.px4.io/) #px4 #飞控 官方入口"
);

assert.strictEqual(
    internals.appendReferenceLine("现有内容", {
        title: "ROS2",
        url: "https://docs.ros.org/",
        tags: "#ros2",
        note: "",
    }),
    "现有内容\n- [ROS2](https://docs.ros.org/) #ros2"
);

console.log("references parser tests passed");
