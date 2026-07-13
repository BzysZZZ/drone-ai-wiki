# Precision Landing Annotated Code Design

## Goal

Create a beginner-oriented annotated copy of `raw/precision-landing-mqtt-code.txt` without modifying the original field code. The reader is assumed to know basic Python but almost no flight-control theory.

## Output

Create `raw/precision-landing-mqtt-code-annotated.py` as an executable Python copy of the source. Preserve every executable statement and default value. Only comments, docstrings, and blank lines may be added.

## Annotation Strategy

Use layered comments instead of commenting every obvious assignment:

1. Add a file-level reading guide covering the system data flow, coordinate systems, command signs, state machine, and safety warning.
2. Add class-level docstrings explaining responsibility, dependencies, and how each class participates in landing.
3. Add function-level docstrings for all non-trivial functions, including inputs, outputs, side effects, and the control concept involved.
4. Add block comments before formulas, state transitions, MQTT ownership operations, concurrency logic, and safety gates.
5. Add short inline comments only where a variable's physical meaning, unit, coordinate frame, or sign is otherwise unclear.
6. Group command-line arguments with section comments and explain how groups affect the control system without duplicating every existing `help` string.

## Teaching Content

The annotated copy will explain:

- The end-to-end path from video bytes to a flight-control command.
- Camera pixel coordinates, body coordinates, focal lengths, and axis/sign conversion.
- ArUco center detection and the pinhole-model height approximation.
- Why this implementation is timed measure-actuate control rather than PID.
- The `SEARCH`, `ALIGN`, `DESCEND`, and `LAND` states and their transition conditions.
- High, middle, and final altitude stages and their different tolerances.
- Deadbands, minimum effective joystick values, pulse/hold compensation, clipping, low-pass filtering, and command-rate gates.
- MQTT request/reply correlation, OSD readiness, control ownership, landing cleanup, and interrupt recovery.
- OpenCV input versus low-latency tailing of a growing H264 file through FFmpeg.
- Known assumptions and limitations, marked as learning notes rather than silently changing behavior.

## Safety And Scope

- Do not change the original `.txt` file.
- Do not fix bugs or refactor duplicated logic in this task.
- Do not change the broker, product ID, thresholds, default-enabled flags, formulas, or state transitions.
- Clearly warn that the annotated file still contains live MQTT defaults and must not be executed against real hardware without bench testing and verified failsafes.
- Clearly distinguish observations about the existing design from guarantees about flight safety.

## Verification

1. Compile the annotated copy with Python's `py_compile` module.
2. Parse both files with Python's AST and compare normalized executable structure after removing docstrings, proving that comments and teaching docstrings did not alter behavior.
3. Confirm the original source has no diff.
4. Review the annotated file for coverage of every class, the main control functions, input sources, parser groups, and runtime cleanup path.

