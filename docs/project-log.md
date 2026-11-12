# VisionBot — Project Log

Running record of every work session. The kid fills the "What we did" parts; keep it short and honest. Judges often ask for exactly this.

**Entry template:**

```
## YYYY-MM-DD — <session title>
**What we did:**
**What broke / how we fixed it:**
**Numbers we used:** (pixel→cm scale, tolerances, PWM)
**Photos:** (file names)
**Next:**
```

---

## 2026-11-12 — Planning day

**What we did:**
- Reviewed the project proposal (Readme.md) and confirmed the build approach.
- Inventoried hardware: ESP32, 2 BO motors + wheels + 1 caster, L298N 2A driver, 4×1.5V cells (6×NiMH 7.2V planned later), Logitech HD 1080p USB webcam, wires.
- Wrote the 2-day build plan: [plan-2day-build.md](plan-2day-build.md).

**Key decisions:**
1. Robot is untethered — ESP32 powered onboard (USB power bank now; L298N 5V-out with the 7.2V NiMH pack later). Laptop ↔ ESP32 over Wi-Fi (UDP); ESP32 creates its own hotspot, so no venue Wi-Fi needed.
2. Slow-and-simple controller: turn-in-place → drive straight → stop. PWM ~40%, angle tolerance 20°, stop tolerance 8 cm.

**Numbers we used:** (none yet — pixel→cm scale and heading calibration happen in Day 1, Block 4)

**Next:** scaffold `code/` — ArUco marker generator, detection test, Wi-Fi drive test, main navigation script, ESP32 firmware.

---

## 2026-11-12 — Wiring plan for 30-pin ESP32

**What we did:** Confirmed the kid's ESP32 is the 30-pin DevKit model. All six chosen signal pins (D32, D33, D25, D26, D27, D14) sit on the same column of that board — no pin changes needed. Wrote [wiring-esp30pin-l298n.md](wiring-esp30pin-l298n.md).

**Key points:** L298N works directly with ESP32's 3.3V logic (no level shifter). Need only: 7 M-F jumper wires, 4×AA holder with switch, power bank + cable, small screwdriver. Remove ENA/ENB jumper caps, keep the 5V cap on, common GND is mandatory.

**Next:** still scaffolding `code/` (marker generator → print markers tonight).

---

## 2026-11-12 — Marker generator + detection test

**What we did:**
- Set up `code/python/` with `requirements.txt` (opencv-python ≥4.8, numpy) and installed into the project `.venv` (Python 3.12).
- Wrote `generate_markers.py` → produced `code/python/markers/`: pure markers (`marker_10_robot.png`, `marker_20_target.png`) and print sheets (`print_10_robot.png`, `print_20_target.png`) with FRONT arrow + instructions.
- Wrote `detect_test.py` — live webcam detection with green/blue boxes, robot→target line, pixel/cm distance, line angle, robot yaw, fps, `s`=snapshot / `q`=quit. Options: `--cam N`, `--scale cm_per_px`, `--flip`.

**What broke / how we fixed it:**
- First generated markers had **no white quiet border** → detector couldn't see them at all. Fixed by padding each marker with a white border (1/8 side). Good lesson for the logbook: ArUco needs white space around the black square.

**Verification (round-trip test passed):**
- Pure PNGs detect as ID 10 / ID 20.
- 120 px marker rotated 90°/180°/270° in a white field: still detected, and yaw reading tracks rotation exactly (−90 → 0 → 90 → 180).
- Full print sheet detects too.

**Numbers we used:** none yet — px→cm scale and N/E/S/W yaw readings get recorded in Day 1 Block 4.

**Printing note:** print `print_*.png` at **100% / "Actual size"** (not "fit to page"); black square should measure ~8×8 cm — measure with a ruler and note the real size here: ______

**Next:** ESP32 firmware (`code/esp32/`) + Wi-Fi drive test (`drive_test.py`).

---

## 2026-11-12 — Camera mounting Q&A (planning)

**Question:** does the camera have to be strictly centered above the arena? (We can't easily build a cage to house it.)

**Answer/decision:** No. Navigation will use a 4-corner perspective calibration (`code/python/calibrate.py`, comes with `main.py`) — click the 4 arena corners once and all positions are reported directly in cm, from ANY mount. So both mounts work:
- **A. Cardboard bridge, centered overhead (~100 cm)** — recommended; best marker detection.
- **B. Angled side mount** on a lamp arm/music stand/tripod at the arena's **short** edge — camera height ≥ the arena dimension pointing away from it (≥ 70–80 cm for the 100×70 arena), because ArUco detection needs to see the marker face at ≤ ~45–55° tilt. The math corrects position, but detection itself can't be fixed by software.

A perfectly-centered camera goes through the same calibration — one code path for every mount, and recalibrating after a bump at the venue is ~1 minute. Bonus talking point if side-mounted: "we correct perspective, the same idea used for aerial maps."

**Plan updated:** plan-2day-build.md §2b (mount options table + rules), Block 4 now uses `calibrate.py` + a 30 cm scale check instead of a single pixel→cm scale.

**Next:** still ESP32 firmware (`code/esp32/`) + Wi-Fi drive test (`drive_test.py`); then `calibrate.py` + `main.py`.

---

## 2026-11-12 — Gradio web UI for the detection test

**What we did:**
- Wrote `detect_ui.py` — the detection test as a browser UI (Gradio 6.31): live arena view with green/blue boxes + robot→target line, big status banner ("BOTH MARKERS DETECTED" / "waiting…"), per-marker badges, live readouts (positions, distance px/cm, line angle, yaw, fps), settings (camera index, cm/px scale, 180° flip) and a snapshot button with gallery. Reuses `ArucoDetector` + geometry from `detect_test.py` — one source of truth.
- Added `gradio>=4.44,<7` to requirements and installed.

**What broke / how we fixed it:**
1. `tick()` read the camera twice per refresh → single `cap.read()` now (~2× faster refresh).
2. Badge bug: `LAST_SEEN` started pre-filled, so a fresh UI showed green "detected" before seeing anything, and markers lost >1 s also showed green. Now: green = seen now, amber = "lost 0.8s" (brief dropout), red = not seen / never seen.
3. Gradio 6 removed `every=` from `demo.load` → falls back to `gr.Timer` automatically (older Gradio still works).

**Verification:** synthetic frame with both markers → IDs 10+20 detected, banner + readouts correct; badge state machine tested for fresh/seen/lost-0.8s/lost-5s; server launched headless, page served with title, closed cleanly.

**How to run:** `python detect_ui.py` (auto-opens http://127.0.0.1:7860). **Only one program may use the webcam** — close `detect_test.py` before starting the UI.

**Next:** ESP32 firmware + `drive_test.py` (Wi-Fi driving test), then `calibrate.py` + `main.py`.

---

## 2026-11-12 — A4 PDF print sheets for the markers

**What we did:** extended `generate_markers.py` to also build `markers/print_a4_markers.pdf` — 2 A4 pages (page 1 = robot marker ID 10, page 2 = target ID 20), each with title, FRONT arrow, the 8 cm marker (white quiet border kept, gray cutting line drawn **outside** the border so the quiet zone survives cutting), an 8.0 cm check bar with 1 cm ticks, and numbered cutting/gluing instructions. Added `pillow` to requirements.txt.

**Verification (passed):**
- PDF MediaBox = 595.2 × 841.92 pt = exactly A4; 2 pages.
- Round-trip: re-ran detection on both composed pages → IDs 10 and 20 detected; black square measures 7.99 × 7.99 cm at 300 dpi.

**Printing note (supersedes the PNG-sheet note above):** print `print_a4_markers.pdf` at **100% / "Actual size"**; after printing, lay a ruler on the check bar — it must read 8.0 cm. Reprint page 2 for spare destination cards. **Keep the white border when cutting** — the detector needs it.

**Next:** ESP32 firmware (`code/esp32/`) + Wi-Fi drive test (`drive_test.py`); then `calibrate.py` + `main.py`.

---

## 2026-11-12 — Board correction: it's a NodeMCU (ESP8266), not an ESP32

**What we did:** While wiring the 4×AA pack + switch + L298N, we caught that the robot board is a **NodeMCU v2 (ESP-12E = ESP8266)** — not a 30-pin ESP32 DevKit as the earlier wiring plan assumed. Both boards have 30 pins, which is how the mix-up happened. The firmware had been right all along: `platformio.ini` → `nodemcuv2`, and the blink test ran on it. Rewrote the wiring guide: [wiring-nodemcu-l298n.md](wiring-nodemcu-l298n.md) (replaces the ESP32 version) and updated plan-2day-build.md + Readme.md to match.

**New pin map (NodeMCU → L298N):** D1→ENA, D2→ENB (the two PWM pins), D5→IN1, D6→IN2, D7→IN3, D0→IN4 (D0 has no PWM — fine for a direction pin). D3/D4/D8 deliberately avoided (boot-strapping pins).

**4×AA alkaline wiring (for now):** pack (+) → [switch] → L298N `+12V`; pack (−) → `GND`; motors → OUT1–4; NodeMCU stays on the USB power bank (the L298N's 5V regulator is unreliable below 7V input). Exhibition: 6×NiMH 7.2V, then L298N `5V` → NodeMCU `VIN`, power bank retired.

**What broke / how we fixed it:** three docs written for the wrong board — all corrected in one pass before any wiring was done. No hardware harm.

**Next:** motor-test firmware in `code/bot-program/bot-code/` (extend the PlatformIO project) + Wi-Fi drive test (`drive_test.py`).

---

## 2026-11-12 — Motor-test firmware (Day 1, Block 2)

**What we did:** Wrote the motor-test firmware into the PlatformIO project `code/bot-program/bot-code/src/main.cpp` — cycles STOP → FORWARD → BACKWARD → LEFT → RIGHT (2 s each, wheels-up test) forever, with serial output (9600 baud) saying what each wheel SHOULD be doing at every step. Wrong-direction wheel = swap that motor's two wires at the L298N terminal (expected once).

**Verification:** compile-verified for `nodemcuv2` (esp8266 core 3.1.2): RAM 35%, flash 22%. Hardware run still to do (Block 2 checklist).

**Numbers we used:** TEST_SPEED = 400/1023 ≈ 40% PWM — matches the plan's starting value.

**Next:** upload via PlatformIO (→ Upload, monitor 9600), robot on a cup, run the Block 2 checklist (watch each wheel). Then Wi-Fi drive-test firmware + `drive_test.py`.

---

## 2026-11-13 — Block 2 motor test PASSED on hardware

**What we did:** Uploaded the motor test via PlatformIO IDE and ran it on the real robot, wheels-up on a cup — family confirmed it works. STOP / FORWARD / BACKWARD / LEFT / RIGHT all observed. *(If you swapped any motor's wires to fix a backward wheel, add a line here — it's part of the story judges like.)*

**Checkpoint:** Block 2 ✅ — every command moves the correct wheels.

**Next:** Block 3 — the fun one: NodeMCU opens a Wi-Fi hotspot `VisionBot`, laptop joins it, and `drive_test.py` lets the kid drive with W/A/S/D.

---

## 2026-11-13 — detect_ui v2: smooth video + Start/Stop camera button

**What we did:** First live run found two issues — the video staggered badly, and there was no way to release the camera without killing the program. Rewrote `detect_ui.py`:

1. **Background camera thread** now reads the camera continuously; UI ticks just take the newest frame. (Root cause of the staggering: the old code read the camera only 7×/sec, so it kept displaying *old buffered* frames — the lag grew over time. A second process couldn't even probe the cameras while the UI held one.)
2. **Lighter transport to the browser**: 960-px JPEG for display instead of 1920-px PNG — detection still runs at full 1080p; snapshots still save full size.
3. **Start/Stop camera button**: releases the camera instantly so other programs can use it; Start reopens it.
4. Readout now shows **camera fps and UI fps** separately, so video health is visible at a glance. UI refresh 10 fps.

**Verification:** display correctly downscaled to 960 px while snapshot copy stays 1200 px; banner + both-fps readout OK; stop → "camera stopped" message frame + camera released; start → reopens; server launched headless and served the page.

**How to run:** `python detect_ui.py --cam 1` (Logitech was index 1 on our laptop; built-in is 0).

**Next:** Block 3 — Wi-Fi drive-test firmware + `drive_test.py`.

---

## 2026-11-13 — Design decision: markers-only navigation (arena box optional)

**Question:** do we need the arena bounding box at all? Can navigation work with markers alone?

**Answer/decision:** **Markers alone are enough.** The navigation loop needs exactly three things, and all come from the two markers: robot position (x, y), robot heading (from the marker's own rotation), target position (x, y). Distance + bearing error are computed in **pixel space**:
- angles need no conversion at all (degrees are degrees),
- the stop tolerance needs just ONE scale number (cm/px from the 30 cm ruler check in Block 4) — `tol_px = 8 cm × scale`.

So `calibrate.py` (4-corner perspective calibration) drops off the critical path **for a centered overhead mount**, where perspective distortion is negligible. It comes back only if the camera must sit at an angle (then distances/angles warp across the arena and the corners fix that).

Containment without a software box: "marker lost → STOP" already keeps the robot inside the camera's view — it physically cannot drive off unseen. Remaining risk is veering near a table edge *while both markers are visible* → mitigate physically: arena on the floor, or a tape/barrier boundary. The physical border still exists for visitors (where to place the card) — it just has no coordinates in software.

**Demo talking point:** the robot navigates purely from what it sees — landmark-based navigation, the same idea ships and aircraft used with lighthouses and stars, and what robots do with visual landmarks.

**Plan impact:** `main.py` = detection + math + UDP send, using the single scale number; no corner-clicking step. Extra time goes to tuning and rehearsal instead.

---

## 2026-11-13 — Arena corner markers (IDs 30-33) + height/parallax analysis

**Two questions from live testing:**
1. *Robot marker sits ~9 cm above the ground, target card lies flat — does the height difference break navigation?* → **Parallax, not a bug, but real:** an angled camera sees an elevated point shifted away from the camera vs. its ground position. Shift ≈ marker height × (distance from the point under the camera) ÷ camera height. With H=110 cm, h=9 cm: ~4 cm at 50 cm off-center, ~7 cm at 90 cm. Effect: at physical arrival the measured distance reads ~that shift instead of 0 → absorb it by mounting the marker LOW (flat plate, ~6-7 cm), camera high, stop tolerance 10 cm, card 12 cm wide. (Perfect fix, not needed for the demo: second calibration plane at robot-marker height.)
2. *Camera is always angled in practice — add corner markers?* → **Yes.** Four 6 cm corner markers give an automatic perspective correction (homography): card position exact in cm, uniform scale, and it **self-recalibrates every frame** — camera bumped at the venue = no problem, no clicking. Ground-plane corners do NOT remove the robot-marker height parallax (height effect ≠ perspective effect); low mounting + tolerance covers that.

**What we did:** extended `generate_markers.py` — `print_a4_markers.pdf` now has **page 3: the four corner markers** (IDs 30/31/32/33, ~6 cm, labeled TOP-LEFT / TOP-RIGHT / BOTTOM-RIGHT / BOTTOM-LEFT *as the camera sees the picture*). Different IDs so they can never be confused with robot 10 / target 20.

**Verification:** corner page detects exactly [30,31,32,33]; PDF has 3 pages; a synthetic frame with ALL SIX markers detects all of them together — the nav code just ignores IDs it doesn't listen to.

**Taping note:** print page 3 at 100%, cut on gray lines, tape flat inside the four arena corners. On-screen check: a robot standing near ID 30 must appear top-left of the picture. If corners end up swapped, the robot drives mirrored → re-tape.

**Plan impact:** `main.py` uses the 4 corners for perspective + cm whenever all four are visible (last-good cached if the robot briefly covers one), and falls back to the single ruler scale if no corners are taped.

---

## 2026-11-13 — Calibration decision + camera placement rules

**Decision: self-healing corner markers** (option C from the calibration discussion: baked-in numbers / one-time setup ritual / taped corners). Chosen because it's the only option whose failure mode is *none* — the correction recomputes every frame, so a bumped camera at the venue heals itself invisibly. Fallback chain stays: no corners visible → single scale; sanity habit: park robot in the START box, on-screen cm must read ~(10, 10) ± 2 cm.

**Camera placement rules (for the ~100×70 arena, C920):**
1. **50° rule (detection):** worst-case viewing angle at the FAR corner ≤ ~50°, comfortable ≤ 45°. Formula: **camera height ≥ horizontal distance to farthest corner ÷ 1.2** (tan 50° ≈ 1.2).
2. **The sneaky one — horizontal FOV (~70°):** an edge-mounted camera can't see its own NEAR corners (they sit >35° off to the sides). No height fixes this; only pulling the camera ~50 cm back from the edge does — which then forces ~130 cm height. Edge mounts are tall and fussy.
3. **Best mount: overhead plank bridge** (two chair/book stacks + plank, camera pointing down) at **110–130 cm** — everything lands ≤ ~35°, parallax shrinks (error ∝ 1/height), whole arena in frame with margin. Higher keeps helping up to ~150 cm; pixel size is not the limit.
4. **2-minute acceptance test (at home AND at the venue):** with the detect UI open — target card placed at each corner + center (5 spots, all badges green), all four corner markers 30–33 visible at once, card slid along the far edge with no amber flicker. Failing far corner → raise camera / move toward center.

**Bonus:** overhead mount fixes two problems at once — detection angle AND the robot-marker parallax from the previous entry.

---

## 2026-11-13 — Loop-robustness analysis (can detection + navigation run continuously?)

**Question:** can the program detect all markers continuously *and* steer the robot at the same time, flawlessly?

**Answer:** not flawlessly — **and it doesn't need to be.** The closed loop is error-tolerant by design. Numbers: detect 6 markers ≈ 5–15 ms per 1080p frame (camera gives a new frame every ~33 ms); decide + UDP send < 2 ms; total loop latency ~50–80 ms. Robot at ~40% PWM moves ~1 cm per frame, ~2 cm per loop latency → absorbed by the 10 cm tolerance. The loop is a fast sequential pipeline (detect → decide → send, 10–30×/s), not literally simultaneous — effectively continuous to the robot.

**Expected dropout behavior (all fail SAFE):** blurred robot marker during fast turns (realistic detection rate 90–98% of frames while moving) → hold-then-stop → reacquire when nearly still; card hidden under the parked robot → success already latched; corner briefly covered → cached correction; camera bumped → self-heals next frame; Wi-Fi/laptop failure → ESP deadman stops motors in 0.6 s.

**Two rules to bake into `main.py`:**
1. **Hold-then-stop:** on a missed frame, repeat the previous command for up to ~3 frames (~100 ms), then STOP — prevents stutter on single dropped frames.
2. **Yaw smoothing** (average last few readings): heading is the jitteriest measurement; smoothing visibly straightens driving.

**Field fix if blur appears at the venue:** lock the C920 exposure (Logitech/Camera settings) so the shutter stays fast in dim light.

**Demo feature:** cover the camera on purpose → robot stops instantly → "it never acts on stale information; if it can't see, it stops — failing safe, like real autonomous vehicles."

---

## 2026-11-13 — Table-demo camera height (arena on a 2.5 ft table)

**Question:** camera 3 ft above the table surface?

**Answer: 4 ft (≈120 cm) above the table, not 3 ft.** Coverage math (C920 straight down, 100×70 arena): at 91 cm the 70 cm direction has only ~1 cm total slack (2·H·tan21.5° ≈ 72 cm) — one bump and a corner marker exits the frame. At 120 cm: 95 cm coverage (12 cm/side margin), far-corner viewing angle 27°, worst-case parallax ≈ 4.6 cm (9 × 61/120). Acceptable minimum 105 cm; recommended 120–130 cm. Total camera height from floor ≈ 2 m.

**Rig notes:** plank bridge on stacks ON the table; C920 (~140 g) taped at plank midpoint, USB cable zip-tied; **add a USB extension (1.8–3 m) to the kit** (C920 cable is only ~1.5 m). Weight the stack bases; setup at ~2 m is an adult job. Run the 2-minute corner walk after rigging — at home today AND at the venue.

---

## 2026-11-13 — detect_ui v3: auto camera detect + plain-text buttons (corrects v2's "--cam 1" note)

**What broke / how we fixed it:**
1. Start/Stop button showed raw HTML entities ("&#9209; Stop camera") — Gradio buttons don't render entities → plain-text labels now.
2. "No camera feed" with v2: camera opens from a **background thread hang on Windows** (COM not initialised there — proven with a minimal test: worker thread never returns, main-thread opens work). v2's capture thread was the culprit → removed; all camera opens/reads/releases now happen inside the UI tick (Gradio event threads, proven in live use since v1).
3. Freshness without a thread: each tick **drains the camera buffer** (`grab()` ×4 then `retrieve()`) — displayed frames are never stale, keeping v2's smoothness fix.
4. Camera index numbering is **unstable** (C920 enumerated as 0 today, and differently per backend — v2's "--cam 1" note above was wrong). New **auto mode is the default**: probes cameras one per tick, picks the one reporting 1920×1080 (our C920 — the only 1080p camera), falls back to first working, holds "no camera found" with a retry pause.

**Verification:** auto prefers a 1080p fake over a 720p one; fallback path works; no-camera message holds; **real** end-to-end auto-detect opened camera 0 (1920×1080); Stop releases the camera; server launches headless and serves the page.

**How to run now:** `python detect_ui.py` — no `--cam` needed. The readout shows which camera auto picked (e.g. "camera 0 (1920x1080)").

---

## 2026-11-13 — detect_ui v3.1: the real camera fix — DirectShow only

**What broke:** v3 still showed no feed on the kid's run. Decisive experiment: ran camera opens on a `ThreadPoolExecutor` (the same kind of worker threads Gradio uses for ticks) → **MSMF backend HANGS there** (no result in 12 s, process barely exits; COM not initialised on those threads — even open-timeouts never fire), while **DSHOW opens and reads fine**. v1 (which worked live) was DSHOW-first; v3 had switched to MSMF-first — that single line froze the very first tick.

**Fix:** `_open_once` is now **DirectShow-only** (timeouts kept, MSMF fallback deliberately NOT added — a clean "cannot open" message beats a frozen UI). Console now prints each open attempt (`[camera] index N: DSHOW ok / cannot open`) for live diagnosis.

**Verification:** full tick path with real DSHOW opens executed on pool workers (Gradio's execution model): tick 1 → `opened camera 0 (1920x1080)`, status running, 960-px display frame; Stop button releases cleanly from a worker. All state-machine tests re-passed.

**Rule for the rest of the project:** on this laptop, OpenCV camera = `cv2.VideoCapture(idx, cv2.CAP_DSHOW)`, opened/used from Gradio event threads only, never from our own background threads.

---

## 2026-11-13 — Final demo runs on Ubuntu → camera code made platform-aware

**What we learned:** the exhibition machine is **Ubuntu** (Windows laptop is dev-only). DirectShow is Windows-only, so v3.1 as written would have found no camera on the demo machine. `detect_ui.py` and `detect_test.py` now pick the backend per OS: `CAP_DSHOW` on Windows (proven in Gradio threads here), `CAP_V4L2` on Linux (native, no COM quirks; the timeout props are Windows-only and ignored harmlessly).

**New doc:** [ubuntu-setup.md](ubuntu-setup.md) — one-time apt installs (`python3-venv libgl1` — without libgl1, `import cv2` fails with `ImportError: libGL.so.1`), venv/pip setup, camera check with `v4l2-ctl` (C920 shows two /dev/video nodes — video + metadata; the auto-detect's no-frame check skips the metadata node), `video`/`dialout` group fixes, focus lock via `v4l2-ctl`, and the rule: **run the 2-minute acceptance test on the Ubuntu box with the full rig, not on the Windows laptop.**

**Verification:** both files compile clean; fake-based auto-detect state machine still passes with the platform-aware `_open_once`. Live-camera regression skipped — the user's own UI instance was running at that moment (port 7860) and held the camera (one-camera-per-program rule applies to my tests too).

**Next:** Block 3 — Wi-Fi drive-test firmware + `drive_test.py`.

---

## 2026-11-13 — Decision: NATIVE window replaces Gradio for detection

**Why:** browser verification of detect_ui (driven with real browser automation + screenshot analysis) showed the camera opens, readout reports `camera 0 (1920x1080)` and fps counts — but the Arena view panel renders **solid black**. Meanwhile a plain-process check with the exact same open+drain pattern returned healthy frames (brightness 129/255 at 1920×1080). Camera and capture pipeline: proven good; Gradio→browser image transport: broken somewhere we couldn't see. One day before the exhibition, we stopped fighting it.

**What we did:** rewrote `code/python/detect_test.py` as the full native app — one main-thread loop (`camera → detect → draw → cv2.imshow`), no threads, no browser: auto-detects the 1080p C920 (same probe logic), drain-reads for fresh frames, same overlays (green/blue boxes, magenta line, distance, line angle, yaw), banner "BOTH MARKERS DETECTED", bottom HUD (camera info, fps, ROBOT/TARGET state), `s`=snapshot / `q`/ESC=quit, console `[camera]`/`[frame]` diagnostics (brightness every 3 s). Still a library: `detect_ui.py` imports `ArucoDetector`/`center_of`/`yaw_deg` from it — API kept intact.

**Second hard lesson (also true at the venue):** hard-killing a process that holds the camera (my TaskStops of the Gradio servers) skips `cap.release()` and after a few rounds **wedged the C920 driver** — every later open hung in fresh processes until the camera was unplugged/replugged. Rule for demo day: always close camera programs with q/ESC (or the Stop button), never by closing a terminal window with force / Task Manager, and if the camera ever "won't open": unplug-replug it.

**Verification status:** library API + synthetic detection verified; live window check pending on the kid's next run (camera was driver-wedged at the end of this session; fixed by replug).

**How to run the native UI:** `.venv\Scripts\python detect_test.py` (add `--scale 0.05` after Block 4 calibration, `--flip` if mounted upside down). Gradio `detect_ui.py` stays in the repo as a fallback.

---

## 2026-11-13 — detect_ui.py rewritten: Tkinter + Openencv (Gradio removed)

**Why:** after the black-panel transport failure, the user asked for a native UI *with real controls* — best of both: `detect_ui.py` is now a **Tkinter** window (Python's built-in GUI) driving the same detection library. No browser, no server, no Gradio dependency at all (removed from requirements.txt — also makes the Ubuntu install much lighter).

**What it has:** live video panel (960 px), green "BOTH MARKERS DETECTED" banner, per-marker badges (green/amber/red), monospace readout (fps, camera info, positions, px/cm distance, line angle, yaw), Stop/Start camera + Snapshot buttons, live settings (camera index entry — empty = auto 1080p detect, cm/px entry, 180° flip). Keys `s` / `q` / ESC still work (ignored while typing in an entry). Everything runs in the MAIN thread via `root.after(30, …)` — the camera-safe pattern proven on this laptop; window close and q/ESC release the camera cleanly (no driver wedge). Detection + camera code imported from `detect_test.py` — one source of truth.

**Ubuntu note:** Tkinter needs `sudo apt install python3-tk` — added to docs/ubuntu-setup.md.

**Verification:** compiles; imports without gradio and without creating a window; entry parsers (empty/junk/valid) and all four badge states tested; placeholder frame; synthetic both-marker detection through the shared `annotate` (602 px). Live window check pending the kid's next run (after C920 replug).

**How to run:** `.venv\Scripts\python detect_ui.py` — or `detect_test.py` for the plain cv2 window; both share the same code.

**Next:** Block 3 — Wi-Fi drive-test firmware + `drive_test.py`.

---

## 2026-11-13 — Block 3 code: Wi-Fi drive test (firmware + drive_test.py)

**What we did:**
- Firmware (`src/main.cpp`): NodeMCU opens an **open hotspot "VisionBot"** at `192.168.4.1`, listens for UDP on port **5005**. Text commands `F/B/L/R/S` + `V<0-1023>` (set speed). **600 ms deadman**: if commands stop, the robot stops itself (matches the loop-robustness design). Serial (9600) prints state changes. Same pins as the motor test — no rewiring.
- Laptop (`code/python/drive_test.py`, **stdlib only, Windows AND Ubuntu** — keyboard via msvcrt on Windows, termios/select on Linux, like the camera code's platform split): W/A/S/D + arrow keys drive, SPACE stop, `+`/`-` speed in steps of 50, ESC = burst of STOPs + quit. Sends the current command 10×/s to feed the deadman.

**Verification:** firmware compile-verified for `nodemcuv2` (esp8266 core 3.1.2); `drive_test.py` syntax-checked. Hardware run pending.

**Numbers we used:** UDP port 5005 · 10 Hz command rate · deadman 600 ms · default speed 400/1023 ≈ 40% · speed step 50.

**How to run:** join laptop Wi-Fi to "VisionBot", then `.venv\Scripts\python code\python\drive_test.py` (Windows) or `.venv/bin/python code/python/drive_test.py` (Ubuntu). Robot on the floor, ~3 m range.

**Next:** drive it around (the reward after Block 2!), then test the deadman — laptop Wi-Fi off mid-drive must stop the robot in ~0.6 s. Then Block 4 acceptance run with the rig.

---

## 2026-11-13 — ✅ Tkinter UI CONFIRMED WORKING live

User report after C920 replug: **"works perfect!"** — live video in the native Tkinter window. The camera/UI saga is closed: detection runs on a proven native stack (Tkinter + OpenCV, main-thread, DSHOW on Windows / V4L2 for the Ubuntu demo box).

**Remaining on detection (Block 4 physical steps):** rig the camera ~120 cm over the arena → 2-minute 5-spot acceptance test (card at 4 corners + center, all badges green, corner markers 30–33 visible) → record px→cm scale (markers 30 cm apart) and robot yaw pointing N/E/S/W into this log.

**Project state:** detection UI ✅ (live-confirmed) · Block 2 motors ✅ · Block 3 code ✅ written (hardware run pending) · `main.py` navigation — the last big piece.

---

## 2026-11-13 — Q&A: what the corner markers are for + placement rules

**User question:** what is the use of the edge/corner markers (IDs 30–33)? Keep them always? Exact distances needed?

**Answer (full guide:** [corner-markers.md](corner-markers.md)**):**
- **Use:** per-frame perspective correction (homography) — true cm anywhere in the arena, and **self-healing after a camera bump at the venue**. Fallback without them: the single ruler px→cm scale (fine for our centered overhead rig) — the demo never depends on them, but taping them to the board permanently is the plan.
- **Keep always?** Yes — tape/glue them permanently to the arena board so they travel with it; nothing to redo at the venue.
- **Exact placement?** NOT needed — the homography learns the real geometry from wherever the four markers sit. What matters: **order as the camera sees it (30=TL, 31=TR, 32=BR, 33=BL** — swapped = mirrored driving = re-tape), each near its corner, flat, all four visible; plus the 10-second sanity check (robot at ID 30 appears top-left on screen). **One-time ruler measurement:** long + short side between taped markers → recorded for `main.py`'s true-cm mapping.

---

## 2026-11-13 — Block 3 first hardware run: radio works, right motor inverted

**What happened:** Wi-Fi link, all four drive commands and `+`/`-` speed work. But directions came out scrambled: W=spin right, A=straight back, S=spin left, D=straight forward.

**Diagnosis:** the pattern decodes to ONE fault — left wheel correct in every command, right wheel inverted in every command (e.g. W sends both-forward: left went forward, right went backward → spin right). So the right motor's two wires are swapped at the L298N. Radio/speed/deadman-feed all proven good — that's why speed worked fine.

**Fix:** battery OFF, swap the right motor's wire pair at `OUT3`/`OUT4`, retest — expecting W=fwd, S=back, A=spin left, D=spin right. *(Retest result: ______ )* Lesson for the logbook: Block 2's wheels-up pass said "worked" but didn't compare each wheel's direction against the serial labels — checking that properly catches this on the cup, before the robot hits the floor.

**Still to test:** the deadman (laptop Wi-Fi off mid-drive → robot self-stops in ~0.6 s).

**Next:** retest after the wire swap → deadman test → Block 3 ✅.

---

## 2026-11-13 — main.py: the full autonomous program (Block 5 code)

**User request:** one separate program — CustomTkinter + OpenCV UI, corner-marker detection, drive the robot to the target at a constant speed controllable in the UI, commands over Wi-Fi. Built as `code/python/main.py` (the plan's Block-5 program).

**What it is:**
- **ArenaMap** — corner markers 30–33 → per-frame homography → true cm positions AND heading (the robot's front vector is mapped through the homography too, so a rotated camera corrects itself). Corner hidden → cached last-good map. No corners ever → single ruler-scale fallback (cm/px entry).
- **Navigator** — the locked simple loop: turn-in-place → straight → stop. ONE constant speed (slider 10–100%, default 40%). Angle tol slider (20°), stop tol slider (10 cm). Arrived latches until the card moves >5 cm out (visitor moves card → robot re-aims). Marker lost → hold last command 3 frames → STOP. Yaw smoothed (vector-mean of last 5). Runtime fix toggles: **invert turn direction** + **heading offset** — sign problems get fixed at the UI, no code edits at the venue.
- **RobotLink** — same UDP protocol the firmware already speaks (F/B/L/R/S + V, 10 Hz keepalive feeding the 600 ms deadman). Stop burst on PAUSE/E-STOP/quit/window close.
- **UI** — live annotated video (boxes, cm distance, heading arrow, err°), state banner color-coded (TURNING/DRIVING/ARRIVED/LOST), E-STOP button (ESC), START (SPACE), snapshot, camera start/stop + auto-detect (the proven DSHOW/V4L2 main-thread pattern), monospace readout (state, arena mode, dist/err, tolerances, packet count, fps).

**Verification (9 headless checks, all passed):** synthetic 6-marker frames → homography cm exact vs ground truth (25.0/35.0 cm, dist 28.6 cm); facing-target → `F` (err 0°); rotated → TURN with invert flipping R↔L; 4 cm → ARRIVED latch, card moved 30 cm → resumes; marker loss → holds F,F,F then S + LOST; corner removed → cached map identical; no-corner frame → ruler-scale mode; UDP loopback → exact wire bytes `F`,`V400`,`S×5`; GUI construct/params/readout/shutdown clean. customtkinter 6.0.0 installed into `.venv`, added to requirements.txt.

**Live checklist for the first run:** ① rig camera + tape corners, robot+card in view ② check "corners (live)" in the readout ③ press START: if the robot turns AWAY from the card, tick "Invert turn direction" ④ adjust speed slider live. Full rig acceptance test = the 2-minute corner walk from the placement rules.

**Next:** live closed-loop run on the real arena (Block 5 checkpoint: card reached 5× in a row), then Block 6 safety demos (cover camera → stop; Wi-Fi off → deadman) and rehearsal.

---

## 2026-11-13 — main.py camera fix: window froze on Start/Stop camera

**What broke:** clicking Start/Stop camera ran `open_camera_auto()` — up to 3 camera opens back-to-back **on the UI thread** (each blocks 1–3 s). The Tk event loop stalled, Windows flagged the window "Not Responding" after ~5 s. If the app was then force-killed mid-open, the C920 driver can wedge (known failure from the detect_ui saga — every later open hangs until the camera is unplugged/replugged).

**Fix:** the camera open is now a **state machine that opens ONE index per UI tick** ("opening"/"on"/"off"): the banner paints "Opening camera N… (a few seconds)" *before* the blocking call (`update_idletasks`), the queue advances one index per 30 ms tick, so the window stays alive between tries. C920 (1080p) adopted the moment it's found; first working non-1080p kept as fallback and **released when a better one is adopted** (the tests caught a leak: the backup camera stayed open); all-fail → clean "No camera found — click to retry". Stop during opening releases the pending fallback. Same DSHOW/V4L2, main-thread pattern as the rest of the project.

**Verification (fake-camera state machine, no hardware touched):** A) idx0 fails / idx1 720p / idx2 1080p → 1080p adopted on tick 3, 720p released; B) only 720p exists → fallback adopted, not released-then-adopted; C) nothing opens → state off + retry banner; D) Stop mid-probe releases the fallback. GUI smoke-clean shutdown.

**Field note for demo day:** if the camera ever "won't open" or hangs at opening — close every camera program first, and if it persists >15 s: **unplug/replug the C920** (driver wedge). Always quit camera apps with their own button/q/ESC, never by killing the process.

**Next:** unchanged — live closed-loop run (Block 5), safety demos, rehearsal.

---

## 2026-11-13 — Demo rule: main.py uses the C920 only, never the integrated camera

**Change:** the auto-probe no longer keeps a non-1080p camera as fallback. A camera that opens but isn't 1080p is **released immediately and skipped** (console: "not the C920, skipped"); if no 1080p camera is found the app refuses with **"No 1080p camera found — connect the Logitech C920, then click Start/Stop camera"** instead of silently substituting the built-in webcam. A forced camera index is held to the same rule. Rationale: a wrong-camera feed at the venue (markers invisible, everything looks broken) is worse than a loud "connect the C920".

**Verification (fake cameras):** 720p@0 + C920@1 → 720p skipped/released, C920 adopted; integrated-only → refused cleanly, nothing left open; forced index of a 720p camera → refused too.

**Note:** `detect_test.py` / `detect_ui.py` (dev tools) still fall back to the first working camera — fine for the bench; tell us if you want them strict too.

---

## 2026-11-13 — main.py camera fix, round 2: helper PROCESS (the real freeze fix)

**What broke:** even with one-open-per-tick, clicking Start/Stop camera froze the window again. Root cause: a **single** `cv2.VideoCapture.open()` can block FOREVER on a wedged driver — the timeout properties never fire (known from the v3.1 saga) — and then the UI thread is stuck *inside* the call; no tick-chunking can help. The earlier force-kills had likely left the C920 driver wedged, guaranteeing the hang.

**Fix (architectural):** all camera work moved into a **helper process** (`camera_worker` + `CameraFeed`):
- The UI thread only drains queues and decodes JPEGs — nothing it calls can block on the camera. Ever.
- Helper opens/probes (C920-only rule kept), reads frames, ships them as JPEGs over a queue (drop-oldest at depth 2).
- **Watchdog:** no helper news for 15 s while opening → helper killed, banner: *"Camera stuck (driver) — UNPLUG and REPLUG the C920, then click Start/Stop camera"*. Helper respawns on the next click.
- Stop/shutdown: graceful quit (lets the helper `release()` the camera) with terminate as fallback — and the UI stays alive either way.

**Verification (4 staged checks, hard timeouts, real spawn):** watchdog fires on silence/quiet while talking; newest-JPEG decode + full queue drain; **real spawned helper** → `('opening',9)`, `('fail',)` in ~2 s, shutdown 0.1 s; **full GUI** → toggle → fail → "No 1080p camera found", `app.update()` pumping throughout, clean shutdown.

**Test lessons (ours, not the app's):** a spawned-process test MUST run under an `if __name__ == "__main__"` guard (else children re-run the test file); and a `maxsize=2` mp.Queue with 3 puts and **no consumer deadlocks** — both cost a debugging round.

**User action if it ever says "Camera stuck (driver)":** unplug/replug the C920, click Start/Stop camera again. That message is the app catching a wedged driver safely instead of freezing.
