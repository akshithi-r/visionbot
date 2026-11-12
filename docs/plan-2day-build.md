# VisionBot — 2-Day Build Plan

**Build days:** 12–13 Nov 2026 · **Exhibition:** 14 Nov 2026 *(assumed — please confirm the exact date!)*

**Golden rule:** every block below ends with a working checkpoint. If a checkpoint fails, stop and fix it before moving on. Never carry a broken subsystem into the next block.

---

## 0. How we work

- **Folders:** everything written/doc-related lives in `docs/`, all code lives in `code/`.
- **Kid builds, parent guides.** The kid does the assembly, wiring, typing and testing. The parent: checks wiring before any power-on, handles hot glue/solder supervision, and helps read code. If the kid can explain a step, the kid owns that step.
- **Safety rules (non-negotiable):**
  1. Battery disconnected while wiring or changing anything.
  2. Parent inspects wiring before the first power-on of every block.
  3. First motor tests always happen with wheels off the ground (robot on a cup/tumbler).
  4. Motors too fast = reduce PWM, never "it'll be fine".

---

## 1. Two design decisions (locked in today)

### Decision 1 — The robot is UNTETHERED (no cable to the laptop)

The NodeMCU cannot stay powered from the laptop USB while the robot is driving — the cable will snag. So:

| Part | Powered by |
|---|---|
| Motors + L298N | 4×1.5V battery pack (6V) → L298N `+12V` and `GND` |
| NodeMCU (now) | Small USB power bank on the chassis *(best with the 6V pack — the L298N's onboard 5V regulator is unreliable below 7V)* |
| NodeMCU (later, exhibition) | 6×NiMH (7.2V) pack → L298N `+12V`, and L298N `5V` output → NodeMCU `VIN` (keep the 5V jumper ON) |

**Communication:** laptop → NodeMCU over **Wi-Fi using UDP**. The NodeMCU creates its own hotspot (`VisionBot`); the laptop joins it. No venue Wi-Fi needed, no cables, and the link that drives the motors also becomes our emergency-stop path.

### Decision 2 — Slow and simple wins

- Motor PWM starts at ~40%. Slow robot = easy to track at 30 fps, safe near visitors, and looks "deliberate" to judges.
- Navigation = 3 moves only: **turn-in-place → drive straight → stop**. No curves, no fancy path planning. Tune later if time permits.

---

## 2. Arrange tonight (checklist)

- [ ] Arena: white foam board or chart paper, ~100 × 70 cm, **matte** (not glossy — glare kills detection)
- [ ] Thick card stock: one 12×12 cm destination card + one small plate for the robot's marker
- [ ] USB power bank + cable (most homes have one)
- [ ] 4×AA battery holder — with or without its own switch (no switch on yours? any small on/off switch works, wiring in [wiring-nodemcu-l298n.md](wiring-nodemcu-l298n.md)) — and a 6×AA holder for the NiMH pack later
- [ ] Camera mount — pick ONE (details in §2b): cardboard bridge (centered overhead) OR lamp-arm/tripod (angled, from one side)
- [ ] One big cardboard delivery box (mount material — doubles as the packing box) + a ruler or dowel for a crossbar
- [ ] Two table lamps (we control the lighting, not the exhibition hall)
- [ ] Double-sided tape, normal tape, zip ties, scissors
- [ ] **Software (parent, ~40 min):** Python 3.11+ installed; `pip install opencv-python numpy`; PlatformIO IDE (already set up — the blink test ran on it)
- [ ] Print the two ArUco markers once `code/python/generate_markers.py` is ready (next work session)

### 2b. Camera mounting — you do NOT need a cage

Strictly-centered is *not* required. Two workable setups:

| Setup | How | Notes |
|---|---|---|
| **A. Cardboard bridge (easiest)** | Two cardboard towers (or one delivery box cut into an inverted U) at the arena's short edges + a ruler/dowel crossbar; webcam taped to the crossbar pointing straight down, ~100 cm above the arena | Camera sees straight down → uniform scale, most reliable marker detection |
| **B. Side mount (angled)** | Webcam on a desk-lamp arm / music stand / tripod clamped at one **short** edge of the arena, tilted down over it. Height ≥ the arena dimension pointing away from the camera (≥ 70–80 cm for a 100×70 arena with the short edge facing the camera) | Works because our 4-corner calibration corrects perspective (homography) — positions AND heading come out correct |

Whichever you choose:

- The camera must see **all 4 corners** of the arena.
- After calibration, tape the camera in place. If it gets bumped (e.g., at the venue), recalibration is just re-clicking 4 corners — about 1 minute.
- **Detection rule:** the far-edge markers must not be viewed at more than ~45–55° tilt. Higher camera = better detection. (This is why side mounts need height — the math corrects position, but detection itself needs to see the marker's face.)
- Lock the webcam focus once (Logitech/Camera settings, manual focus) so autofocus doesn't hunt during the demo.
- If you side-mount, tell the judges — perspective correction is a bonus talking point ("the same idea used to make aerial maps").

---

## 3. Wiring map

Parent checks every connection against this table **before** the first power-on.

### Signals: NodeMCU → L298N

| L298N pin | NodeMCU pin | Notes |
|---|---|---|
| ENA | D1 (GPIO 5) | Left motor speed (PWM) — **remove the ENA jumper cap** |
| IN1 | D5 (GPIO 14) | Left motor direction |
| IN2 | D6 (GPIO 12) | Left motor direction |
| IN3 | D7 (GPIO 13) | Right motor direction |
| IN4 | D0 (GPIO 16) | Right motor direction (D0 has no PWM — fine, direction is just on/off) |
| ENB | D2 (GPIO 4) | Right motor speed (PWM) — **remove the ENB jumper cap** |
| GND | GND | **Common ground is mandatory** — robot won't move reliably without it |

D3 (GPIO 0), D4 (GPIO 2) and D8 (GPIO 15) are deliberately avoided (boot-strapping pins — motors on those can stop the NodeMCU from starting). Full guide: [wiring-nodemcu-l298n.md](wiring-nodemcu-l298n.md).

### Power

- Battery pack (+) → [switch if the holder has none] → L298N `+12V`, battery (−) → L298N `GND`
- Keep the small **5V jumper ON** the L298N
- Power bank → NodeMCU USB socket (for now)

---

## 4. Day 1 — Build + each subsystem tested alone

### Block 1 · Mechanics (~1.5 h) — *kid does almost everything*

1. Mount the two BO motors near one end of the chassis (double-sided tape + zip ties).
2. Attach wheels; fix the caster wheel at the opposite end.
3. Mount: L298N, NodeMCU, battery holder (switch reachable), power bank.
4. Tape the marker plate flat on top of the robot — **must be level**, not tilted.
5. Photo for the logbook.

✅ **Checkpoint:** robot sits flat, all 3 wheels touch the ground, nothing dangles.

### Block 2 · Wiring + motor test (~1.5 h)

1. Wire everything per the table above with the battery **off**. Parent inspects.
2. Parent uploads `code/bot-program/bot-code/` (PlatformIO — the **→ Upload** arrow); robot **on a cup, wheels up**.
3. Test: forward, left turn, right turn, stop. Kid watches each wheel.
4. A wheel spinning the wrong way = swap that motor's two wires at the L298N terminal. (This is normal — expect it once.)

✅ **Checkpoint:** all four commands move the correct wheels, still USB-tethered on the cup.

### Block 3 · Wi-Fi driving test (~1.5 h) — *the fun one*

1. NodeMCU firmware creates hotspot `VisionBot`; laptop joins it.
2. Run `code/python/drive_test.py` — keys **W/A/S/D** drive the robot.
3. Kid drives it around the floor untethered. Seriously — play with it 10 minutes. This validates power, motors and radio in one go, and it's the reward after Block 2.

✅ **Checkpoint:** robot drives on battery power with **no cables attached**, ~3 m from the laptop.

### Block 4 · Camera + markers (~1.5 h)

1. Mount the webcam per §2b (bridge or side mount — both fine); lock focus (manual focus in the Logitech/Camera settings if available).
2. Print markers (ID 10 = robot, ~8 cm; ID 20 = destination, ~8 cm on the card).
3. Run `code/python/detect_test.py` — live video with boxes + IDs drawn.
4. Kid slides both markers to every corner of the arena — both IDs must be detected everywhere. (If the far corners miss detection, raise the camera or switch to the bridge mount.)
5. **Perspective calibration:** run `code/python/calibrate.py` and click the 4 arena corners in order (top-left → top-right → bottom-right → bottom-left, measured in cm from a fixed real corner). This saves the transform — from then on all positions are reported directly in centimetres, and an angled camera is fully corrected.
6. **Scale check:** place the two markers exactly 30 cm apart with a ruler — the reported distance should read ~30 cm.
7. **Heading sanity check:** point the robot north/south/east/west and note the reported angle each time (we'll use this to fix sign conventions tomorrow — write the 4 numbers down).

✅ **Checkpoint:** both markers detected in the whole arena, calibration saved, 30 cm reads ~30 cm, 4 heading numbers written down.

**End of Day 1 = wheels work wirelessly AND the camera sees both markers.** If either fails, that's the evening's job — Day 2 depends on both.

---

## 5. Day 2 — Integration, robustness, rehearsal

### Block 5 · Close the loop (~2.5 h) — kid + parent pair up

1. Run `code/python/main.py` (detect → compute → send, 10×/sec).
2. First goal is boring on purpose: robot only **rotates** to face the card, then stops. Fix the turn direction if it turns away (invert the heading sign — that's what yesterday's 4 numbers are for).
3. Then enable driving: rotate until facing the target (±20°) → drive straight → stop within 8 cm.
4. Kid moves the card; robot re-aims and drives. Repeat a lot. Tune with the cheat sheet below.

Expected and *normal* fixes: left/right inverted (swap IN3/IN4 wire or one line of code), heading sign flipped, overshoot → lower PWM.

✅ **Checkpoint:** from any starting spot, robot reaches a card placed anywhere, 5 times in a row.

### Block 6 · Safety & demo polish (~1 h)

1. Marker lost from view → laptop sends STOP automatically (already in the code); test by covering the camera.
2. **SPACE = START, ESC = emergency STOP** shown on screen.
3. Radio lost → NodeMCU stops motors by itself after 0.6 s of silence (deadman timer) — test by turning off laptop Wi-Fi mid-drive.

✅ **Checkpoint:** robot stops on camera-covered and Wi-Fi-off tests.

### Block 7 · Rehearse + backup (~1 h)

1. Full visitor flow ×5: visitor places card → SPACE → robot drives → stops on card.
2. Record a **video of the best run on a phone** — insurance if anything fails at the venue.
3. Kid rehearses the 60-second explanation (below) to a parent, twice.

### Block 8 · Logbook + packing (~1 h)

1. Fill `docs/project-log.md` with today's numbers (scale, tolerances, PWM) and insert photos.
2. Print the proposal if the school wants it. Pack the kit (Section 7).

---

## 6. Tuning cheat sheet (starting values)

| Parameter | Start | If… |
|---|---|---|
| Motor PWM (drive) | 45% | overshoots the card → 35–40% |
| Motor PWM (turn) | 40% | doesn't turn on the surface → 50% |
| Angle tolerance | 20° | zigzags while driving → 30° |
| Distance tolerance (stop) | 8 cm | stops short → 10 cm |
| Command rate | 10 Hz | keep fixed |
| Deadman timeout | 600 ms | keep fixed |

**Change ONE number at a time, then do 3 test runs.** The kid writes every change in the log — judges love seeing the tuning history.

---

## 7. Exhibition-day kit

Laptop (charged + charger) · robot · battery pack (fresh cells) · power bank (charged) · webcam + stand · arena board · destination card + 2 spare cards · 2 table lamps + extension cord · tape, zip ties, screwdriver · printed 60-second script · backup video on the phone · this folder printed, if wanted.

**At the venue:** set up first, run the heading sanity check (lighting is different!), do one full test run before visitors arrive.

---

## 8. Kid's 60-second demo script (say it in your own words)

1. "This robot finds its own position using that camera — see the pattern on top? The computer recognizes it." *(point at camera + marker)*
2. "You put the target card anywhere. Please place it." *(visitor places card)*
3. "The computer uses the distance formula and atan2 — the same math we learn in coordinate geometry — to find how far and which way."
4. "No remote control: the camera watches, the computer corrects, the motors obey — that's a closed feedback loop."
5. *(press SPACE)* "Watch it correct itself — you can even gently push it off course." *(robot reaches card)* "And it stops because the distance is now inside the tolerance."

---

## 9. Fallback ladder (if time runs short)

1. Drop Block 6 polish — keep only ESC emergency stop.
2. Widen tolerances (30°, 10 cm) instead of tuning for precision.
3. Worst case: fixed slow speed, no turning-while-driving — still a fully autonomous demo.
4. Never skip: backup video + rehearsed script. A confident explanation saves any hardware hiccup.
