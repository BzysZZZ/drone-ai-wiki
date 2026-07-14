# Precision Landing Deep Annotations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the precision-landing learning edition with 800 to 1200 lines of rigorous beginner-facing comments while preserving executable behavior exactly.

**Architecture:** Modify only `raw/precision-landing-mqtt-code-annotated.py` in five annotation batches. After every batch, compile the file and compare its normalized AST against `raw/precision-landing-mqtt-code.txt`; comments may expand understanding but never change runtime structure.

**Tech Stack:** Python 3, Python `ast`, OpenCV/Aruco mathematics, MQTT, FFmpeg, flight-control state machines

---

### Task 1: Establish Baseline And Documentation Inventory

**Files:**
- Read: `raw/precision-landing-mqtt-code.txt`
- Modify: `raw/precision-landing-mqtt-code-annotated.py`

- [ ] **Step 1: Record the baseline**

Count source lines, annotated lines, Chinese comment lines, classes, functions, and parser arguments. Save the command output in the task notes so final coverage can be compared numerically.

- [ ] **Step 2: Verify the existing learning edition**

Run `py_compile`, normalized AST comparison, and `git diff --check` before editing. Expected results are successful compilation, `AST_EQUIVALENT=True`, and no whitespace errors.

- [ ] **Step 3: Build a function coverage inventory**

Use `rg` to list every class and function. Classify each non-trivial function into MQTT/control ownership, control mathematics, state machine, video input, configuration, or runtime cleanup. Every inventory item must receive nearby teaching documentation in Tasks 2 through 5.

### Task 2: Deepen Data Model, MQTT, And Control-Ownership Comments

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py` from imports through `MqttAdapter.shutdown_after_land`

- [ ] **Step 1: Expand the file-level architecture guide**

Document the complete video-to-flight-command path, threads, feedback loops, data units, coordinate frames, control modes, and safe reading order. Include a warning that importing is inert but running the script can contact the configured broker.

- [ ] **Step 2: Document all MQTT adapter functions**

For each non-trivial method, add responsibility, caller, inputs, outputs, changed state, blocking behavior, and failure behavior. Explain the three topics, JSON envelope, `tid` correlation, callback threading, QoS versus application replies, and stale OSD concerns.

- [ ] **Step 3: Derive command conversion and dead-zone compensation**

Explain velocity clipping, asymmetric climb/descent limits, joystick scaling, sign conversion, hold compensation, pulse duty cycle, keepalive, and command suppression. Include numerical examples for velocity-to-stick conversion and pulse averaging.

- [ ] **Step 4: Explain ownership and cleanup**

Explain startup snapshots, mode normalization, autonomous-mode protection, joystick/PVA readiness, command rejection holdoff, repeated zero commands, land versus negative vertical velocity, disarm, and restoration order.

- [ ] **Step 5: Verify Task 2**

Run compilation, AST equality, whitespace checks, and an inventory check for every `MqttAdapter` method.

### Task 3: Deepen Vision, Geometry, Filtering, And Timed-Control Comments

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py` in `ArucoLandingController` before `update`

- [ ] **Step 1: Define all coordinate systems**

Explain image `(u,v)`, camera optical geometry, approximate body `(x,y,z)`, joystick axes, yaw compensation, swap/invert flags, mechanical offsets, and sign-verification procedures. Include a worked pixel-to-body example.

- [ ] **Step 2: Derive vision equations**

Explain ArUco corner averaging, pixel width, pinhole marker-height estimation, horizontal-distance estimation, focal length units, fronto-parallel assumptions, distortion and attitude errors, and why solvePnP/EKF would be stronger alternatives.

- [ ] **Step 3: Derive filtering and stage scaling**

Explain first-order low-pass filtering with at least two alpha examples, command smoothing, high/mid/final stage thresholds, pixel tolerance versus meter tolerance, and the noise-delay trade-off.

- [ ] **Step 4: Derive measure-actuate control**

Explain sample averaging, deadband subtraction, minimum stick, wind bias, theoretical and effective speed, bounded `time = distance / speed`, single-axis and multi-axis plans, overshoot handling, and response-gain adaptation. Include one complete numerical actuation-plan example.

- [ ] **Step 5: Verify Task 3**

Run compilation, AST equality, whitespace checks, and searches proving each required formula and numerical example is present.

### Task 4: Deepen State-Machine And Safety-Gate Comments

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py` from `detect` through `draw_overlay`

- [ ] **Step 1: Explain detection and startup safety**

Document marker selection, current-frame detection versus timeout freshness, startup guard, selected height source, stale measurement risks, and vision-loss braking.

- [ ] **Step 2: Explain every state branch**

For `SEARCH`, `ALIGN`, `DESCEND`, and `LAND`, document entry, active command, exit, fallback, physical reason, and unsafe threshold cases. Expand the nested ALIGN measure/actuate phases and explain why this is not continuous PID.

- [ ] **Step 3: Explain command scheduling gates**

Document control rate, minimum interval, frame gap, epsilon change detection, autonomous-mode blocking, recent rejection holdoff, OSD readiness, idle zero commands, near-center pause, and keepalive interaction.

- [ ] **Step 4: Explain touchdown and finalization risks**

Document height and vertical-speed confirmation, persistence timing, missing-speed behavior, force-land paths, timeout finalization, disarm risk, and why these thresholds require hardware-specific tests.

- [ ] **Step 5: Verify Task 4**

Run compilation, AST equality, whitespace checks, and a four-state documentation audit.

### Task 5: Deepen Video Pipeline, Parameters, Runtime, And Limitations

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py` from `OpenCVVideoSource` through the active entry point

- [ ] **Step 1: Explain both video paths**

Document OpenCV capture timestamps and buffering, growing-file tailing, FFmpeg stdin/stdout/stderr, fixed BGR frame sizes, partial reads, three background threads, Condition signaling, latest-frame semantics, rotation, truncation, and cleanup.

- [ ] **Step 2: Explain H264 startup and latency**

Explain SPS, PPS, IDR, warm history, live-data gating, `probesize`, `analyzeduration`, flush behavior, frame dropping, CPU versus latency, and why stale frames are dangerous to control.

- [ ] **Step 3: Add parameter tuning guidance**

For every existing parameter group, explain physical meaning, effects of increasing/decreasing values, important couplings, and high-risk settings. Explicitly identify default-true `store_true` options that cannot be disabled through the current CLI.

- [ ] **Step 4: Explain runtime and known limitations**

Document initialization order, active versus duplicate main loop, preview behavior, exception cleanup, and every known limitation listed in the design specification, including ineffective timestamp pruning.

- [ ] **Step 5: Verify Task 5**

Run compilation, AST equality, whitespace checks, parameter-group searches, and known-limitation searches.

### Task 6: Final Coverage And Regression Verification

**Files:**
- Verify: `raw/precision-landing-mqtt-code-annotated.py`
- Verify unchanged: `raw/precision-landing-mqtt-code.txt`

- [ ] **Step 1: Run complete static verification**

Compile the annotated file, require `AST_EQUIVALENT=True`, run `git diff --check`, and require an empty diff for the original `.txt` file.

- [ ] **Step 2: Run repository tests**

Run `python -m unittest server.test_app` with a writable temporary directory. Expected result: all discovered tests pass; record any pre-existing resource warnings separately.

- [ ] **Step 3: Audit specification coverage**

Check every class, non-trivial function, formula, numerical example, state, MQTT concept, video concept, parameter group, and known limitation against the design document. Fix omissions before completion.

- [ ] **Step 4: Compare annotation depth**

Report original lines, final annotated lines, Chinese teaching-comment lines, documented functions, and remaining undocumented functions. The target is 800 to 1200 additional teaching-comment lines with no unexplained non-trivial functions.

### Task 7: Enforce In-Body Comments For Every Function

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py`
- Verify unchanged: `raw/precision-landing-mqtt-code.txt`

- [ ] **Step 1: Run the mechanical function-coverage audit**

Parse the annotated file with Python `ast`. For every `FunctionDef` and `AsyncFunctionDef`, inspect the physical lines after the complete signature and before the first executable statement. A function passes only when that region contains a `#` comment or the function starts with a docstring.

Baseline expected from the reviewed file:

```text
FUNCTIONS=125
MISSING=54
```

- [ ] **Step 2: Document all missing data-model and MQTT methods**

Add in-body Chinese comments to the 29 missing methods from `ControlCommand.__init__` through `MqttAdapter._apply_joystick_z_min_effective`. Simple getters and setters must state their return value or protocol side effect. Wrappers must explain delegation and whether they mutate their input.

For `_apply_joystick_xy_min_effective` and `_apply_joystick_z_min_effective`, explicitly document payload copying, per-axis delegation, configuration fallback order, disabled-compensation behavior, and non-mutation of the caller's dictionary.

- [ ] **Step 3: Verify the MQTT batch**

Run `py_compile`, AST equality, whitespace checks, and the coverage audit. Expected: AST equality remains true and the missing count decreases by exactly the number of newly documented functions.

- [ ] **Step 4: Document all missing controller methods**

Add in-body Chinese comments to the 20 missing `ArucoLandingController` methods, including constructors, height-source getters, stage selectors, command selectors, reset helpers, simple wrappers, state-name helpers, and final-land predicates. Each comment must identify units, return semantics, state reset, or transition role as applicable.

- [ ] **Step 5: Verify the controller batch**

Run `py_compile`, AST equality, whitespace checks, and the coverage audit. Expected: no controller method remains in the missing list.

- [ ] **Step 6: Document all missing video-source methods**

Add in-body Chinese comments to the five missing `OpenCVVideoSource` and `TailH264Source` methods. Explain resource initialization, release behavior, stderr draining, exact-byte reads, and the meaning of constructor state.

- [ ] **Step 7: Enforce zero missing functions**

Run the coverage audit and require exactly:

```text
FUNCTIONS=125
MISSING=0
```

Any missing function blocks completion, even if it is a one-line getter, setter, wrapper, constructor, or callback.

- [ ] **Step 8: Run final regression verification**

Compile the annotated file, require `AST_EQUIVALENT=True`, run `git diff --check`, confirm the original `.txt` has no diff, and run `python -m unittest server.test_app` with a writable temporary directory.
