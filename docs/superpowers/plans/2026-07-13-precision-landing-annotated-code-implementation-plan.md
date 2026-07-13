# Precision Landing Annotated Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an executable, beginner-oriented annotated Python copy of the MQTT ArUco precision-landing program without changing its runtime behavior.

**Architecture:** Keep `raw/precision-landing-mqtt-code.txt` as the immutable source and create `raw/precision-landing-mqtt-code-annotated.py`. Add layered teaching comments around existing code, then verify behavior preservation by comparing Python ASTs after stripping docstrings.

**Tech Stack:** Python 3, `ast`, `py_compile`, OpenCV/Aruco concepts, MQTT concepts

---

### Task 1: Establish the Annotated Copy and Equivalence Check

**Files:**
- Read: `raw/precision-landing-mqtt-code.txt`
- Create: `raw/precision-landing-mqtt-code-annotated.py`

- [ ] **Step 1: Copy the source through an additive patch**

Create the annotated `.py` file with exactly the executable contents of the `.txt` source. Do not modify the source file.

- [ ] **Step 2: Compile the baseline copy**

Run:

```powershell
python -m py_compile raw/precision-landing-mqtt-code-annotated.py
```

Expected: exit code `0`. This check imports no flight libraries and sends no MQTT commands.

- [ ] **Step 3: Compare normalized ASTs**

Run a PowerShell inline Python command that parses both files, removes module/class/function docstring expression nodes recursively, and compares `ast.dump(..., include_attributes=False)`.

Expected output:

```text
AST_EQUIVALENT=True
```

### Task 2: Add System, Data Model, and MQTT Teaching Comments

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py:1-805`

- [ ] **Step 1: Add the file-level learning guide**

Explain the video-to-control data flow, the difference between a requested velocity and a virtual joystick value, physical units, coordinate/sign caveats, and the live-hardware safety warning.

- [ ] **Step 2: Document the data containers and MQTT adapter**

Add beginner-facing explanations for `ControlCommand`, `DetectionResult`, MQTT topics, request IDs, OSD state, reply correlation, control ownership, readiness checks, and startup/interrupt restoration.

- [ ] **Step 3: Explain command conversion and minimum-effective-stick compensation**

Document velocity clipping, linear conversion to joystick values, dead-zone compensation, `hold` versus `pulse`, keepalive suppression, and the three supported motion-control methods.

- [ ] **Step 4: Re-run compile and AST equivalence checks**

Expected: compilation succeeds and `AST_EQUIVALENT=True`.

### Task 3: Add Precision-Landing Controller Teaching Comments

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py` around class `ArucoLandingController`

- [ ] **Step 1: Explain controller state and coordinate conventions**

Document `SEARCH`, `ALIGN`, `DESCEND`, and `LAND`; camera pixel coordinates; body-frame commands; altitude sources; mechanical offsets; and stage-specific thresholds.

- [ ] **Step 2: Explain filtering and pixel-to-motion formulas**

Show the low-pass relation

```text
filtered = (1 - alpha) * previous + alpha * current
```

and the pinhole approximations

```text
body_x ~= camera_height * pixel_dv / fy
body_y ~= camera_height * pixel_du / fx
height ~= fx * marker_size / marker_pixel_width
```

State their assumptions and limitations without changing the implementation.

- [ ] **Step 3: Explain timed measure-actuate control**

Document measurement averaging, meter-level deadband, minimum stick and wind bias, estimated effective speed, bounded actuation duration, single-axis versus multi-axis control, and online response-gain adaptation. Explicitly distinguish this method from PID.

- [ ] **Step 4: Explain transitions, loss behavior, landing, and touchdown**

Annotate every state branch and safety gate, including startup guard, marker loss, staged descent, autonomous-mode blocking, command-rate limiting, touchdown confirmation, timeout finalization, and disarm cleanup.

- [ ] **Step 5: Re-run compile and AST equivalence checks**

Expected: compilation succeeds and `AST_EQUIVALENT=True`.

### Task 4: Add Video, Configuration, and Runtime Teaching Comments

**Files:**
- Modify: `raw/precision-landing-mqtt-code-annotated.py` around `OpenCVVideoSource`, `TailH264Source`, `build_parser`, and runtime entry points

- [ ] **Step 1: Explain the two video paths**

Document direct OpenCV capture and the three-thread H264 tailing pipeline: growing file to FFmpeg stdin, decoded BGR frames from stdout, and error collection from stderr. Explain file rotation, truncation, warm history, and live-data gating.

- [ ] **Step 2: Group configuration parameters**

Add section comments for input/camera geometry, marker detection, height geometry, timed controller, landing stages, MQTT/control ownership, joystick dead zones, command scheduling, touchdown, and FFmpeg tailing.

- [ ] **Step 3: Explain the runtime loops and cleanup**

Document initialization order, frame processing, preview handling, landing finalization, exception recovery, and why `run_with_interrupt_cleanup()` is the active entry point while `main()` is retained.

- [ ] **Step 4: Run final verification**

Run compilation, normalized AST comparison, `git diff --check`, and confirm `git diff -- raw/precision-landing-mqtt-code.txt` is empty.

Expected: all commands exit `0`, AST equivalence is true, and the original source has no diff.

- [ ] **Step 5: Review annotation coverage**

Use `rg` to confirm that all classes and major control functions have nearby Chinese documentation, and manually scan the beginning of each major section for readable progression and no misleading safety claims.

