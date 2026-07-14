# Precision Landing Deep Annotations Design

## Goal

Expand `raw/precision-landing-mqtt-code-annotated.py` into a self-contained learning edition for a reader who understands basic Python but has almost no background in flight control, computer vision, or MQTT control systems.

The existing executable behavior must remain identical to `raw/precision-landing-mqtt-code.txt`.

## Scope

Only the annotated Python copy will change. The original `.txt` source, runtime defaults, formulas, state transitions, broker settings, and control behavior will remain untouched.

The target is approximately 800 to 1200 additional teaching-comment lines beyond the original source. Comment volume is a guide, not the success criterion; coverage and clarity are.

## Annotation Standard

Every non-trivial function will explain:

- Its responsibility in the end-to-end landing pipeline.
- Who calls it and what it calls next.
- Inputs, outputs, units, coordinate frames, and sign conventions.
- State mutations, I/O, thread interactions, and flight-side effects.
- Why the implementation exists and what problem it solves.
- Assumptions, failure modes, and safety limitations.

Obvious Python syntax and direct assignments will not receive repetitive narration.

## Mathematical Explanations

The learning edition will derive and illustrate:

- Pinhole projection and the approximations `height = fx * marker_size / pixel_width` and `distance = height * pixel_error / focal_length`.
- The relationship among image coordinates, camera coordinates, body coordinates, and flight-protocol joystick axes.
- First-order low-pass filtering, including the effect of alpha on noise rejection and delay.
- Velocity clipping and proportional velocity-to-joystick conversion.
- Minimum-effective-stick dead zones, hold compensation, pulse duty cycle, and time-averaged actuation.
- Meter-level deadbands and the timed actuation relation `time = residual_distance / effective_speed`.
- Online axis-response adaptation from predicted versus measured movement.

Each major formula will include at least one concrete numerical example using representative values from the file.

## State-Machine Explanations

The `SEARCH`, `ALIGN`, `DESCEND`, and `LAND` states will each document:

- Entry conditions.
- Commands emitted while active.
- Normal exit conditions.
- Vision-loss, readiness, and timeout behavior.
- Why the transition exists physically.
- Risks produced by incorrect thresholds or stale sensor data.

The comments will explicitly explain the nested `measure` and `actuate` phases inside `ALIGN`, and distinguish this controller from continuous PID control.

## MQTT And Runtime Explanations

The MQTT section will explain:

- Topic roles, JSON envelope fields, `tid` request/reply correlation, QoS limitations, and asynchronous callbacks.
- OSD feedback, flight-mode normalization, control ownership, joystick/PVA readiness, rejection holdoff, and startup restoration.
- Why zero commands are repeated during interruption and landing cleanup.
- The difference among joystick, velocity, target, hold, brake, land, and disarm commands.

The video section will explain:

- Direct OpenCV capture versus tailing a growing H264 file.
- FFmpeg stdin/stdout/stderr roles and the reader, writer, and error threads.
- SPS/PPS/IDR warm history, file rotation, truncation, live-data gating, frame dropping, and latency trade-offs.

## Parameter Guidance

Each parameter group will include guidance about:

- What physical or software behavior it controls.
- The likely effect of increasing or decreasing it.
- Important couplings with other parameters.
- Parameters that can reverse axes, destabilize motion, trigger premature landing, or cause unsafe cleanup.

Existing `argparse` help text will not be mechanically repeated.

## Known Limitations To Explain

Comments will identify, without fixing:

- No calibrated distortion correction, PnP pose estimation, EKF, or full attitude compensation.
- Simplified fronto-parallel marker height estimation.
- No horizontal correction during the `DESCEND` phase.
- Force-land paths that can bypass horizontal alignment.
- Landing-finalization timeout followed by disarm.
- `store_true` options whose defaults are already `True` and therefore lack a CLI disable path.
- Measurement-sample timestamp pruning that is currently ineffective.
- Duplicate `main()` and `run_with_interrupt_cleanup()` loops.

## Verification

1. Compile the learning edition with `py_compile`.
2. Parse the original and annotated files with Python `ast` and require identical normalized executable structure.
3. Run `git diff --check` on the annotated file.
4. Confirm the original `.txt` file has no diff.
5. Run the repository unit tests.
6. Audit every class and non-trivial function for nearby teaching documentation.
7. Audit each required formula, numerical example, state, parameter group, and known limitation against this design.

