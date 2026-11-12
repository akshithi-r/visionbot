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
