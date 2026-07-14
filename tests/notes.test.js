const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const source = fs.readFileSync(path.join(__dirname, "..", "assets", "notes.js"), "utf8");

const sandbox = {
    console,
    window: {
        __NOTES_TEST_HOOKS__: true,
        addEventListener() {},
    },
    document: {
        querySelector() {
            return null;
        },
    },
};
sandbox.globalThis = sandbox;
vm.runInNewContext(source, sandbox, {filename: "notes.js"});

const internals = sandbox.window.__notesInternals;
assert(internals, "notes internals should be exposed in test mode");

const sanitized = internals.sanitizeNoteHtml('<script>alert(1)</script><p onclick="x">Hello</p><a href="javascript:alert(1)">bad</a>');
assert(!sanitized.includes("script"));
assert(!sanitized.includes("onclick"));
assert(!sanitized.includes("javascript:"));
assert(sanitized.includes("Hello"));

assert.strictEqual(internals.noteTitleFromHtml("<h1>Mission Brief</h1><p>Body</p>"), "Mission Brief");
assert.strictEqual(internals.noteTitleFromHtml("<p>   </p>"), "Untitled note");

console.log("notes frontend tests passed");